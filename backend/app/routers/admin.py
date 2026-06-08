from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from app.database import get_db
from app.models.all_models import Tenant, User, Subscription, WhatsAppSession, Message, AIUsageLog, CampaignLog, PaymentTransaction, AuditLog, Chatbot, KnowledgeBase, KBDocument
from app.core.websocket import websocket_manager
from uuid import UUID
from typing import List, Optional
from pydantic import BaseModel, EmailStr
from datetime import datetime, timezone, timedelta
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from app.config import settings
import httpx
import redis
import hmac
import hashlib
import time
import base64
import struct
import os

router = APIRouter(prefix="/admin", tags=["Master Super Admin Control Plane"])
security_bearer = HTTPBearer()

# ----------------------------------------------------------------------
# AUDIT LOGGING HELPER
# ----------------------------------------------------------------------
def log_audit(
    db: Session,
    admin_user_id: Optional[UUID],
    action_type: str,
    target_tenant_id: Optional[UUID] = None,
    affected_resources: Optional[str] = None,
    old_state: Optional[dict] = None,
    new_state: Optional[dict] = None
):
    try:
        log = AuditLog(
            admin_user_id=admin_user_id,
            action_type=action_type,
            target_tenant_id=target_tenant_id,
            affected_resources=affected_resources,
            old_state=old_state,
            new_state=new_state
        )
        db.add(log)
        db.commit()
    except Exception as e:
        print("[Audit Log] Error writing audit log to DB:", e)


# ----------------------------------------------------------------------
# SUPER ADMIN SECURITY MIDDLEWARE
# ----------------------------------------------------------------------
def get_current_super_admin_basic(
    credentials: HTTPAuthorizationCredentials = Depends(security_bearer),
    db: Session = Depends(get_db)
) -> User:
    """
    Basic token check for admin access (e.g. before password rotation or 2FA verification).
    Checks signature, expiration, role, and Redis token blacklist.
    """
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate administrator credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # 1. Check Redis token blacklist
    try:
        r = redis.Redis.from_url(settings.REDIS_URL)
        if r.get(f"blacklist_token:{token}"):
            raise credentials_exception
    except Exception as e:
        print("[Auth Middleware] Redis blacklist connection error:", e)
        
    # 2. Decode JWT claims
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        scopes: list = payload.get("scopes", [])
        if user_id is None or "super_admin" not in scopes:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    # 3. Retrieve and assert active user context
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or user.role != "admin" or not user.is_active:
        raise credentials_exception
        
    return user

def get_current_super_admin(
    current_user: User = Depends(get_current_super_admin_basic),
    credentials: HTTPAuthorizationCredentials = Depends(security_bearer)
) -> User:
    """
    Full security verification. Enforces forced password rotation and 2FA verification.
    """
    token = credentials.credentials
    
    # Assert password change requirement
    if current_user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forced password change required on first login."
        )
        
    # Assert TOTP verification claim
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.ALGORITHM])
        totp_verified: bool = payload.get("totp_verified", False)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate authorization claims."
        )
        
    if current_user.totp_enabled and not totp_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="TOTP 2FA verification required."
        )
        
    return current_user


# ----------------------------------------------------------------------
# PYDANTIC MODEL SCHEMAS
# ----------------------------------------------------------------------
class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str

class PasswordChangeRequest(BaseModel):
    new_password: str

class TOTPVerifyRequest(BaseModel):
    code: str

class PlanChangeRequest(BaseModel):
    plan_tier: str
    max_bots: Optional[int] = None
    max_messages: Optional[int] = None
    days: Optional[int] = 30

class QuotaOverrideRequest(BaseModel):
    max_bots: int
    max_messages: int

class MaintenanceBroadcastRequest(BaseModel):
    message: str

class TerminateRequest(BaseModel):
    mode: str # instant or graceful

class RetentionPolicyRequest(BaseModel):
    policy: str # archive, delete


# ----------------------------------------------------------------------
# TOTP 2FA CORE IMPLEMENTATION (Pure Python)
# ----------------------------------------------------------------------
def verify_totp_code(secret: str, code: str) -> bool:
    try:
        secret = secret.strip().replace(" ", "")
        missing_padding = len(secret) % 8
        if missing_padding:
            secret += "=" * (8 - missing_padding)
        key = base64.b32decode(secret, casefold=True)
        
        time_step = int(time.time() / 30)
        
        # Clock drift window of +/- 1 time step (30 seconds)
        for drift in [-1, 0, 1]:
            t = time_step + drift
            msg = struct.pack(">Q", t)
            hmac_hash = hmac.new(key, msg, hashlib.sha1).digest()
            offset = hmac_hash[-1] & 0x0F
            truncated_hash = hmac_hash[offset : offset + 4]
            bin_code = struct.unpack(">I", truncated_hash)[0] & 0x7FFFFFFF
            calculated_code = bin_code % 1000000
            
            if f"{calculated_code:06d}" == code:
                return True
        return False
    except Exception as e:
        print("[TOTP Core Error] Verification failed:", e)
        return False


# ----------------------------------------------------------------------
# SUPER ADMIN AUTHENTICATION CONTROLLERS
# ----------------------------------------------------------------------
@router.post("/auth/login")
def admin_login(payload: AdminLoginRequest, db: Session = Depends(get_db)):
    """
    Validates Super Admin credentials. Supports first-login forced rotation and TOTP checks.
    """
    email = payload.email.lower()
    try:
        r = redis.Redis.from_url(settings.REDIS_URL)
        failed_key = f"admin_failed_login:{email}"
        failed_count = int(r.get(failed_key) or 0)
        
        # Brute-force rate limiter / IP bans
        if failed_count >= 5:
            r.setex(f"admin_lockout:{email}", 900, "locked")
            log_audit(
                db=db,
                admin_user_id=None,
                action_type="ACCOUNT_LOCKED",
                affected_resources="auth",
                new_state={"email": email, "reason": "Too many failed login attempts"}
            )
            raise HTTPException(status_code=429, detail="Too many failed login attempts. Try again in 15 minutes.")
            
        if r.get(f"admin_lockout:{email}"):
            raise HTTPException(status_code=429, detail="Account is temporarily locked. Try again in 15 minutes.")
    except redis.RedisError as e:
        print("[Auth Login] Redis lockout failed:", e)
        r = None

    from app.core.security import verify_password
    user = db.query(User).filter(User.email == email).first()
    if not user or user.role != "admin" or not verify_password(payload.password, user.password_hash):
        if r:
            r.incr(failed_key)
            r.expire(failed_key, 3600)
            
        log_audit(
            db=db,
            admin_user_id=user.id if user else None,
            action_type="FAILED_ADMIN_LOGIN",
            affected_resources="auth",
            new_state={"email": email}
        )
        raise HTTPException(status_code=401, detail="Invalid email or password.")
        
    if r:
        r.delete(failed_key)
        
    expires = timedelta(hours=2) # 2-Hour admin session expiration
    
    # 1. Forced Password Rotation Block
    if user.must_change_password:
        token_payload = {
            "exp": datetime.utcnow() + expires,
            "sub": str(user.id),
            "scopes": ["super_admin"],
            "totp_verified": False
        }
        token = jwt.encode(token_payload, settings.JWT_SECRET, algorithm=settings.ALGORITHM)
        log_audit(
            db=db,
            admin_user_id=user.id,
            action_type="ADMIN_LOGIN_FORCE_PASSWORD_CHANGE",
            affected_resources="auth"
        )
        return {
            "must_change_password": True,
            "totp_enabled": False,
            "access_token": token,
            "token_type": "bearer",
            "tenant_id": str(user.tenant_id)
        }
        
    # 2. TOTP 2FA verification challenge
    if user.totp_enabled:
        token_payload = {
            "exp": datetime.utcnow() + expires,
            "sub": str(user.id),
            "scopes": ["super_admin"],
            "totp_verified": False
        }
        token = jwt.encode(token_payload, settings.JWT_SECRET, algorithm=settings.ALGORITHM)
        log_audit(
            db=db,
            admin_user_id=user.id,
            action_type="ADMIN_LOGIN_TOTP_CHALLENGE",
            affected_resources="auth"
        )
        return {
            "must_change_password": False,
            "totp_enabled": True,
            "access_token": token,
            "token_type": "bearer",
            "tenant_id": str(user.tenant_id)
        }
        
    # 3. Successful Normal Login
    token_payload = {
        "exp": datetime.utcnow() + expires,
        "sub": str(user.id),
        "scopes": ["super_admin"],
        "totp_verified": True
    }
    token = jwt.encode(token_payload, settings.JWT_SECRET, algorithm=settings.ALGORITHM)
    
    log_audit(
        db=db,
        admin_user_id=user.id,
        action_type="SUCCESSFUL_ADMIN_LOGIN",
        affected_resources="auth",
        new_state={"email": email}
    )
    
    return {
        "must_change_password": False,
        "totp_enabled": False,
        "access_token": token,
        "token_type": "bearer",
        "role": "admin",
        "tenant_id": str(user.tenant_id)
    }



@router.post("/auth/password-change")
def admin_password_change(
    payload: PasswordChangeRequest,
    admin: User = Depends(get_current_super_admin_basic),
    db: Session = Depends(get_db)
):
    """
    Forced password rotation endpoint allowing password reset on first login.
    """
    new_pw = payload.new_password.strip()
    if len(new_pw) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long.")
        
    from app.core.security import get_password_hash
    old_must_change = admin.must_change_password
    admin.password_hash = get_password_hash(new_pw)
    admin.must_change_password = False
    db.commit()
    db.refresh(admin)
    
    log_audit(
        db=db,
        admin_user_id=admin.id,
        action_type="ADMIN_PASSWORD_ROTATE",
        target_tenant_id=admin.tenant_id,
        affected_resources="user_security",
        old_state={"must_change_password": old_must_change},
        new_state={"must_change_password": False}
    )
    
    expires = timedelta(hours=2)
    totp_verified = not admin.totp_enabled
    
    token_payload = {
        "exp": datetime.utcnow() + expires,
        "sub": str(admin.id),
        "scopes": ["super_admin"],
        "totp_verified": totp_verified
    }
    token = jwt.encode(token_payload, settings.JWT_SECRET, algorithm=settings.ALGORITHM)
    
    return {
        "status": "success",
        "message": "Password updated successfully.",
        "totp_enabled": admin.totp_enabled,
        "access_token": token,
        "token_type": "bearer",
        "tenant_id": str(admin.tenant_id)
    }

@router.post("/auth/totp/setup")
def admin_totp_setup(
    admin: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db)
):
    """
    Generates a secure cryptographically strong TOTP secret and QR uri.
    """
    import secrets
    random_bytes = secrets.token_bytes(20)
    secret = base64.b32encode(random_bytes).decode('utf-8').replace('=', '')
    
    admin.totp_secret = secret
    db.commit()
    
    label = f"ReplyOS-Admin:{admin.email}"
    otpauth_uri = f"otpauth://totp/{label}?secret={secret}&issuer=ReplyOS"
    
    return {
        "secret": secret,
        "otpauth_uri": otpauth_uri
    }

@router.post("/auth/totp/enable")
def admin_totp_enable(
    payload: TOTPVerifyRequest,
    admin: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db)
):
    """
    Verifies the generated TOTP setup code, locks 2FA, and returns recovery codes.
    """
    if not admin.totp_secret:
        raise HTTPException(status_code=400, detail="TOTP secret not initialized. Trigger setup first.")
        
    code = payload.code.strip()
    if not verify_totp_code(admin.totp_secret, code):
        raise HTTPException(status_code=400, detail="Invalid 2FA verification code.")
        
    admin.totp_enabled = True
    
    # Generate 8 recovery codes
    import secrets
    recovery_codes = [secrets.token_hex(4) for _ in range(8)]
    admin.recovery_codes = recovery_codes
    db.commit()
    
    log_audit(
        db=db,
        admin_user_id=admin.id,
        action_type="ADMIN_TOTP_ENABLED",
        target_tenant_id=admin.tenant_id,
        affected_resources="user_security",
        new_state={"totp_enabled": True, "recovery_codes_count": 8}
    )
    
    return {
        "status": "success",
        "message": "TOTP 2FA successfully locked and enabled.",
        "recovery_codes": recovery_codes
    }

@router.post("/auth/totp/verify")
def admin_totp_verify(
    payload: TOTPVerifyRequest,
    admin: User = Depends(get_current_super_admin_basic),
    db: Session = Depends(get_db)
):
    """
    Verifies the TOTP code or recovery code to unlock the final super admin JWT token.
    """
    code = payload.code.strip().lower()
    recovery_success = False
    
    # 1. Recovery code validation
    if admin.recovery_codes and isinstance(admin.recovery_codes, list):
        if code in admin.recovery_codes:
            updated_codes = [c for c in admin.recovery_codes if c != code]
            admin.recovery_codes = updated_codes
            db.commit()
            recovery_success = True
            log_audit(
                db=db,
                admin_user_id=admin.id,
                action_type="ADMIN_RECOVERY_CODE_USED",
                affected_resources="user_security",
                new_state={"codes_remaining": len(updated_codes)}
            )
            
    # 2. Dynamic TOTP verification
    if not recovery_success:
        if not admin.totp_secret or not verify_totp_code(admin.totp_secret, code):
            raise HTTPException(status_code=400, detail="Invalid 2FA verification code or recovery code.")
            
    expires = timedelta(hours=2)
    token_payload = {
        "exp": datetime.utcnow() + expires,
        "sub": str(admin.id),
        "scopes": ["super_admin"],
        "totp_verified": True
    }
    token = jwt.encode(token_payload, settings.JWT_SECRET, algorithm=settings.ALGORITHM)
    
    log_audit(
        db=db,
        admin_user_id=admin.id,
        action_type="SUCCESSFUL_ADMIN_2FA_VERIFICATION",
        affected_resources="auth"
    )
    
    return {
        "status": "success",
        "message": "TOTP 2FA validation succeeded.",
        "access_token": token,
        "token_type": "bearer",
        "role": "admin",
        "tenant_id": str(admin.tenant_id)
    }

@router.post("/auth/revoke-session")
def admin_revoke_session(
    credentials: HTTPAuthorizationCredentials = Depends(security_bearer),
    admin: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db)
):
    """
    Revokes the active admin session by blacklisting the token in Redis.
    """
    token = credentials.credentials
    try:
        r = redis.Redis.from_url(settings.REDIS_URL)
        r.setex(f"blacklist_token:{token}", 60 * 60 * 24 * 7, "revoked")
    except Exception as e:
        print("[Revoke Session] Redis connection error:", e)
        
    log_audit(
        db=db,
        admin_user_id=admin.id,
        action_type="REVOKE_ADMIN_SESSION",
        affected_resources="user_security"
    )
    
    return {"status": "success", "message": "Admin session revoked successfully."}

class ChangeUsernameRequest(BaseModel):
    new_username: EmailStr

@router.post("/auth/change-username")
def change_admin_username(
    payload: ChangeUsernameRequest,
    admin: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db)
):
    """
    Updates the super admin email/username.
    """
    new_email = payload.new_username.lower().strip()
    existing = db.query(User).filter(User.email == new_email).first()
    if existing and existing.id != admin.id:
        raise HTTPException(status_code=400, detail="This email/username is already in use.")
        
    old_email = admin.email
    admin.email = new_email
    db.commit()
    
    log_audit(
        db=db,
        admin_user_id=admin.id,
        action_type="ADMIN_USERNAME_CHANGE",
        target_tenant_id=admin.tenant_id,
        affected_resources="user_identity",
        old_state={"email": old_email},
        new_state={"email": new_email}
    )
    
    return {
        "status": "success",
        "message": f"Administrative username successfully updated to {new_email}"
    }

@router.post("/auth/totp/disable")
def admin_totp_disable(
    admin: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db)
):
    """
    Disables 2FA for the super admin (requires valid authenticated session with totp_verified).
    """
    admin.totp_enabled = False
    admin.totp_secret = None
    admin.recovery_codes = None
    db.commit()
    
    log_audit(
        db=db,
        admin_user_id=admin.id,
        action_type="ADMIN_TOTP_DISABLED",
        target_tenant_id=admin.tenant_id,
        affected_resources="user_security",
        new_state={"totp_enabled": False}
    )
    
    return {
        "status": "success",
        "message": "TOTP 2FA successfully disabled."
    }


# ----------------------------------------------------------------------
# TENANT MANAGEMENT ENDPOINTS
# ----------------------------------------------------------------------
@router.get("/tenants")
def get_all_tenants(admin: User = Depends(get_current_super_admin), db: Session = Depends(get_db)):
    """
    Returns all tenants including subdomain, lifecycle status, active sessions, and usage metrics.
    """
    tenants = db.query(Tenant).filter(Tenant.is_visible == True).all()
    results = []
    
    for t in tenants:
        sub = db.query(Subscription).filter(Subscription.tenant_id == t.id).first()
        sessions = db.query(WhatsAppSession).filter(WhatsAppSession.tenant_id == t.id).all()
        user_count = db.query(User).filter(User.tenant_id == t.id).count()
        
        # Monthly Message Usage
        now = datetime.now(timezone.utc)
        start_of_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        from app.models.all_models import Conversation
        message_count = db.query(Message).join(Conversation).filter(
            Conversation.tenant_id == t.id,
            Message.created_at >= start_of_month
        ).count()
        
        results.append({
            "id": str(t.id),
            "name": t.name,
            "subdomain": t.subdomain,
            "status": t.status,
            "termination_grace_period_ends": t.termination_grace_period_ends,
            "data_retention_policy": t.data_retention_policy,
            "created_at": t.created_at,
            "user_count": user_count,
            "message_usage": message_count,
            "subscription": {
                "plan_tier": sub.plan_tier if sub else "free",
                "status": sub.status if sub else "active",
                "max_bots": sub.max_bots if sub else 1,
                "max_messages": sub.max_messages_per_month if sub else 500,
                "current_period_end": sub.current_period_end if sub else None
            },
            "sessions": [{
                "id": str(s.id),
                "name": s.session_name,
                "status": s.status,
                "phone": s.phone_number
            } for s in sessions]
        })
    return results

@router.post("/tenants/{tenant_id}/suspend")
def suspend_tenant(
    tenant_id: UUID,
    admin: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db)
):
    """
    Manually suspends a tenant. Blocks their logins, disconnects active sessions, and disables subscription.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found.")
        
    if tenant.name == "System Operations" or tenant_id == admin.tenant_id:
        raise HTTPException(status_code=400, detail="Cannot suspend the administrative System Operations tenant.")
        
    old_status = tenant.status
    tenant.status = "suspended"
    
    # Deactivate users (safeguarding super admin accounts)
    users = db.query(User).filter(User.tenant_id == tenant_id, User.role != "admin").all()
    for u in users:
        u.is_active = False
        
    # Disable subscription
    sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
    if sub:
        sub.status = "suspended"
        
    db.commit()
    
    log_audit(
        db=db,
        admin_user_id=admin.id,
        action_type="SUSPEND_TENANT",
        target_tenant_id=tenant_id,
        affected_resources="tenant, users, subscription",
        old_state={"status": old_status},
        new_state={"status": "suspended"}
    )
    
    return {"status": "success", "message": f"Tenant {tenant.name} suspended successfully."}

@router.post("/tenants/{tenant_id}/reactivate")
def reactivate_tenant(
    tenant_id: UUID,
    admin: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db)
):
    """
    Manually reactivates a suspended tenant. Re-enables logins and subscriptions.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found.")
        
    if tenant.status == "TERMINATED":
        raise HTTPException(
            status_code=400,
            detail="Cannot reactivate a terminated tenant. Purge the tenant space to register anew."
        )
        
    old_status = tenant.status
    tenant.status = "active"
    
    # Reactivate users
    users = db.query(User).filter(User.tenant_id == tenant_id).all()
    for u in users:
        u.is_active = True
        
    # Reactivate subscription
    sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
    if sub:
        sub.status = "active"
        
    db.commit()
    
    log_audit(
        db=db,
        admin_user_id=admin.id,
        action_type="REACTIVATE_TENANT",
        target_tenant_id=tenant_id,
        affected_resources="tenant, users, subscription",
        old_state={"status": old_status},
        new_state={"status": "active"}
    )
    
    return {"status": "success", "message": f"Tenant {tenant.name} reactivated successfully."}


# ----------------------------------------------------------------------
# SUBSCRIPTION & BILLING CONTROLS
# ----------------------------------------------------------------------
@router.post("/tenants/{tenant_id}/change-plan")
def change_plan_tier(
    tenant_id: UUID, 
    payload: PlanChangeRequest, 
    admin: User = Depends(get_current_super_admin), 
    db: Session = Depends(get_db)
):
    """
    Allows Super Admin to extend subscriptions, grant free months, or change plans.
    """
    sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
    if not sub:
        sub = Subscription(tenant_id=tenant_id)
        db.add(sub)
        
    tier = payload.plan_tier.lower()
    from app.routers.billing import PLAN_DETAILS
    if tier not in PLAN_DETAILS:
        raise HTTPException(status_code=400, detail="Invalid subscription tier.")
        
    old_tier = sub.plan_tier
    old_expiry = sub.current_period_end
    
    plan = PLAN_DETAILS[tier]
    sub.plan_tier = tier
    sub.status = "active"
    sub.max_bots = payload.max_bots if payload.max_bots is not None else plan["max_bots"]
    sub.max_messages_per_month = payload.max_messages if payload.max_messages is not None else plan["max_messages"]
    
    # Handle expiration date extension
    now_utc = datetime.now(timezone.utc)
    base_time = sub.current_period_end if (sub.current_period_end and sub.current_period_end > now_utc) else now_utc
    sub.current_period_end = base_time + timedelta(days=payload.days)
    
    # Ensure users are reactivated
    users = db.query(User).filter(User.tenant_id == tenant_id).all()
    for u in users:
        u.is_active = True
        
    # Reactivate tenant status
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant and tenant.status in ["suspended", "expired"]:
        tenant.status = "active"
        
    db.commit()
    db.refresh(sub)
    
    log_audit(
        db=db,
        admin_user_id=admin.id,
        action_type="OVERRIDE_SUBSCRIPTION_PLAN",
        target_tenant_id=tenant_id,
        affected_resources="subscription, tenant, users",
        old_state={"plan_tier": old_tier, "expiry": old_expiry.isoformat() if old_expiry else None},
        new_state={"plan_tier": sub.plan_tier, "expiry": sub.current_period_end.isoformat(), "days_added": payload.days}
    )
    
    return {
        "status": "success", 
        "subscription": {
            "plan_tier": sub.plan_tier,
            "max_bots": sub.max_bots,
            "max_messages": sub.max_messages_per_month,
            "current_period_end": sub.current_period_end
        }
    }

@router.post("/tenants/{tenant_id}/quotas")
def override_quotas(
    tenant_id: UUID, 
    payload: QuotaOverrideRequest, 
    admin: User = Depends(get_current_super_admin), 
    db: Session = Depends(get_db)
):
    """
    Directly overrides usage quotas (bots and message limits) for a specific tenant.
    """
    sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription model not found for this tenant.")
        
    old_bots = sub.max_bots
    old_messages = sub.max_messages_per_month
    
    sub.max_bots = payload.max_bots
    sub.max_messages_per_month = payload.max_messages
    db.commit()
    db.refresh(sub)
    
    log_audit(
        db=db,
        admin_user_id=admin.id,
        action_type="OVERRIDE_QUOTAS",
        target_tenant_id=tenant_id,
        affected_resources="subscription",
        old_state={"max_bots": old_bots, "max_messages": old_messages},
        new_state={"max_bots": sub.max_bots, "max_messages": sub.max_messages_per_month}
    )
    
    return {
        "status": "success", 
        "max_bots": sub.max_bots, 
        "max_messages": sub.max_messages_per_month
    }

@router.post("/tenants/{tenant_id}/reset-usage")
def reset_usage_counters(
    tenant_id: UUID, 
    admin: User = Depends(get_current_super_admin), 
    db: Session = Depends(get_db)
):
    """
    Resets usage counters by deleting message logs registered in the current billing month.
    """
    now = datetime.now(timezone.utc)
    start_of_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    
    from app.models.all_models import Conversation
    deleted_rows = db.query(Message).filter(
        Message.conversation_id.in_(
            db.query(Conversation.id).filter(Conversation.tenant_id == tenant_id)
        ),
        Message.created_at >= start_of_month
    ).delete(synchronize_session=False)
    db.commit()
    
    log_audit(
        db=db,
        admin_user_id=admin.id,
        action_type="RESET_USAGE_COUNTERS",
        target_tenant_id=tenant_id,
        affected_resources="messages",
        new_state={"deleted_rows_count": deleted_rows}
    )
    
    return {"status": "success", "message": f"Tenant {tenant_id} counters successfully reset. cleared {deleted_rows} logs."}


# ----------------------------------------------------------------------
# SERVICE TERMINATION SYSTEM
# ----------------------------------------------------------------------
@router.post("/tenants/{tenant_id}/terminate")
async def terminate_tenant(
    tenant_id: UUID,
    payload: TerminateRequest,
    admin: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db)
):
    """
    Executes service terminations: Mode 1 (Instant lockout & disconnect) vs Mode 2 (Graceful 24h warnings).
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found.")
        
    if tenant.name == "System Operations" or tenant_id == admin.tenant_id:
        raise HTTPException(status_code=400, detail="Cannot terminate the administrative System Operations tenant.")
        
    mode = payload.mode.lower()
    if mode not in ["instant", "graceful"]:
        raise HTTPException(status_code=400, detail="Invalid mode. Specify 'instant' or 'graceful'.")
        
    old_status = tenant.status
    
    # MODE 1: INSTANT
    if mode == "instant":
        tenant.status = "TERMINATED"
        tenant.is_visible = False
        tenant.termination_grace_period_ends = None
        
        # 1. Lock user logins (safeguarding super admin accounts)
        users = db.query(User).filter(User.tenant_id == tenant_id, User.role != "admin").all()
        for u in users:
            u.is_active = False
            
        # 2. Suspend subscription
        sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
        if sub:
            sub.status = "suspended"
            
        # 3. Disconnect WhatsApp Sessions via Baileys Engine
        sessions = db.query(WhatsAppSession).filter(WhatsAppSession.tenant_id == tenant_id).all()
        async with httpx.AsyncClient() as client:
            for s in sessions:
                try:
                    s.status = "disconnected"
                    url = f"{settings.WHATSAPP_ENGINE_URL}/sessions/{s.id}"
                    await client.delete(url, timeout=5.0)
                except Exception as e:
                    print(f"[Instant Termination] Session disconnect failed for {s.id}: {e}")
                    
        # 4. Trigger Secure Transactional Purge immediately if policy is Delete Mode
        if tenant.data_retention_policy == "delete":
            # Scan and delete physical PDF/text uploads from local storage first
            kb_docs = db.query(KBDocument).join(KnowledgeBase).filter(KnowledgeBase.tenant_id == tenant_id).all()
            for doc in kb_docs:
                if doc.file_path and os.path.exists(doc.file_path):
                    try:
                        os.remove(doc.file_path)
                    except Exception as f_err:
                        print(f"[Instant Purge] File delete error {doc.file_path}: {f_err}")
            
            # ORM Cascade deletes users, sessions, chatbots, conversations, campaigns, uploads, vectors
            db.delete(tenant)
            db.commit()
            
            log_audit(
                db=db,
                admin_user_id=admin.id,
                action_type="INSTANT_TERMINATION_WITH_PURGE",
                target_tenant_id=tenant_id,
                affected_resources="tenant, data",
                old_state={"status": old_status},
                new_state={"status": "PURGED"}
            )
            return {"status": "success", "message": f"Tenant {tenant_id} terminated and all vector files purged."}
            
        db.commit()
        log_audit(
            db=db,
            admin_user_id=admin.id,
            action_type="INSTANT_TERMINATION",
            target_tenant_id=tenant_id,
            affected_resources="tenant, users, sessions",
            old_state={"status": old_status},
            new_state={"status": "TERMINATED"}
        )
        return {"status": "success", "message": f"Tenant {tenant.name} has been instantly terminated."}
        
    # MODE 2: GRACEFUL
    else:
        tenant.status = "PENDING TERMINATION"
        grace_end = datetime.now(timezone.utc) + timedelta(hours=24)
        tenant.termination_grace_period_ends = grace_end
        db.commit()
        
        # Broadcast Warning alerts to active dashboard users via WebSocket
        await websocket_manager.publish_event(str(tenant_id), "termination_warning", {
            "message": "URGENT WARNING: Your account is marked PENDING TERMINATION. You have 24 HOURS to export conversations and settle billing before absolute deletion.",
            "grace_period_ends": grace_end.isoformat()
        })
        
        log_audit(
            db=db,
            admin_user_id=admin.id,
            action_type="GRACEFUL_TERMINATION_SCHEDULED",
            target_tenant_id=tenant_id,
            affected_resources="tenant",
            old_state={"status": old_status},
            new_state={"status": "PENDING TERMINATION", "grace_period_ends": grace_end.isoformat()}
        )
        return {
            "status": "success",
            "message": f"Tenant {tenant.name} scheduled for graceful termination. 24h warning broadcasted.",
            "grace_period_ends": grace_end
        }

@router.post("/tenants/{tenant_id}/retention-policy")
def set_retention_policy(
    tenant_id: UUID,
    payload: RetentionPolicyRequest,
    admin: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db)
):
    """
    Sets data retention policy: 'archive' (keeps data permanently) vs 'delete' (wipes vectors/conversations on purge).
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found.")
        
    if tenant.name == "System Operations" or tenant_id == admin.tenant_id:
        raise HTTPException(status_code=400, detail="Cannot modify retention policy for the administrative System Operations tenant.")
        
    policy = payload.policy.lower()
    if policy not in ["archive", "delete"]:
        raise HTTPException(status_code=400, detail="Invalid policy. Must be 'archive' or 'delete'.")
        
    old_policy = tenant.data_retention_policy
    tenant.data_retention_policy = policy
    db.commit()
    
    log_audit(
        db=db,
        admin_user_id=admin.id,
        action_type="CHANGE_RETENTION_POLICY",
        target_tenant_id=tenant_id,
        affected_resources="tenant",
        old_state={"data_retention_policy": old_policy},
        new_state={"data_retention_policy": policy}
    )
    
    return {"status": "success", "message": f"Data retention policy set to {policy} successfully."}

@router.delete("/tenants/{tenant_id}/purge")
def manual_purge_tenant(
    tenant_id: UUID,
    admin: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db)
):
    """
    Executes secure transactional hard delete purging all conversations, uploads, vectors, and sessions.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found.")
        
    if tenant.name == "System Operations" or tenant_id == admin.tenant_id:
        raise HTTPException(status_code=400, detail="Cannot purge the administrative System Operations tenant.")
        
    if tenant.data_retention_policy != "delete" and tenant.status != "TERMINATED":
        raise HTTPException(status_code=400, detail="Cannot purge. Tenant retention policy is set to 'archive'.")
        
    # Delete uploaded files first
    kb_docs = db.query(KBDocument).join(KnowledgeBase).filter(KnowledgeBase.tenant_id == tenant_id).all()
    for doc in kb_docs:
        if doc.file_path and os.path.exists(doc.file_path):
            try:
                os.remove(doc.file_path)
            except Exception as f_err:
                print(f"[Purge] File delete error: {f_err}")
                
    tenant_name = tenant.name
    tenant_subdomain = tenant.subdomain
    tenant_status = tenant.status

    # Log audit first to preserve it (target_tenant_id is set to None to prevent cascade deletion and FK violation)
    log_audit(
        db=db,
        admin_user_id=admin.id,
        action_type="MANUAL_HARD_PURGE",
        target_tenant_id=None,
        affected_resources=f"tenant:{tenant_id}:{tenant_name}, database_tables, files",
        old_state={"name": tenant_name, "subdomain": tenant_subdomain, "status": tenant_status},
        new_state={"status": "PURGED"}
    )

    # ORM Cascade Purge
    db.delete(tenant)
    db.commit()
    
    return {"status": "success", "message": f"Tenant {tenant_id} and all child data records deleted transactionally."}

@router.post("/tenants/{tenant_id}/revoke-sessions")
async def force_revoke_tenant_sessions(
    tenant_id: UUID,
    admin: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db)
):
    """
    Forces instant WhatsApp disconnection across all linked phone numbers of a tenant.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found.")
        
    if tenant.name == "System Operations" or tenant_id == admin.tenant_id:
        raise HTTPException(status_code=400, detail="Cannot disconnect sessions for the administrative System Operations tenant.")
        
    sessions = db.query(WhatsAppSession).filter(WhatsAppSession.tenant_id == tenant_id).all()
    async with httpx.AsyncClient() as client:
        for s in sessions:
            try:
                s.status = "disconnected"
                url = f"{settings.WHATSAPP_ENGINE_URL}/sessions/{s.id}"
                await client.delete(url, timeout=5.0)
            except Exception as e:
                print(f"[Admin Revoke] Session disconnect failed: {e}")
                
    db.commit()
    
    log_audit(
        db=db,
        admin_user_id=admin.id,
        action_type="REVOKE_TENANT_WHATSAPP_SESSIONS",
        target_tenant_id=tenant_id,
        affected_resources="whatsapp_sessions"
    )
    
    return {"status": "success", "message": "All WhatsApp engine sessions disconnected."}

@router.post("/tenants/{tenant_id}/force-logout")
def force_logout_users(
    tenant_id: UUID,
    admin: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db)
):
    """
    Locks logins for all members/owners of a tenant.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found.")
    if tenant.name == "System Operations" or tenant_id == admin.tenant_id:
        raise HTTPException(status_code=400, detail="Cannot force logout users on the administrative System Operations tenant.")
        
    users = db.query(User).filter(User.tenant_id == tenant_id, User.role != "admin").all()
    for u in users:
        u.is_active = False
    db.commit()
    
    log_audit(
        db=db,
        admin_user_id=admin.id,
        action_type="FORCE_LOGOUT_TENANT_USERS",
        target_tenant_id=tenant_id,
        affected_resources="users_is_active"
    )
    
    return {"status": "success", "message": "All tenant users successfully logged out and accounts locked."}


@router.post("/tenants/{tenant_id}/grant-access")
def grant_tenant_access(
    tenant_id: UUID,
    admin: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db)
):
    """
    Grants access (is_active = True) for all users associated with a tenant.
    """
    users = db.query(User).filter(User.tenant_id == tenant_id).all()
    for u in users:
        u.is_active = True
    db.commit()
    
    log_audit(
        db=db,
        admin_user_id=admin.id,
        action_type="GRANT_TENANT_ACCESS",
        target_tenant_id=tenant_id,
        affected_resources="users_is_active",
        new_state={"is_active": True}
    )
    return {"status": "success", "message": "Access successfully granted to all tenant users."}


@router.post("/tenants/{tenant_id}/revoke-access")
def revoke_tenant_access(
    tenant_id: UUID,
    admin: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db)
):
    """
    Locks logins (is_active = False) for all users associated with a tenant.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found.")
    if tenant.name == "System Operations" or tenant_id == admin.tenant_id:
        raise HTTPException(status_code=400, detail="Cannot revoke access for the administrative System Operations tenant.")
        
    users = db.query(User).filter(User.tenant_id == tenant_id, User.role != "admin").all()
    for u in users:
        u.is_active = False
    db.commit()
    
    log_audit(
        db=db,
        admin_user_id=admin.id,
        action_type="REVOKE_TENANT_ACCESS",
        target_tenant_id=tenant_id,
        affected_resources="users_is_active",
        new_state={"is_active": False}
    )
    return {"status": "success", "message": "Access successfully revoked for all tenant users."}


# ----------------------------------------------------------------------
# OBSERVABILITY & HEALTH MONITORS
# ----------------------------------------------------------------------
@router.get("/system-health")
async def get_system_health(admin: User = Depends(get_current_super_admin), db: Session = Depends(get_db)):
    """
    Monitors host system resources and service statuses (Postgres, Redis, Ollama AI, Node Engine, WS sockets).
    """
    import psutil
    
    # 0. Emergency Lock state check
    emergency_system_lock = False
    try:
        r = redis.Redis.from_url(settings.REDIS_URL)
        emergency_system_lock = (r.get("emergency_system_lock") == b"true")
    except Exception as e:
        print("[System Health] Redis emergency lock check error:", e)
        
    # 1. PostgreSQL DB Status
    db_status = "online"
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = "offline"
        print("[System Health] Postgres connection error:", e)
        
    # 2. Redis Cache Status
    redis_status = "online"
    redis_ping_ms = 0
    try:
        r = redis.Redis.from_url(settings.REDIS_URL)
        start = time.time()
        r.ping()
        redis_ping_ms = int((time.time() - start) * 1000)
    except Exception as e:
        redis_status = "offline"
        print("[System Health] Redis connection error:", e)
        
    # 3. WhatsApp Node Engine Status
    whatsapp_engine_status = "offline"
    active_sessions = 0
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(f"{settings.WHATSAPP_ENGINE_URL}/health", timeout=3.0)
            if res.status_code == 200:
                data = res.json()
                whatsapp_engine_status = data.get("status", "healthy")
                active_sessions = data.get("activeSessions", 0)
    except Exception as e:
        print("[System Health] WhatsApp engine connection error:", e)
        
    # 4. Ollama AI Runtime status
    ai_status = "online"
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(f"{settings.OLLAMA_HOST}/", timeout=3.0)
            if res.status_code != 200:
                ai_status = "degraded"
    except Exception as e:
        ai_status = "offline"
        print("[System Health] Ollama AI connection error:", e)
        
    # 5. WebSockets Realtime status
    active_ws_tenants = len(websocket_manager.active_connections)
    active_ws_sockets = sum(len(conns) for conns in websocket_manager.active_connections.values())
    
    # 6. Celery Worker Queue status
    celery_status = "offline"
    celery_queue_size = 0
    try:
        r = redis.Redis.from_url(settings.REDIS_URL)
        celery_queue_size = r.llen("celery")
        
        from worker.celery_app import celery
        inspect = celery.control.inspect(timeout=1.0)
        active_workers = inspect.ping()
        if active_workers:
            celery_status = "online"
    except Exception as e:
        print("[System Health] Celery active workers check error:", e)
        
    return {
        "system": {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "ram_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage('/').percent
        },
        "services": {
            "postgres": db_status,
            "redis": redis_status,
            "redis_latency_ms": redis_ping_ms,
            "whatsapp_engine": whatsapp_engine_status,
            "whatsapp_active_sessions": active_sessions,
            "ai_runtime": ai_status,
            "websockets": {
                "status": "online" if active_ws_sockets > 0 or active_ws_tenants > 0 else "degraded",
                "active_tenants": active_ws_tenants,
                "active_connections": active_ws_sockets
            },
            "celery_workers": {
                "status": celery_status,
                "queue_size": celery_queue_size
            }
        },
        "emergency_system_lock": emergency_system_lock
    }

@router.get("/monitoring")
def monitor_system_metrics(admin: User = Depends(get_current_super_admin), db: Session = Depends(get_db)):
    """
    Displays core performance violations, IP bans, failed payments, and queue structures.
    """
    # 1. Delivery failures
    failed_messages = db.query(Message).filter(Message.status == "failed").count()
    failed_campaigns = db.query(CampaignLog).filter(CampaignLog.status == "failed").count()
    
    # 2. Redis queue states
    queue_sizes = {}
    celery_size = 0
    try:
        r = redis.Redis.from_url(settings.REDIS_URL)
        queue_keys = r.keys("whatsapp_queue_*")
        queue_sizes = {key.decode(): r.llen(key) for key in queue_keys}
        celery_size = r.llen("celery")
    except Exception as e:
        print("[Monitoring] Redis connection error:", e)

    # 3. Failed payment capture logs
    failed_payments_count = db.query(PaymentTransaction).filter(PaymentTransaction.status == "failed").count()
    failed_payments = db.query(PaymentTransaction).filter(PaymentTransaction.status == "failed").order_by(PaymentTransaction.created_at.desc()).limit(10).all()
    
    # 4. Security violation bands
    banned_ips = []
    violations = 0
    try:
        r = redis.Redis.from_url(settings.REDIS_URL)
        ban_keys = r.keys("ip_ban:*")
        banned_ips = [key.decode().split(":")[-1] for key in ban_keys]
        violation_keys = r.keys("rate_limit_violation:*")
        violations = sum(int(r.get(k) or 0) for k in violation_keys)
    except Exception:
        pass
        
    active_ws_tenants = len(websocket_manager.active_connections)
    active_ws_sockets = sum(len(conns) for conns in websocket_manager.active_connections.values())
    
    return {
        "delivery_failures": {
            "failed_messages": failed_messages,
            "failed_campaign_logs": failed_campaigns
        },
        "redis_queues": {
            "whatsapp_queues": queue_sizes,
            "celery_queue_size": celery_size
        },
        "websocket_health": {
            "active_tenants": active_ws_tenants,
            "active_connections": active_ws_sockets
        },
        "failed_payments": {
            "count": failed_payments_count,
            "recent": [{
                "id": str(p.id),
                "order_id": p.order_id,
                "amount": p.amount,
                "plan_tier": p.plan_tier,
                "created_at": p.created_at
            } for p in failed_payments]
        },
        "security_violations": {
            "banned_ips_count": len(banned_ips),
            "banned_ips": banned_ips,
            "active_rate_limit_violations": violations
        }
    }


# ----------------------------------------------------------------------
# AUDIT LOGS & SECURITY CENTERS
# ----------------------------------------------------------------------
@router.get("/audit-logs")
def get_audit_logs(
    limit: int = 100,
    offset: int = 0,
    admin: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db)
):
    """
    Returns permanently saved administrative audit log histories.
    """
    logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()
    results = []
    
    for l in logs:
        tenant_name = None
        tenant_subdomain = None
        if l.target_tenant_id:
            t = db.query(Tenant).filter(Tenant.id == l.target_tenant_id).first()
            if t:
                tenant_name = t.name
                tenant_subdomain = t.subdomain
                
        admin_email = "System / Lockout"
        if l.admin_user_id:
            u = db.query(User).filter(User.id == l.admin_user_id).first()
            if u:
                admin_email = u.email
                
        results.append({
            "id": str(l.id),
            "admin_user_id": str(l.admin_user_id) if l.admin_user_id else None,
            "admin_email": admin_email,
            "action_type": l.action_type,
            "target_tenant_id": str(l.target_tenant_id) if l.target_tenant_id else None,
            "target_tenant_name": tenant_name,
            "target_tenant_subdomain": tenant_subdomain,
            "affected_resources": l.affected_resources,
            "old_state": l.old_state,
            "new_state": l.new_state,
            "created_at": l.created_at
        })
    return results

@router.get("/security-center")
def get_security_center_metrics(
    admin: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db)
):
    """
    Security control center statistics tracking lockouts, rate limit violations, and system access.
    """
    failed_logins = db.query(AuditLog).filter(AuditLog.action_type == "FAILED_ADMIN_LOGIN").count()
    locked_accounts = db.query(AuditLog).filter(AuditLog.action_type == "ACCOUNT_LOCKED").count()
    totp_challenges = db.query(AuditLog).filter(AuditLog.action_type == "ADMIN_LOGIN_TOTP_CHALLENGE").count()
    
    recent_events = db.query(AuditLog).filter(
        AuditLog.action_type.in_([
            "FAILED_ADMIN_LOGIN",
            "ACCOUNT_LOCKED",
            "ADMIN_TOTP_ENABLED",
            "ADMIN_PASSWORD_ROTATE",
            "REVOKE_ADMIN_SESSION"
        ])
    ).order_by(AuditLog.created_at.desc()).limit(20).all()
    
    events = []
    for l in recent_events:
        admin_email = "System"
        if l.admin_user_id:
            u = db.query(User).filter(User.id == l.admin_user_id).first()
            if u:
                admin_email = u.email
        events.append({
            "id": str(l.id),
            "admin_email": admin_email,
            "action": l.action_type,
            "state": l.new_state,
            "created_at": l.created_at
        })
        
    banned_ips = []
    try:
        r = redis.Redis.from_url(settings.REDIS_URL)
        ban_keys = r.keys("ip_ban:*")
        banned_ips = [k.decode().split(":")[-1] for k in ban_keys]
    except Exception:
        pass
        
    return {
        "metrics": {
            "failed_logins_count": failed_logins,
            "locked_accounts_count": locked_accounts,
            "totp_challenges_count": totp_challenges,
            "banned_ips_count": len(banned_ips)
        },
        "banned_ips": banned_ips,
        "recent_security_events": events
    }


# ----------------------------------------------------------------------
# SYSTEM MAINTENANCE & MANUAL CRON DIALS
# ----------------------------------------------------------------------
@router.post("/broadcast-maintenance")
async def broadcast_maintenance_alert(payload: MaintenanceBroadcastRequest, admin: User = Depends(get_current_super_admin)):
    """
    Broadcasts maintenance alerts over open WebSockets to all connected client dashboards.
    """
    await websocket_manager.broadcast_global_event("maintenance_alert", {
        "message": payload.message,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    return {"status": "success", "message": "Global maintenance warning successfully broadcasted."}

@router.post("/system/trigger-cron")
def trigger_periodic_tasks(
    admin: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db)
):
    """
    Forces instant evaluation of periodic administrative tasks (e.g. grace period, subscription reminders).
    """
    try:
        from worker.celery_app import celery
        celery.send_task("worker.tasks.check_graceful_terminations_task")
        celery.send_task("worker.tasks.check_subscription_reminders_task")
        celery.send_task("worker.tasks.process_autopay_renewals_task")
        
        log_audit(
            db=db,
            admin_user_id=admin.id,
            action_type="MANUAL_CRON_TRIGGER",
            affected_resources="celery_workers"
        )
        return {"status": "success", "message": "All administrative daemon triggers successfully queued in background workers."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed triggering periodic jobs: {e}")

@router.get("/payments")
def get_payments_history(admin: User = Depends(get_current_super_admin), db: Session = Depends(get_db)):
    """
    Retrieves global payment transaction invoice history.
    """
    return db.query(PaymentTransaction).order_by(PaymentTransaction.created_at.desc()).all()

@router.get("/usage")
def get_usage_metrics(admin: User = Depends(get_current_super_admin), db: Session = Depends(get_db)):
    """
    Observability telemetry showing total and outbound messages, tokens used, and avg latency.
    """
    total_messages = db.query(Message).count()
    outbound_messages = db.query(Message).filter(Message.direction == "outbound").count()
    
    token_stats = db.query(
        func.sum(AIUsageLog.tokens_used).label("total_tokens"),
        func.avg(AIUsageLog.latency_ms).label("avg_latency")
    ).first()
    
    tenant_usage = db.query(
        Message.sender_type,
        func.count(Message.id).label("count")
    ).group_by(Message.sender_type).all()
    
    return {
        "global_usage": {
            "total_messages": total_messages,
            "outbound_messages": outbound_messages,
            "total_ai_tokens": token_stats.total_tokens if token_stats and token_stats.total_tokens else 0,
            "avg_ai_latency_ms": float(token_stats.avg_latency) if token_stats and token_stats.avg_latency else 0.0
        },
        "message_distribution": {row[0]: row[1] for row in tenant_usage}
    }


# ----------------------------------------------------------------------
# STORAGE & EMERGENCY LOCK UTILITIES
# ----------------------------------------------------------------------
def get_dir_size(path: str) -> int:
    total = 0
    if not os.path.exists(path):
        return 0
    try:
        if os.path.isfile(path):
            return os.path.getsize(path)
        for root, dirs, files in os.walk(path):
            for f in files:
                fp = os.path.join(root, f)
                if os.path.exists(fp):
                    total += os.path.getsize(fp)
    except Exception as e:
        print(f"[Storage Report] Error walking {path}: {e}")
    return total


def query_docker_socket(path: str) -> dict:
    import socket
    import json
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect("/var/run/docker.sock")
        req = f"GET {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n"
        s.sendall(req.encode('utf-8'))
        response = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            response += chunk
        s.close()
        parts = response.split(b"\r\n\r\n", 1)
        if len(parts) < 2:
            return {}
        body = parts[1]
        if b"Transfer-Encoding: chunked" in parts[0]:
            decoded_body = b""
            idx = 0
            while idx < len(body):
                line_end = body.find(b"\r\n", idx)
                if line_end == -1:
                    break
                chunk_len_str = body[idx:line_end]
                try:
                    chunk_len = int(chunk_len_str, 16)
                except ValueError:
                    break
                if chunk_len == 0:
                    break
                idx = line_end + 2
                decoded_body += body[idx:idx+chunk_len]
                idx += chunk_len + 2
            body = decoded_body
        return json.loads(body.decode('utf-8'))
    except Exception as e:
        print("[Storage Report] Docker socket query failed:", e)
        return {}


@router.get("/storage-report")
def get_storage_report(
    admin: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db)
):
    """
    Computes VM and Docker storage footprint recursively.
    """
    import psutil
    
    # 1. Disk usage via psutil
    disk = psutil.disk_usage('/')
    total_space = disk.total
    used_space = disk.used
    free_space = disk.free
    
    # 2. Database size
    db_size = 0
    try:
        res = db.execute(text("SELECT pg_database_size(current_database())"))
        db_size = res.scalar() or 0
    except Exception as e:
        print("[Storage Report] DB Size query failed:", e)
        
    # 3. Redis Memory Usage
    redis_size = 0
    try:
        r = redis.Redis.from_url(settings.REDIS_URL)
        info = r.info("memory")
        redis_size = info.get("used_memory") or 0
    except Exception as e:
        print("[Storage Report] Redis Size query failed:", e)
        
    # 4. Query Docker Socket for system usage
    docker_images_size = 0
    docker_volumes_size = 0
    docker_build_cache_size = 0
    docker_containers_rw_size = 0
    
    docker_data = query_docker_socket("/system/df")
    if docker_data:
        docker_images_size = sum(img.get("Size", 0) for img in docker_data.get("Images", []))
        docker_containers_rw_size = sum(c.get("SizeRw", 0) for c in docker_data.get("Containers", []))
        
        for v in docker_data.get("Volumes", []):
            usage = v.get("UsageData")
            if usage and usage != -1:
                docker_volumes_size += usage.get("Size", 0)
                
        bc = docker_data.get("BuildCache")
        if isinstance(bc, list):
            docker_build_cache_size = sum(item.get("Size", 0) for item in bc)
        elif isinstance(bc, dict):
            docker_build_cache_size = bc.get("TotalSize", 0)
            
    # 5. Directory scanning
    uploads_size = get_dir_size("/app/uploads")
    project_files_size = get_dir_size("/app/project-files")
    
    # Backups folders
    backups_size = get_dir_size("/app/project-files/backups") + get_dir_size("/app/project-files/project-brain/backups")
    
    # Temporary folders
    tmp_size = get_dir_size("/tmp")
    
    # Container logs
    container_logs_size = get_dir_size("/app/docker-logs")
    
    return {
        "total_storage": total_space,
        "used_storage": used_space,
        "free_storage": free_space,
        "docker_images_size": docker_images_size,
        "docker_volume_size": docker_volumes_size,
        "docker_cache_size": docker_build_cache_size,
        "builder_cache_size": docker_build_cache_size,
        "container_logs_size": container_logs_size,
        "database_size": db_size,
        "redis_size": redis_size,
        "project_files_size": project_files_size,
        "uploads_size": uploads_size,
        "backups_size": backups_size,
        "temporary_files_size": tmp_size
    }


@router.post("/system/emergency-lock")
def emergency_lock_system(
    admin: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db)
):
    """
    Emergency locks the entire system, preventing all customer logins and API access.
    """
    r = redis.Redis.from_url(settings.REDIS_URL)
    r.set("emergency_system_lock", "true")
    
    log_audit(
        db=db,
        admin_user_id=admin.id,
        action_type="EMERGENCY_SYSTEM_LOCK",
        affected_resources="global_system_access",
        new_state={"emergency_system_lock": "true"}
    )
    return {"status": "success", "message": "Global system emergency lockdown has been ACTIVATED. All tenant traffic blocked."}


@router.post("/system/emergency-unlock")
def emergency_unlock_system(
    admin: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db)
):
    """
    Emergency unlocks the system, restoring normal operations.
    """
    r = redis.Redis.from_url(settings.REDIS_URL)
    r.delete("emergency_system_lock")
    
    log_audit(
        db=db,
        admin_user_id=admin.id,
        action_type="EMERGENCY_SYSTEM_UNLOCK",
        affected_resources="global_system_access",
        new_state={"emergency_system_lock": "false"}
    )
    return {"status": "success", "message": "Global system emergency lockdown has been DEACTIVATED. Normal traffic restored."}


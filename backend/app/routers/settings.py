from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from uuid import UUID
from datetime import datetime

from app.database import get_db
from app.auth.service import get_current_user
from app.models.all_models import User, Tenant, WhatsAppSession, Message, Conversation, TenantSetting
from app.core.security import verify_password, get_password_hash

router = APIRouter(prefix="/settings", tags=["User Settings"])


# ── Pydantic Schemas ─────────────────────────────────────────────────────────

class ProfileResponse(BaseModel):
    id: UUID
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: str
    tenant_name: str
    created_at: datetime

    class Config:
        from_attributes = True


class TenantSettingResponse(BaseModel):
    reply_delay: int
    simulate_typing_delay: int
    campaign_send_interval: int
    queue_speed: str
    throttle_rate: int
    send_mode: str
    default_country_code: str
    llm_model: str
    tone: str
    personality: str
    business_style: str
    enable_2fa: bool
    session_timeout: int

    class Config:
        from_attributes = True

class TenantSettingUpdate(BaseModel):
    reply_delay: Optional[int] = None
    simulate_typing_delay: Optional[int] = None
    campaign_send_interval: Optional[int] = None
    queue_speed: Optional[str] = None
    throttle_rate: Optional[int] = None
    send_mode: Optional[str] = None
    default_country_code: Optional[str] = None
    llm_model: Optional[str] = None
    tone: Optional[str] = None
    personality: Optional[str] = None
    business_style: Optional[str] = None
    enable_2fa: Optional[bool] = None
    session_timeout: Optional[int] = None



class ProfileUpdateRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class SessionResponse(BaseModel):
    id: UUID
    session_name: str
    phone_number: Optional[str] = None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class ActivityLogEntry(BaseModel):
    id: UUID
    conversation_id: UUID
    direction: str
    sender_type: str
    content: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/profile", response_model=ProfileResponse)
def get_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns the authenticated user's profile including tenant name."""
    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    tenant_name = tenant.name if tenant else "Unknown"

    return ProfileResponse(
        id=current_user.id,
        email=current_user.email,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        role=current_user.role,
        tenant_name=tenant_name,
        created_at=current_user.created_at,
    )


@router.patch("/profile", response_model=ProfileResponse)
def update_profile(
    payload: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Updates the user's first name, last name, and/or email address."""
    if payload.email and payload.email != current_user.email:
        existing = db.query(User).filter(
            User.email == payload.email,
            User.id != current_user.id,
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This email address is already in use by another account.",
            )
        current_user.email = payload.email

    if payload.first_name is not None:
        current_user.first_name = payload.first_name

    if payload.last_name is not None:
        current_user.last_name = payload.last_name

    db.commit()
    db.refresh(current_user)

    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    tenant_name = tenant.name if tenant else "Unknown"

    return ProfileResponse(
        id=current_user.id,
        email=current_user.email,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        role=current_user.role,
        tenant_name=tenant_name,
        created_at=current_user.created_at,
    )


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Changes the user's password after verifying the current one."""
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )

    if len(payload.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 8 characters long.",
        )

    current_user.password_hash = get_password_hash(payload.new_password)
    db.commit()

    return {"message": "Password updated successfully."}


@router.get("/sessions", response_model=List[SessionResponse])
def list_tenant_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns all active WhatsApp sessions for the user's tenant."""
    sessions = (
        db.query(WhatsAppSession)
        .filter(WhatsAppSession.tenant_id == current_user.tenant_id)
        .order_by(WhatsAppSession.created_at.desc())
        .all()
    )
    return sessions


@router.get("/activity-log", response_model=List[ActivityLogEntry])
def get_activity_log(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns the last 50 messages for the tenant, showing recent activity."""
    messages = (
        db.query(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .filter(Conversation.tenant_id == current_user.tenant_id)
        .order_by(Message.created_at.desc())
        .limit(50)
        .all()
    )
    return messages


@router.delete("/account")
def delete_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Soft-deletes the user account by setting is_active to False."""
    current_user.is_active = False
    db.commit()

    return {"message": "Account has been deactivated successfully."}


@router.get("/delivery-performance", response_model=TenantSettingResponse)
def get_delivery_performance_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieves or creates delivery and performance settings for the tenant."""
    settings_row = db.query(TenantSetting).filter(TenantSetting.tenant_id == current_user.tenant_id).first()
    if not settings_row:
        settings_row = TenantSetting(tenant_id=current_user.tenant_id)
        db.add(settings_row)
        db.commit()
        db.refresh(settings_row)
    return settings_row


@router.patch("/delivery-performance", response_model=TenantSettingResponse)
def update_delivery_performance_settings(
    payload: TenantSettingUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Updates delivery and performance settings for the tenant."""
    settings_row = db.query(TenantSetting).filter(TenantSetting.tenant_id == current_user.tenant_id).first()
    if not settings_row:
        settings_row = TenantSetting(tenant_id=current_user.tenant_id)
        db.add(settings_row)
        db.commit()
        db.refresh(settings_row)
        
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(settings_row, k, v)
        
    db.commit()
    db.refresh(settings_row)
    return settings_row


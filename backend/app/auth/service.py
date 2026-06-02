from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.models.all_models import User, Tenant

security_bearer = HTTPBearer()

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_bearer),
    db: Session = Depends(get_db)
) -> User:
    """
    Decodes the Bearer JWT token, validates signatures, and fetches active user context.
    Acts as the entry barrier for all restricted SaaS endpoints.
    """
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate authorization credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
        
    # Check global emergency system lock
    try:
        import redis
        r = redis.Redis.from_url(settings.REDIS_URL)
        if r.get("emergency_system_lock") == b"true" and user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="System is under emergency lockdown. Please try again later."
            )
    except HTTPException as he:
        raise he
    except Exception as re_err:
        print("[Auth] Emergency lock check failed:", re_err)
        
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is suspended."
        )
        
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    if tenant and tenant.status in ["suspended", "TERMINATED"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Tenant space is {tenant.status}."
        )
        
    return user

def get_current_tenant_id(
    current_user: User = Depends(get_current_user)
) -> str:
    """
    Helper dependency yielding the active tenant_id context for strict data scoping
    """
    return current_user.tenant_id

def get_current_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Dependency yielding the current user context, asserting that the user role is 'admin'
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requires Super Admin permissions."
        )
    return current_user

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.all_models import Tenant, User, Subscription
from app.schemas.all_schemas import UserRegister, UserLogin, Token
from app.core.security import verify_password, get_password_hash, create_access_token
from datetime import timedelta

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=Token)
def register_user(payload: UserRegister, db: Session = Depends(get_db)):
    """
    Registers a new tenant organization and primary administrator.
    Ensures absolute data isolation by allocating dedicated Tenant space.
    """
    # 1. Check if email is already taken
    existing_user = db.query(User).filter(User.email == payload.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email address is already registered."
        )

    # 2. Check if subdomain is already taken
    if payload.subdomain:
        existing_tenant = db.query(Tenant).filter(Tenant.subdomain == payload.subdomain).first()
        if existing_tenant:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Subdomain is already taken."
            )


    # 2. Create the Organization Tenant space
    new_tenant = Tenant(
        name=payload.tenant_name,
        subdomain=payload.subdomain
    )
    db.add(new_tenant)
    db.commit()
    db.refresh(new_tenant)

    # 3. Create the administrator account
    hashed_pwd = get_password_hash(payload.password)
    new_user = User(
        tenant_id=new_tenant.id,
        email=payload.email,
        password_hash=hashed_pwd,
        first_name=payload.first_name,
        last_name=payload.last_name,
        role="owner"
    )
    db.add(new_user)
    
    # 4. Initialize free quota subscription tier
    new_sub = Subscription(
        tenant_id=new_tenant.id,
        plan_tier="free",
        status="active"
    )
    db.add(new_sub)
    
    db.commit()
    db.refresh(new_user)

    # 5. Issue secure Access token containing user identification
    token = create_access_token(subject=str(new_user.id))
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": new_user.role,
        "tenant_id": new_tenant.id
    }

@router.post("/login", response_model=Token)
def login_user(payload: UserLogin, db: Session = Depends(get_db)):
    """
    Validates user credentials and generates secure JWT access tokens.
    """
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password credentials."
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated."
        )

    token = create_access_token(subject=str(user.id))
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role,
        "tenant_id": user.tenant_id
    }

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.service import get_current_tenant_id
from app.models.all_models import Subscription, PaymentTransaction
from app.config import settings
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime, timedelta, timezone
import razorpay
import razorpay.errors

router = APIRouter(prefix="/billing", tags=["Billing & Subscriptions"])
payments_router = APIRouter(prefix="/payments", tags=["Payments & Webhooks"])

# Price configuration (in INR, represented in Paise: 1 INR = 100 Paise)
PLAN_DETAILS = {
    "free": {"amount": 0, "max_bots": 1, "max_messages": 500},
    "starter": {"amount": 99900, "max_bots": 2, "max_messages": 5000},
    "pro": {"amount": 299900, "max_bots": 5, "max_messages": 50000},
    "agency": {"amount": 999900, "max_bots": 20, "max_messages": 1000000}
}

class CreateOrderRequest(BaseModel):
    plan_tier: str

class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    plan_tier: str

@router.get("/plan")
def get_current_plan(tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """
    Retrieves the active subscription plan and limits for the tenant.
    """
    sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
    if not sub:
        # Default to Free tier if no record exists
        sub = Subscription(
            tenant_id=tenant_id,
            plan_tier="free",
            status="active",
            max_bots=PLAN_DETAILS["free"]["max_bots"],
            max_messages_per_month=PLAN_DETAILS["free"]["max_messages"]
        )
        db.add(sub)
        db.commit()
        db.refresh(sub)
        
    return {
        "plan_tier": sub.plan_tier,
        "status": sub.status,
        "max_bots": sub.max_bots,
        "max_messages_per_month": sub.max_messages_per_month,
        "current_period_end": sub.current_period_end,
        "created_at": sub.created_at
    }

@router.post("/create-order")
async def create_razorpay_order(
    payload: CreateOrderRequest,
    tenant_id: UUID = Depends(get_current_tenant_id),
    db: Session = Depends(get_db)
):
    """
    Creates a new Razorpay Order for upgrading plan using the official SDK.
    """
    tier = payload.plan_tier.lower()
    if tier not in PLAN_DETAILS or tier == "free":
        raise HTTPException(status_code=400, detail="Invalid plan tier specified.")

    plan = PLAN_DETAILS[tier]
    amount = plan["amount"]

    # Verify client authentication and initialization parameters
    key_id = settings.RAZORPAY_KEY_ID
    key_secret = settings.RAZORPAY_KEY_SECRET

    print(f"[Razorpay] Initializing Client in mode '{settings.PAYMENT_MODE}'. Auth Key: {key_id[:8]}...")

    try:
        client = razorpay.Client(auth=(key_id, key_secret))
        order_data = client.order.create(data={
            "amount": amount,
            "currency": "INR",
            "receipt": f"receipt_{str(tenant_id)[:20]}",
            "notes": {
                "tenant_id": str(tenant_id),
                "plan_tier": tier,
                "payment_mode": settings.PAYMENT_MODE
            }
        })
        
        # Save transaction record as created
        tx = PaymentTransaction(
            tenant_id=tenant_id,
            order_id=order_data["id"],
            amount=amount,
            status="created",
            plan_tier=tier
        )
        db.add(tx)
        db.commit()
        
        print(f"[Razorpay] Order created successfully: {order_data['id']} for tenant {tenant_id}")
        return {
            "razorpay_order_id": order_data["id"],
            "amount": order_data["amount"],
            "currency": order_data["currency"],
            "razorpay_key_id": key_id
        }
    except Exception as e:
        error_msg = str(e)
        print(f"[Razorpay SDK Error] Failed to create order: {error_msg}")
        
        # Format user-friendly error message based on common Razorpay failure signatures
        friendly_error = error_msg
        if "Authentication failed" in error_msg or "BAD_REQUEST_ERROR" in error_msg:
            friendly_error = "Authentication failed. Invalid Razorpay API Key ID or Secret."
        elif "connection" in error_msg.lower():
            friendly_error = "Razorpay servers are temporarily unreachable."
            
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Razorpay Order Creation Failed: {friendly_error}"
        )

@router.post("/verify-payment")
def verify_razorpay_payment(
    payload: VerifyPaymentRequest,
    tenant_id: UUID = Depends(get_current_tenant_id),
    db: Session = Depends(get_db)
):
    """
    Verifies signature of payment and updates subscription status.
    Strictly verifies signature against Razorpay key secret using the official SDK.
    """
    tier = payload.plan_tier.lower()
    if tier not in PLAN_DETAILS:
        raise HTTPException(status_code=400, detail="Invalid plan tier.")

    order_id = payload.razorpay_order_id
    payment_id = payload.razorpay_payment_id
    signature = payload.razorpay_signature

    # Verify signature using official Razorpay client utility
    try:
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        client.utility.verify_payment_signature({
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature
        })
    except razorpay.errors.SignatureVerificationError as e:
        print(f"[Razorpay Verification Error] Signature check failed for order {order_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment signature verification failed. The transaction might be spoofed."
        )
    except Exception as e:
        print(f"[Razorpay Verification Error] Unexpected verification failure: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Verification failure: {str(e)}"
        )

    # Update or insert transaction record
    tx = db.query(PaymentTransaction).filter(PaymentTransaction.order_id == order_id).first()
    if not tx:
        tx = PaymentTransaction(
            tenant_id=tenant_id,
            order_id=order_id,
            amount=PLAN_DETAILS[tier]["amount"],
            plan_tier=tier
        )
        db.add(tx)
    
    tx.payment_id = payment_id
    tx.signature = signature
    tx.status = "captured"
    
    # Update subscription in database
    sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
    if not sub:
        sub = Subscription(tenant_id=tenant_id)
        db.add(sub)

    plan = PLAN_DETAILS[tier]
    sub.plan_tier = tier
    sub.status = "active"
    sub.max_bots = plan["max_bots"]
    sub.max_messages_per_month = plan["max_messages"]
    sub.current_period_end = datetime.now(timezone.utc) + timedelta(days=30)
    sub.razorpay_order_id = order_id
    sub.razorpay_payment_id = payment_id
    
    db.commit()
    db.refresh(sub)

    print(f"[Razorpay Verification] Success. Upgraded tenant {tenant_id} to tier '{tier}'.")

    return {
        "status": "success",
        "plan_tier": sub.plan_tier,
        "max_bots": sub.max_bots,
        "max_messages_per_month": sub.max_messages_per_month,
        "current_period_end": sub.current_period_end
    }

async def process_webhook_payload(payload: dict, db: Session):
    event = payload.get("event")
    
    # Handle payment.captured, order.paid, or subscription.charged
    if event in ["payment.captured", "order.paid", "subscription.charged"]:
        payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
        notes = payment_entity.get("notes", {})
        tenant_id_str = notes.get("tenant_id")
        plan_tier = notes.get("plan_tier")
        
        # Fallback to subscription entity metadata if needed
        if not tenant_id_str:
            sub_entity = payload.get("payload", {}).get("subscription", {}).get("entity", {})
            notes = sub_entity.get("notes", {})
            tenant_id_str = notes.get("tenant_id")
            plan_tier = notes.get("plan_tier")
            
        if tenant_id_str and plan_tier:
            tenant_id = UUID(tenant_id_str)
            order_id = payment_entity.get("order_id", "")
            payment_id = payment_entity.get("id", "")
            
            # Idempotency check: if order is already captured, bypass processing
            if order_id:
                tx = db.query(PaymentTransaction).filter(PaymentTransaction.order_id == order_id).first()
                if tx and tx.status == "captured":
                    print(f"[Razorpay Webhook] Order {order_id} already processed and captured. Skipping.")
                    return
            
            # Log transaction status in payment_transactions table
            tx = db.query(PaymentTransaction).filter(PaymentTransaction.order_id == order_id).first()
            if not tx:
                tx = PaymentTransaction(
                    tenant_id=tenant_id,
                    order_id=order_id,
                    amount=payment_entity.get("amount", 0),
                    plan_tier=plan_tier.lower()
                )
                db.add(tx)
            tx.payment_id = payment_id
            tx.status = "captured"
            
            sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
            if not sub:
                sub = Subscription(tenant_id=tenant_id)
                db.add(sub)
                
            plan = PLAN_DETAILS.get(plan_tier.lower(), PLAN_DETAILS["free"])
            sub.plan_tier = plan_tier.lower()
            sub.status = "active"
            sub.max_bots = plan["max_bots"]
            sub.max_messages_per_month = plan["max_messages"]
            sub.current_period_end = datetime.now(timezone.utc) + timedelta(days=30)
            sub.razorpay_order_id = order_id
            sub.razorpay_payment_id = payment_id
            
            db.commit()
            print(f"[Razorpay Webhook] Successfully processed payment event '{event}' for tenant: {tenant_id}")

@payments_router.post("/webhook")
async def razorpay_payments_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Secure Razorpay webhook endpoint mapped to /api/v1/payments/webhook.
    Strictly verifies the HMAC signature from Razorpay.
    """
    signature = request.headers.get("X-Razorpay-Signature", "")
    raw_body = await request.body()
    
    try:
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        client.utility.verify_webhook_signature(
            raw_body.decode("utf-8"),
            signature,
            settings.RAZORPAY_WEBHOOK_SECRET
        )
    except Exception as e:
        print(f"[Razorpay Webhook Signature Error] Validation failed: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Webhook signature mismatch.")

    try:
        payload = await request.json()
        await process_webhook_payload(payload, db)
    except Exception as e:
        print("[Razorpay Webhook Error] Failed to process payload:", e)
        
    return {"status": "ok"}

@router.post("/webhook")
async def razorpay_billing_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Backup hook mapped to /api/v1/billing/webhook.
    """
    signature = request.headers.get("X-Razorpay-Signature", "")
    raw_body = await request.body()
    
    try:
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        client.utility.verify_webhook_signature(
            raw_body.decode("utf-8"),
            signature,
            settings.RAZORPAY_WEBHOOK_SECRET
        )
    except Exception as e:
        print(f"[Razorpay Webhook Signature Error] Validation failed: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Webhook signature mismatch.")

    try:
        payload = await request.json()
        await process_webhook_payload(payload, db)
    except Exception as e:
        print("[Razorpay Webhook Error] Failed to process payload:", e)
        
    return {"status": "ok"}

def has_exceeded_message_limit(db: Session, tenant_id: UUID) -> bool:
    """
    Checks if the tenant has exceeded their monthly outbound message limit.
    Enforces subscription caps dynamically.
    """
    sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
    max_messages = sub.max_messages_per_month if sub else 500
    
    if sub and sub.status != "active":
        max_messages = 500

    # Start of current month (UTC)
    now = datetime.now(timezone.utc)
    start_of_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    # 1. Count outbound chat messages
    from app.models.all_models import Message, Conversation, CampaignLog, Campaign
    chat_count = db.query(Message).join(Conversation).filter(
        Conversation.tenant_id == tenant_id,
        Message.direction == "outbound",
        Message.created_at >= start_of_month
    ).count()

    # 2. Count outbound campaign logs
    campaign_count = db.query(CampaignLog).join(Campaign).filter(
        Campaign.tenant_id == tenant_id,
        CampaignLog.status == "sent",
        CampaignLog.sent_at >= start_of_month
    ).count()

    return (chat_count + campaign_count) >= max_messages

def is_subscription_active(db: Session, tenant_id: UUID) -> bool:
    """
    Checks if a tenant's subscription is active and has not expired.
    If current period end is past due, auto-suspends/expires the plan dynamically.
    """
    from app.models.all_models import Tenant
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant or tenant.status in ["suspended", "TERMINATED"]:
        return False

    sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
    if not sub:
        # Default free tier is active
        return True

    if sub.status != "active":
        return False

    if sub.current_period_end:
        now = datetime.now(timezone.utc)
        end_time = sub.current_period_end
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)

        if now > end_time:
            # Plan has expired, change status in DB
            sub.status = "expired"
            db.commit()
            print(f"[Billing] Tenant {tenant_id} subscription expired dynamically at {end_time}")
            
            # Broadcast suspension event to Websockets to enforce UI locks immediately
            from app.core.websocket import publish_tenant_event_sync
            publish_tenant_event_sync(str(tenant_id), "subscription_expired", {"status": "expired"})
            return False

    return True

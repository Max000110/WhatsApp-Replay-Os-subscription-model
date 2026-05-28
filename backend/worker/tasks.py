from worker.celery_app import celery
from app.database import SessionLocal
from app.models.all_models import KBDocument, KBDocumentChunk, Campaign, CampaignLog, KnowledgeBase
from app.services.rag_service import rag_service
from app.services.session_service import session_service
from app.core.websocket import publish_tenant_event_sync
from pypdf import PdfReader
from sqlalchemy import text
import os
import time

@celery.task(name="worker.tasks.process_kb_document_task")
def process_kb_document_task(doc_id: str):
    """
    RAG ingestion task. Extracting text from files (PDF/TXT), chunking it,
    vectorizing it via local Ollama and inserting it into pgvector database.
    """
    db = SessionLocal()
    print(f"[Celery Worker] Starting document vectorization: {doc_id}")
    
    doc = db.query(KBDocument).filter(KBDocument.id == doc_id).first()
    if not doc:
        print(f"[Celery Worker] Error: Document {doc_id} not found.")
        db.close()
        return

    try:
        # 1. Update status to processing
        doc.status = "processing"
        db.commit()
        db.refresh(doc)
        kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == doc.kb_id).first()
        if kb:
            doc_data = {
                "id": str(doc.id),
                "kb_id": str(doc.kb_id),
                "filename": doc.filename,
                "file_path": doc.file_path,
                "status": doc.status,
                "created_at": doc.created_at.isoformat() if doc.created_at else None
            }
            publish_tenant_event_sync(str(kb.tenant_id), "kb_document", doc_data)

        # 2. Extract plain text content based on file extension
        text_content = ""
        file_path = doc.file_path

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File {file_path} does not exist on disk.")

        _, ext = os.path.splitext(file_path.lower())

        if ext == ".pdf":
            reader = PdfReader(file_path)
            extracted_pages = []
            for page in reader.pages:
                extracted_pages.append(page.extract_text() or "")
            text_content = "\n".join(extracted_pages)
        else:
            # Fallback to plain text processing
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text_content = f.read()

        if not text_content.strip():
            raise ValueError("Extracted text is empty.")

        # 3. Create overlapping text chunks (~500 chars with ~50 overlap)
        chunk_size = 500
        overlap = 50
        chunks = []
        
        start = 0
        while start < len(text_content):
            end = start + chunk_size
            chunks.append(text_content[start:end])
            start += chunk_size - overlap

        print(f"[Celery Worker] Document split into {len(chunks)} text chunks.")

        # 4. Generate vectors and insert into database pgvector
        import asyncio
        loop = asyncio.get_event_loop()

        for chunk_text in chunks:
            if not chunk_text.strip():
                continue
                
            # Synchronously run async Ollama calls
            vector = loop.run_until_complete(rag_service.get_embedding(chunk_text))
            
            # Formulate raw insert using SQL parameter binding
            vector_str = "[" + ",".join(map(str, vector)) + "]"
            
            sql_insert = text("""
                INSERT INTO kb_document_chunks (id, document_id, content, embedding)
                VALUES (uuid_generate_v4(), :doc_id, :content, :vector_str)
            """)
            
            db.execute(sql_insert, {
                "doc_id": doc.id,
                "content": chunk_text,
                "vector_str": vector_str
            })
            
        db.commit()
        
        # Mark document as fully processed
        doc.status = "processed"
        db.commit()
        db.refresh(doc)
        print(f"[Celery Worker] Ingestion succeeded for file: {doc.filename}")
        
        kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == doc.kb_id).first()
        if kb:
            doc_data = {
                "id": str(doc.id),
                "kb_id": str(doc.kb_id),
                "filename": doc.filename,
                "file_path": doc.file_path,
                "status": doc.status,
                "created_at": doc.created_at.isoformat() if doc.created_at else None
            }
            publish_tenant_event_sync(str(kb.tenant_id), "kb_document", doc_data)

    except Exception as e:
        print(f"[Celery Worker] Error processing document {doc_id}:", str(e))
        doc.status = "failed"
        db.commit()
        try:
            db.refresh(doc)
            kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == doc.kb_id).first()
            if kb:
                doc_data = {
                    "id": str(doc.id),
                    "kb_id": str(doc.kb_id),
                    "filename": doc.filename,
                    "file_path": doc.file_path,
                    "status": doc.status,
                    "created_at": doc.created_at.isoformat() if doc.created_at else None
                }
                publish_tenant_event_sync(str(kb.tenant_id), "kb_document", doc_data)
        except Exception:
            pass
    finally:
        db.close()


@celery.task(name="worker.tasks.run_campaign_broadcast_task")
def run_campaign_broadcast_task(campaign_id: str):
    """
    Sequentially processes a marketing campaign by pulling pending recipients
    and requesting WhatsApp dispatches with safe intervals to bypass bot blocklists.
    """
    db = SessionLocal()
    print(f"[Celery Worker] Commencing campaign broadcast: {campaign_id}")

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        print(f"[Celery Worker] Error: Campaign {campaign_id} not found.")
        db.close()
        return

    tenant_id = campaign.tenant_id

    try:
        campaign.status = "sending"
        db.commit()
        db.refresh(campaign)

        # Broadcast campaign state update
        campaign_data = {
            "id": str(campaign.id),
            "tenant_id": str(campaign.tenant_id),
            "session_id": str(campaign.session_id) if campaign.session_id else None,
            "name": campaign.name,
            "template_text": campaign.template_text,
            "scheduled_time": campaign.scheduled_time.isoformat() if campaign.scheduled_time else None,
            "status": campaign.status,
            "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
            "updated_at": campaign.updated_at.isoformat() if campaign.updated_at else None
        }
        publish_tenant_event_sync(str(tenant_id), "campaign", campaign_data)

        # Fetch all pending logs
        pending_logs = db.query(CampaignLog).filter(
            CampaignLog.campaign_id == campaign.id,
            CampaignLog.status == "pending"
        ).all()

        import asyncio
        loop = asyncio.get_event_loop()

        for log in pending_logs:
            # Check message limit
            from app.routers.billing import has_exceeded_message_limit, is_subscription_active
            if not is_subscription_active(db, tenant_id):
                print(f"[Celery Worker - Campaign] Subscription plan expired or suspended. Pausing campaign {campaign_id}.")
                campaign.status = "paused"
                db.commit()
                db.refresh(campaign)
                campaign_data["status"] = "paused"
                campaign_data["updated_at"] = campaign.updated_at.isoformat() if campaign.updated_at else None
                publish_tenant_event_sync(str(tenant_id), "campaign", campaign_data)
                break

            if has_exceeded_message_limit(db, tenant_id):
                print(f"[Celery Worker - Campaign] Monthly message limit reached. Pausing campaign {campaign_id}.")
                campaign.status = "paused"
                db.commit()
                db.refresh(campaign)
                campaign_data["status"] = "paused"
                campaign_data["updated_at"] = campaign.updated_at.isoformat() if campaign.updated_at else None
                publish_tenant_event_sync(str(tenant_id), "campaign", campaign_data)
                break

            session_id = campaign.session_id
            recipient = log.recipient_phone

            print(f"[Celery Worker - Campaign] Sending to {recipient}: {campaign.template_text[:20]}...")

            # Broadcast log status update as "sending"
            log.status = "sending"
            db.commit()
            db.refresh(log)
            publish_tenant_event_sync(str(tenant_id), "campaign_status", {
                "campaign": campaign_data,
                "log": {
                    "id": str(log.id),
                    "campaign_id": str(log.campaign_id),
                    "recipient_phone": log.recipient_phone,
                    "status": log.status,
                    "sent_at": log.sent_at.isoformat() if log.sent_at else None,
                    "delivered_at": log.delivered_at.isoformat() if log.delivered_at else None,
                    "read_at": log.read_at.isoformat() if log.read_at else None
                }
            })

            # Trigger WhatsApp Engine message command via session service, passing log.id as message_id
            success = loop.run_until_complete(
                session_service.send_whatsapp_message(
                    session_id=str(session_id),
                    to_phone=recipient,
                    text=campaign.template_text,
                    message_id=str(log.id)
                )
            )

            if success:
                log.status = "queued"
            else:
                log.status = "failed"
                log.error_message = "Engine refused dispatch command."
                
            db.commit()
            db.refresh(log)

            # Broadcast log status update
            publish_tenant_event_sync(str(tenant_id), "campaign_status", {
                "campaign": campaign_data,
                "log": {
                    "id": str(log.id),
                    "campaign_id": str(log.campaign_id),
                    "recipient_phone": log.recipient_phone,
                    "status": log.status,
                    "sent_at": log.sent_at.isoformat() if log.sent_at else None,
                    "delivered_at": log.delivered_at.isoformat() if log.delivered_at else None,
                    "read_at": log.read_at.isoformat() if log.read_at else None
                }
            })

            # Enforce safety cooling-off delay between bulk dispatches (10s - 15s)
            time.sleep(10 + (time.time() % 5))

        campaign.status = "completed"
        db.commit()
        db.refresh(campaign)
        campaign_data["status"] = "completed"
        campaign_data["updated_at"] = campaign.updated_at.isoformat() if campaign.updated_at else None
        publish_tenant_event_sync(str(tenant_id), "campaign", campaign_data)
        print(f"[Celery Worker] Broadcast successfully completed for campaign: {campaign.name}")

    except Exception as e:
        print(f"[Celery Worker] Campaign failed:", str(e))
        campaign.status = "paused"
        db.commit()
        db.refresh(campaign)
        campaign_data["status"] = "paused"
        campaign_data["updated_at"] = campaign.updated_at.isoformat() if campaign.updated_at else None
        publish_tenant_event_sync(str(tenant_id), "campaign", campaign_data)
    finally:
        db.close()


@celery.task(name="worker.tasks.check_subscription_reminders_task")
def check_subscription_reminders_task():
    """
    Periodic task verifying expiring subscriptions and broadcasting reminders
    over WebSockets, log systems, and WhatsApp dispatches.
    """
    db = SessionLocal()
    try:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        
        # Query active subscriptions
        subs = db.query(Subscription).filter(Subscription.status == "active").all()
        
        import asyncio
        loop = asyncio.get_event_loop()
        
        for sub in subs:
            if not sub.current_period_end:
                continue
                
            end_time = sub.current_period_end
            if end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=timezone.utc)
                
            days_left = (end_time - now).days
            
            # Match specific reminder trigger intervals (7, 3, 1, 0 days)
            if days_left in [7, 3, 1, 0]:
                print(f"[Reminders System] Subscription for tenant {sub.tenant_id} expires in {days_left} days.")
                
                msg_content = f"Reminder: Your WA-SaaS plan expires in {days_left} days. Please renew to prevent service interruptions."
                if days_left == 0:
                    msg_content = "URGENT: Your subscription plan expires today! Auto-pay charging will commence shortly."
                
                # 1. Broadcast notification via WebSockets
                publish_tenant_event_sync(str(sub.tenant_id), "subscription_reminder", {
                    "tenant_id": str(sub.tenant_id),
                    "days_left": days_left,
                    "message": msg_content
                })
                
                # 2. Trigger outbound WhatsApp notice to the linked session phone if connected
                sess = db.query(WhatsAppSession).filter(
                    WhatsAppSession.tenant_id == sub.tenant_id,
                    WhatsAppSession.status == "connected"
                ).first()
                
                if sess and sess.phone_number:
                    loop.run_until_complete(
                        session_service.send_whatsapp_message(
                            session_id=str(sess.id),
                            to_phone=sess.phone_number,
                            text=f"[Billing] {msg_content}"
                        )
                    )
                    print(f"[Reminders System] WhatsApp alert sent to {sess.phone_number}")
                    
    except Exception as e:
        print("[Reminders System] Error executing checks:", e)
    finally:
        db.close()


@celery.task(name="worker.tasks.process_autopay_renewals_task")
def process_autopay_renewals_task():
    """
    Automated charging of active subscriptions before period end.
    Simulates production subscription payment captures via Razorpay Token charging.
    """
    db = SessionLocal()
    try:
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        
        # Check active subscriptions expiring in less than 24 hours
        expiring_subs = db.query(Subscription).filter(
            Subscription.status == "active",
            Subscription.current_period_end <= now + timedelta(hours=24)
        ).all()
        
        for sub in expiring_subs:
            print(f"[AutoPay] Triggering auto-renew charge for subscription: {sub.id}")
            
            # Create a renewal job record
            from app.models.all_models import RenewalJob, PaymentTransaction
            job = RenewalJob(
                subscription_id=sub.id,
                status="processing",
                scheduled_at=now
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            
            try:
                # If autopay tokens or razorpay subscription ids exist, we execute capture
                # In production, call Razorpay Subscription charge endpoint
                charge_success = True
                
                if charge_success:
                    # Update subscription period and logs
                    sub.current_period_end = now + timedelta(days=30)
                    job.status = "succeeded"
                    job.executed_at = now
                    
                    # Create mock transaction entry
                    transaction = PaymentTransaction(
                        tenant_id=sub.tenant_id,
                        order_id=f"renew_order_{str(sub.id)[:8]}_{int(now.timestamp())}",
                        payment_id=f"pay_auto_{str(sub.id)[:8]}_{int(now.timestamp())}",
                        amount=99900 if sub.plan_tier == "starter" else (299900 if sub.plan_tier == "pro" else 999900),
                        status="captured",
                        plan_tier=sub.plan_tier
                    )
                    db.add(transaction)
                    db.commit()
                    print(f"[AutoPay] Charge successfully captured for tenant: {sub.tenant_id}. Subscription extended.")
                else:
                    raise Exception("Razorpay token transaction declined.")
                    
            except Exception as charge_err:
                print(f"[AutoPay] Renewal charge failed for sub {sub.id}: {charge_err}")
                job.status = "failed"
                job.executed_at = now
                job.error_message = str(charge_err)
                sub.status = "past_due" # Triggers grace-period or suspend restrictions
                db.commit()
                
    except Exception as e:
        print("[AutoPay] Scheduler error:", e)
    finally:
        db.close()

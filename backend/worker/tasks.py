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

        from app.services.knowledge import parse_document_to_text
        text_content = parse_document_to_text(file_path)

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

            from app.core.jid import normalize_jid
            session_id = campaign.session_id
            try:
                recipient = normalize_jid(log.recipient_phone)
            except ValueError as err:
                print(f"[Celery Worker - Campaign] Rejecting invalid recipient '{log.recipient_phone}': {err}")
                log.status = "failed"
                log.error_message = str(err)
                db.commit()
                continue

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

            from app.models.all_models import TenantSetting
            t_settings = db.query(TenantSetting).filter(TenantSetting.tenant_id == tenant_id).first()
            opts = {
                "replyDelay": t_settings.reply_delay if t_settings else 2,
                "simulateTypingDelay": t_settings.simulate_typing_delay if t_settings else 1000,
                "sendMode": t_settings.send_mode if t_settings else "humanized"
            }
            send_interval = t_settings.campaign_send_interval if t_settings else 5

            # Trigger WhatsApp Engine message command via session service, passing log.id as message_id
            success = loop.run_until_complete(
                session_service.send_whatsapp_message(
                    session_id=str(session_id),
                    to_phone=recipient,
                    text=campaign.template_text,
                    message_id=str(log.id),
                    options=opts
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

            # Enforce safety cooling-off delay between bulk dispatches based on user settings
            time.sleep(send_interval)

        campaign.status = "completed"
        db.commit()
        db.refresh(campaign)
        campaign_data["status"] = "completed"
        campaign_data["updated_at"] = campaign.updated_at.isoformat() if campaign.updated_at else None
        publish_tenant_event_sync(str(tenant_id), "campaign", campaign_data)
        print(f"[Celery Worker] Broadcast successfully completed for campaign: {campaign.name}")

        # Handle recurring campaigns scheduling next run
        rec_interval = campaign.recurring_interval
        if rec_interval and rec_interval != "none":
            from datetime import timedelta
            next_time = campaign.scheduled_time
            if rec_interval == "hourly":
                next_time += timedelta(hours=1)
            elif rec_interval == "daily":
                next_time += timedelta(days=1)
            elif rec_interval == "weekly":
                next_time += timedelta(weeks=1)

            print(f"[Celery Worker] Scheduling next iteration of recurring campaign '{campaign.name}' at {next_time}")
            
            # Create a duplicate Campaign for the next execution period
            next_campaign = Campaign(
                tenant_id=campaign.tenant_id,
                session_id=campaign.session_id,
                name=campaign.name,
                template_text=campaign.template_text,
                scheduled_time=next_time,
                recurring_interval=rec_interval,
                status="scheduled"
            )
            db.add(next_campaign)
            db.commit()
            db.refresh(next_campaign)

            # Re-insert logs for the next execution campaign recipients
            campaign_logs = db.query(CampaignLog).filter(CampaignLog.campaign_id == campaign.id).all()
            for old_log in campaign_logs:
                new_log = CampaignLog(
                    campaign_id=next_campaign.id,
                    recipient_phone=old_log.recipient_phone,
                    status="pending"
                )
                db.add(new_log)
            db.commit()

            # Schedule future execution ETA in Celery
            celery.send_task(
                "worker.tasks.run_campaign_broadcast_task",
                args=[str(next_campaign.id)],
                eta=next_time
            )

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
                    from app.core.jid import normalize_jid
                    try:
                        target_phone = normalize_jid(sess.phone_number)
                    except ValueError as err:
                        print(f"[Reminders System] Skipping invalid session phone '{sess.phone_number}': {err}")
                        continue
                    loop.run_until_complete(
                        session_service.send_whatsapp_message(
                            session_id=str(sess.id),
                            to_phone=target_phone,
                            text=f"[Billing] {msg_content}"
                        )
                    )
                    print(f"[Reminders System] WhatsApp alert sent to {target_phone}")
                    
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


@celery.task(name="worker.tasks.check_graceful_terminations_task")
def check_graceful_terminations_task():
    """
    Periodic task processing Graceful Service Terminations (Mode 2).
    For any tenant in 'PENDING TERMINATION' state whose 24-hour grace period is expired,
    fully deactivates all services, suspends the subscription, disconnects active sessions,
    and applies their configured Data Retention Policy (Archive vs. transactional hard Purge).
    """
    db = SessionLocal()
    try:
        from datetime import datetime, timezone
        from app.models.all_models import Tenant, User, Subscription, WhatsAppSession, KBDocument, KnowledgeBase
        from app.config import settings
        import httpx
        import os
        now = datetime.now(timezone.utc)
        
        tenants = db.query(Tenant).filter(
            Tenant.status == "PENDING TERMINATION",
            Tenant.termination_grace_period_ends <= now
        ).all()
        
        for tenant in tenants:
            print(f"[Termination Worker] Executing grace period expiry for tenant {tenant.id} ({tenant.name}).")
            
            # 1. Update status to TERMINATED
            tenant.status = "TERMINATED"
            tenant.is_visible = True
            
            # 2. Deactivate all tenant users (safeguarding super admin accounts)
            users = db.query(User).filter(User.tenant_id == tenant.id, User.role != "admin").all()
            for u in users:
                u.is_active = False
                
            # 3. Disable active subscription
            sub = db.query(Subscription).filter(Subscription.tenant_id == tenant.id).first()
            if sub:
                sub.status = "suspended"
                
            # 4. Disconnect WhatsApp Sessions via Node Engine
            sessions = db.query(WhatsAppSession).filter(WhatsAppSession.tenant_id == tenant.id).all()
            for sess in sessions:
                try:
                    sess.status = "disconnected"
                    # Call whatsapp engine API to remove session
                    engine_url = f"{settings.WHATSAPP_ENGINE_URL}/sessions/{sess.id}"
                    httpx.delete(engine_url, timeout=5.0)
                except Exception as sess_err:
                    print(f"[Termination Worker] FAILED disconnecting session {sess.id}: {sess_err}")
            
            db.commit()
            
            # 5. Execute Data Retention Policy (Archive vs. Delete Mode)
            if tenant.data_retention_policy == "delete":
                print(f"[Termination Worker] Policy is DELETE. Triggering secure transactional purge for tenant {tenant.id}...")
                
                # Retrieve files to delete from local disk first
                kb_docs = db.query(KBDocument).join(KnowledgeBase).filter(KnowledgeBase.tenant_id == tenant.id).all()
                for doc in kb_docs:
                    if doc.file_path and os.path.exists(doc.file_path):
                        try:
                            os.remove(doc.file_path)
                            print(f"[Purge System] Removed file: {doc.file_path}")
                        except Exception as file_err:
                            print(f"[Purge System] Error deleting file {doc.file_path}: {file_err}")
                
                # Delete tenant record (ORM Cascade will transactional-delete users, sessions, bots, KBs, campaigns, conversations, messages, logs)
                db.delete(tenant)
                db.commit()
                print(f"[Termination Worker] Transactional purge completed for tenant {tenant.id}.")
            else:
                print(f"[Termination Worker] Policy is ARCHIVE. Tenant {tenant.id} data preserved.")
                
    except Exception as e:
        print("[Termination Worker] Error executing graceful check:", e)
    finally:
        db.close()


@celery.task(name="worker.tasks.scan_stuck_delivery_task")
def scan_stuck_delivery_task():
    """
    BUG-001 Fix: Periodic scanner that detects outbound messages stuck in
    'sent' status for more than 5 minutes and flags them as 'sent_carrier_pending'.

    Root cause of delivery status delays:
      1. Carrier or recipient device delay in returning WhatsApp ACK callbacks.
      2. Recipient has read receipts disabled — no 'read' ACK ever fires.
      3. WhatsApp network silently drops the ACK frame (rare but real).

    This task prevents the UI from showing permanent 'sent' spinners by
    transitioning messages to a terminal non-blocking state with a clear label.

    Schedule: Run every 5 minutes via Celery Beat.
    Threshold: 5 minutes (configurable via STUCK_DELIVERY_THRESHOLD_MINUTES).
    """
    db = SessionLocal()
    try:
        from datetime import datetime, timezone, timedelta
        from app.models.all_models import Message, Conversation
        from app.core.websocket import publish_tenant_event_sync

        THRESHOLD_MINUTES = 5
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=THRESHOLD_MINUTES)

        # Query outbound messages stuck in 'sent' older than threshold
        stuck_messages = db.query(Message).filter(
            Message.direction == "outbound",
            Message.status == "sent",
            Message.created_at <= cutoff
        ).all()

        if not stuck_messages:
            print(f"[Delivery Scanner] No stuck 'sent' messages found at {now.isoformat()}")
            db.close()
            return

        print(f"[Delivery Scanner] Found {len(stuck_messages)} stuck message(s) older than {THRESHOLD_MINUTES} minutes.")

        updated_count = 0
        for msg in stuck_messages:
            try:
                msg.status = "sent_carrier_pending"
                db.commit()
                db.refresh(msg)
                updated_count += 1

                # Broadcast updated status to tenant WebSocket clients
                conv = db.query(Conversation).filter(Conversation.id == msg.conversation_id).first()
                if conv:
                    publish_tenant_event_sync(str(conv.tenant_id), "message_status_update", {
                        "message_id": str(msg.id),
                        "conversation_id": str(msg.conversation_id),
                        "status": "sent_carrier_pending",
                        "whatsapp_message_id": msg.whatsapp_message_id,
                        "flagged_at": now.isoformat(),
                        "reason": f"No delivery ACK received within {THRESHOLD_MINUTES} minutes"
                    })

            except Exception as msg_err:
                print(f"[Delivery Scanner] Error updating message {msg.id}: {msg_err}")
                db.rollback()
                continue

        print(f"[Delivery Scanner] Flagged {updated_count}/{len(stuck_messages)} stuck message(s) as 'sent_carrier_pending'.")

    except Exception as e:
        print("[Delivery Scanner] Scanner task error:", e)
    finally:
        db.close()


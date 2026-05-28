from worker.celery_app import celery
from app.database import SessionLocal
from app.models.all_models import KBDocument, KBDocumentChunk, Campaign, CampaignLog
from app.services.rag_service import rag_service
from app.services.session_service import session_service
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
        print(f"[Celery Worker] Ingestion succeeded for file: {doc.filename}")

    except Exception as e:
        print(f"[Celery Worker] Error processing document {doc_id}:", str(e))
        doc.status = "failed"
        db.commit()
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

    try:
        campaign.status = "sending"
        db.commit()

        # Fetch all pending logs
        pending_logs = db.query(CampaignLog).filter(
            CampaignLog.campaign_id == campaign.id,
            CampaignLog.status == "pending"
        ).all()

        import asyncio
        loop = asyncio.get_event_loop()

        for log in pending_logs:
            # Refresh session checking connection health
            session_id = campaign.session_id
            recipient = log.recipient_phone

            print(f"[Celery Worker - Campaign] Sending to {recipient}: {campaign.template_text[:20]}...")

            # Trigger WhatsApp Engine message command via session service
            success = loop.run_until_complete(
                session_service.send_whatsapp_message(
                    session_id=str(session_id),
                    to_phone=recipient,
                    text=campaign.template_text
                )
            )

            if success:
                log.status = "sent"
                log.sent_at = text("NOW()")
            else:
                log.status = "failed"
                log.error_message = "Engine refused dispatch command."
                
            db.commit()

            # Enforce safety cooling-off delay between bulk dispatches (10s - 15s)
            time.sleep(10 + (time.time() % 5))

        campaign.status = "completed"
        db.commit()
        print(f"[Celery Worker] Broadcast successfully completed for campaign: {campaign.name}")

    except Exception as e:
        print(f"[Celery Worker] Campaign failed:", str(e))
        campaign.status = "paused"
        db.commit()
    finally:
        db.close()

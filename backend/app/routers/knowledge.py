from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.service import get_current_tenant_id
from app.models.all_models import KnowledgeBase, KBDocument
from app.schemas.all_schemas import KBCreate, KBResponse, DocumentResponse
from uuid import UUID
from typing import List
import os
import shutil

router = APIRouter(prefix="/knowledge", tags=["RAG Knowledge Bases"])

# Mount physical uploads root folder inside container
UPLOAD_DIR = "/app/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.get("/", response_model=List[KBResponse])
def list_knowledge_bases(tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """Retrieves list of knowledge bases for the active tenant"""
    return db.query(KnowledgeBase).filter(KnowledgeBase.tenant_id == tenant_id).all()

@router.post("/", response_model=KBResponse)
def create_knowledge_base(payload: KBCreate, tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """Creates a new knowledge base catalog"""
    kb = KnowledgeBase(
        tenant_id=tenant_id,
        name=payload.name,
        description=payload.description
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return kb

@router.post("/{kb_id}/documents", response_model=DocumentResponse)
async def upload_kb_document(kb_id: UUID, file: UploadFile = File(...), tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """
    Ingests PDF/Text documents, saves to storage, and queues Celery text vectorization tasks
    """
    # 1. Verify target catalog scope
    kb = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == kb_id,
        KnowledgeBase.tenant_id == tenant_id
    ).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found.")

    # 2. Secure file writing with optimized binary stream validation pipeline
    file_id_path = os.path.join(UPLOAD_DIR, f"{kb_id}_{file.filename}")
    try:
        written_bytes = 0
        # Reset file stream position
        await file.seek(0)
        with open(file_id_path, "wb") as buffer:
            while True:
                chunk = await file.read(1024 * 1024) # 1MB chunk
                if not chunk:
                    break
                buffer.write(chunk)
                written_bytes += len(chunk)
                
        # Validate binary stream integrity
        if written_bytes == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")
            
        # Verify file size on block storage matches exactly
        disk_size = os.path.getsize(file_id_path)
        if disk_size != written_bytes:
            raise HTTPException(status_code=500, detail="Binary stream mismatch: disk size does not match written bytes.")
            
        print(f"[RAG Upload Pipeline] Cleanly saved and verified {written_bytes} bytes for {file.filename}.")
    except Exception as stream_err:
        if os.path.exists(file_id_path):
            try:
                os.remove(file_id_path)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Binary stream validation failed: {str(stream_err)}")

    # 3. Create Document DB state
    new_doc = KBDocument(
        kb_id=kb_id,
        filename=file.filename,
        file_path=file_id_path,
        status="processing"
    )
    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)

    # 4. Trigger Celery Task (Imported dynamically to avoid circular import loops)
    try:
        from worker.celery_app import celery
        # Dispatch background work asynchronously to Celery Redis workers
        celery.send_task("worker.tasks.process_kb_document_task", args=[str(new_doc.id)])
    except Exception as err:
        print("[Router] Failed dispatching Celery vector task:", err)
        # Fallback to immediate mock processing status if broker is offline for safety
        new_doc.status = "failed"
        db.commit()

    return new_doc

@router.get("/{kb_id}/documents", response_model=List[DocumentResponse])
def list_kb_documents(kb_id: UUID, tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """Lists all files uploaded inside a specific knowledge base"""
    # Verify catalog ownership
    kb = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == kb_id,
        KnowledgeBase.tenant_id == tenant_id
    ).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found.")

    return db.query(KBDocument).filter(KBDocument.kb_id == kb_id).all()

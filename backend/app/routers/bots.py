from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.service import get_current_tenant_id
from app.models.all_models import Chatbot, WhatsAppSession, Conversation
from app.schemas.all_schemas import BotCreate, BotUpdate, BotResponse, PromptTestRequest, PromptTestResponse
from app.services.ai_service import assemble_layered_prompt, ai_gateway
from app.services.rag_service import rag_service
from uuid import UUID
from typing import List

router = APIRouter(prefix="/bots", tags=["Chatbots"])

@router.get("/", response_model=List[BotResponse])
def list_bots(tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """Retrieves all bots belonging to the active organization tenant"""
    return db.query(Chatbot).filter(Chatbot.tenant_id == tenant_id).all()

@router.post("/", response_model=BotResponse)
def create_bot(payload: BotCreate, tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """Creates a new chatbot configured with instructions and target sessions"""
    # Verify session JID belongs to same tenant
    if payload.session_id:
        sess = db.query(WhatsAppSession).filter(
            WhatsAppSession.id == payload.session_id,
            WhatsAppSession.tenant_id == tenant_id
        ).first()
        if not sess:
            raise HTTPException(status_code=400, detail="Invalid target WhatsApp session JID.")
            
        # Deactivate any active bot currently mounted to same session JID to prevent loops
        db.query(Chatbot).filter(
            Chatbot.session_id == payload.session_id,
            Chatbot.is_active == True
        ).update({"is_active": False})
        db.commit()

    new_bot = Chatbot(
        tenant_id=tenant_id,
        session_id=payload.session_id,
        name=payload.name,
        system_prompt=payload.system_prompt,
        model_name=payload.model_name,
        temperature=payload.temperature,
        rag_enabled=payload.rag_enabled,
        is_active=True,
        personality=payload.personality,
        company_name=payload.company_name,
        services=payload.services,
        products=payload.products,
        pricing=payload.pricing,
        policies=payload.policies,
        location=payload.location,
        working_hours=payload.working_hours,
        contact_details=payload.contact_details,
        custom_instructions=payload.custom_instructions,
        memory_enabled=payload.memory_enabled
    )
    db.add(new_bot)
    db.commit()
    db.refresh(new_bot)
    return new_bot

@router.get("/{bot_id}", response_model=BotResponse)
def get_bot(bot_id: UUID, tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """Retrieves config for a single chatbot"""
    bot = db.query(Chatbot).filter(Chatbot.id == bot_id, Chatbot.tenant_id == tenant_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Chatbot not found.")
    return bot

@router.patch("/{bot_id}", response_model=BotResponse)
def update_bot(bot_id: UUID, payload: BotUpdate, tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """Updates chatbot settings"""
    bot = db.query(Chatbot).filter(Chatbot.id == bot_id, Chatbot.tenant_id == tenant_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Chatbot not found.")

    for field, val in payload.dict(exclude_unset=True).items():
        setattr(bot, field, val)

    db.commit()
    db.refresh(bot)
    return bot

@router.delete("/{bot_id}")
def delete_bot(bot_id: UUID, tenant_id: UUID = Depends(get_current_tenant_id), db: Session = Depends(get_db)):
    """Deletes a chatbot config"""
    bot = db.query(Chatbot).filter(Chatbot.id == bot_id, Chatbot.tenant_id == tenant_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Chatbot not found.")
    db.delete(bot)
    db.commit()
    return {"message": "Chatbot successfully deleted."}

@router.post("/{bot_id}/test-prompt", response_model=PromptTestResponse)
async def test_prompt_sandbox(
    bot_id: UUID,
    payload: PromptTestRequest,
    tenant_id: UUID = Depends(get_current_tenant_id),
    db: Session = Depends(get_db)
):
    """Sandbox endpoint allowing tenants to test chatbot prompt assembly and responses"""
    bot = db.query(Chatbot).filter(Chatbot.id == bot_id, Chatbot.tenant_id == tenant_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Chatbot not found.")
        
    conv = None
    if payload.conversation_id:
        conv = db.query(Conversation).filter(
            Conversation.id == payload.conversation_id,
            Conversation.tenant_id == tenant_id
        ).first()
        
    # 1. Fetch matching context (RAG)
    kb_context = ""
    if bot.rag_enabled:
        if bot.session_id:
            kb_context = await rag_service.fetch_matching_context(db, bot.session_id, payload.test_question)
        else:
            # Fallback: query pgvector using any active Knowledge Base belonging to tenant
            from app.models.all_models import KnowledgeBase
            kb = db.query(KnowledgeBase).filter(KnowledgeBase.tenant_id == tenant_id).first()
            if kb:
                query_vector = await rag_service.get_embedding(payload.test_question)
                if not all(v == 0.0 for v in query_vector):
                    from sqlalchemy import text
                    sql_search = text("""
                        SELECT chunk.content, chunk.embedding <=> :vector_str AS distance
                        FROM kb_document_chunks chunk
                        JOIN kb_documents doc ON chunk.document_id = doc.id
                        WHERE doc.kb_id = :kb_id
                        ORDER BY distance ASC
                        LIMIT 3
                    """)
                    vector_str = "[" + ",".join(map(str, query_vector)) + "]"
                    results = db.execute(sql_search, {
                        "kb_id": kb.id,
                        "vector_str": vector_str
                    }).fetchall()
                    if results:
                        contexts = [f"- {row[0].strip()}" for row in results]
                        kb_context = "\n\nRelevant Business Context:\n" + "\n".join(contexts)

    # 2. Classify intent & Assemble system prompt (Phase 5 & 6)
    from app.services.ai_service import classify_intent
    detected_intent = classify_intent(payload.test_question)
    constructed_prompt = assemble_layered_prompt(bot, conv, kb_context, intent=detected_intent)

    # 3. Close database session to release connection to the pool during slow LLM inference!
    db.close()

    # 4. Request LLM response
    from app.database import SessionLocal
    db_fresh = SessionLocal()
    try:
        llm_response = await ai_gateway.generate_response(
            prompt=payload.test_question,
            system_prompt=constructed_prompt,
            model=bot.model_name,
            db=db_fresh,
            tenant_id=tenant_id,
            chatbot_id=bot.id
        )
    finally:
        db_fresh.close()

    return PromptTestResponse(
        constructed_prompt=constructed_prompt,
        retrieved_context=kb_context,
        llm_response=llm_response
    )

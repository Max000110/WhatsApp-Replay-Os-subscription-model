import httpx
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.config import settings

class RAGService:
    """
    RAG service vectorizing queries using local Ollama embeddings and retrieving
    relevant document context chunks from PostgreSQL using pgvector cosine search.
    """

    def __init__(self):
        self.ollama_host = settings.OLLAMA_HOST
        self.embedding_model = "all-minilm:latest"

    async def get_embedding(self, text_to_embed: str) -> list:
        """
        Calls Ollama embeddings endpoint to generate a vector representation of text
        """
        url = f"{self.ollama_host}/api/embeddings"
        payload = {
            "model": self.embedding_model,
            "prompt": text_to_embed
        }
        
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    return res.json().get("embedding", [])
                else:
                    # In case the model isn't pulled yet, trigger auto-pull background request
                    print(f"[RAGService] Ollama embeddings failed: {res.text}. Trying to pull model...")
                    await client.post(f"{self.ollama_host}/api/pull", json={"name": self.embedding_model})
                    return [0.0] * 384
            except Exception as err:
                print("[RAGService] Error connecting to Ollama embeddings:", err)
                return [0.0] * 384

    async def fetch_matching_context(self, db: Session, session_id, query_text: str, limit: int = 3) -> str:
        """
        Performs vector similarity search on PostgreSQL pgvector, matching
        chunks associated with the active tenant session's chatbot's knowledge bases.
        """
        # 1. Fetch active knowledge base for chatbot configured on this session
        sql_kb = text("""
            SELECT kb.id FROM knowledge_bases kb
            JOIN chatbots cb ON cb.tenant_id = kb.tenant_id
            WHERE cb.session_id = :session_id AND cb.rag_enabled = TRUE
            LIMIT 1
        """)
        kb_res = db.execute(sql_kb, {"session_id": session_id}).fetchone()
        if not kb_res:
            return ""
            
        kb_id = kb_res[0]

        # 2. Get query text vector embedding
        query_vector = await self.get_embedding(query_text)
        if all(v == 0.0 for v in query_vector):
            return ""

        # 3. Query pgvector using Cosine distance operator (<=>)
        sql_search = text("""
            SELECT chunk.content, chunk.embedding <=> :vector_str AS distance
            FROM kb_document_chunks chunk
            JOIN kb_documents doc ON chunk.document_id = doc.id
            WHERE doc.kb_id = :kb_id
            ORDER BY distance ASC
            LIMIT :limit
        """)
        
        # Serialize list of floats as PG-compatible vector string: '[0.1,0.2,...]'
        vector_str = "[" + ",".join(map(str, query_vector)) + "]"
        
        results = db.execute(sql_search, {
            "kb_id": kb_id,
            "vector_str": vector_str,
            "limit": limit
        }).fetchall()

        if not results:
            return ""

        # Format fetched contexts cleanly
        contexts = []
        for row in results:
            contexts.append(f"- {row[0].strip()}")
            
        return "\n\nRelevant Business Context:\n" + "\n".join(contexts)

rag_service = RAGService()

import httpx
import os
import time
from sqlalchemy.orm import Session
from app.config import settings
from app.models.all_models import AIUsageLog

class AIGateway:
    """
    Unified AI model gateway mapping system prompts and chat prompts to
    Ollama or external LLMs dynamically, capturing usage analytics.
    """
    
    def __init__(self):
        self.ollama_host = settings.OLLAMA_HOST
        self.provider = settings.AI_PROVIDER
        self.api_key = settings.AI_API_KEY

    async def generate_response(
        self, 
        prompt: str, 
        system_prompt: str, 
        model: str, 
        db: Session, 
        tenant_id, 
        chatbot_id=None
    ) -> str:
        start_time = time.time()
        reply_content = ""
        
        try:
            if self.provider == "ollama":
                reply_content = await self._call_ollama(prompt, system_prompt, model)
            elif self.provider == "openrouter":
                reply_content = await self._call_openrouter(prompt, system_prompt, model)
            else:
                reply_content = "Configuration Error: Unsupported AI provider."
        except Exception as e:
            reply_content = f"Sorry, I experienced a server processing error: {str(e)}"
        
        latency = int((time.time() - start_time) * 1000)
        
        # Keep metrics logs to measure latency and estimate cost models
        try:
            # Estimate token use roughly (~4 characters per token as fallback)
            est_tokens = int((len(prompt) + len(system_prompt) + len(reply_content)) / 4)
            log = AIUsageLog(
                tenant_id=tenant_id,
                chatbot_id=chatbot_id,
                tokens_used=est_tokens,
                model_name=model,
                latency_ms=latency
            )
            db.add(log)
            db.commit()
        except Exception as err:
            print("Failed to save usage logs:", err)
            db.rollback()

        return reply_content

    async def _call_ollama(self, prompt: str, system_prompt: str, model: str) -> str:
        url = f"{self.ollama_host}/api/chat"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "options": {
                "temperature": 0.3,
                "top_p": 0.9,
                "num_predict": 400
            },
            "stream": False
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            res = await client.post(url, json=payload)
            if res.status_code == 200:
                return res.json().get("message", {}).get("content", "").strip()
            else:
                return f"[AI Engine Response Code Error {res.status_code}]"

    async def _call_openrouter(self, prompt: str, system_prompt: str, model: str) -> str:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model or "deepseek/deepseek-chat",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(url, json=payload, headers=headers)
            if res.status_code == 200:
                return res.json()["choices"][0]["message"]["content"].strip()
            else:
                return f"[OpenRouter API Error: {res.text}]"

# Export gateway singleton
ai_gateway = AIGateway()

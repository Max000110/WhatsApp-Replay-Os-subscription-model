import os

class Settings:
    PROJECT_NAME: str = "WhatsApp AI Automation SaaS"
    API_V1_STR: str = "/api/v1"
    
    # Core DB & Cache Strings
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "postgresql://saas_admin:SecretSaaSPassword123!@postgres:5432/saas_whatsapp"
    )
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://:SecretRedisPassword123!@redis:6379/0")
    
    # Internal Node Control Service
    WHATSAPP_ENGINE_URL: str = os.getenv("WHATSAPP_ENGINE_URL", "http://whatsapp-engine:3000")
    
    # AI Engine Settings
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "ollama")
    AI_API_KEY: str = os.getenv("AI_API_KEY", "")
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://ollama:11434")
    
    # JWT Authentications
    JWT_SECRET: str = os.getenv("JWT_SECRET", "VeryStrongJWTSecret987654321!")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 Days Token validity

settings = Settings()

# server/llm_factory.py
import logging
from langchain_ollama import ChatOllama
from config import settings

logger = logging.getLogger("AI-LLM-Factory")

class LLMFactory:
    """Factory for creating and managing LLM instances (Singleton pattern)."""
    
    _instances = {}

    @staticmethod
    def get_llm(
        model_name: str = settings.model_name,
        temperature: float = settings.temperature,
        num_ctx: int = settings.context_size,
        num_gpu: int = -1,
        format: str | None = None,
        base_url: str | None = None,
    ):
        """Returns a configured ChatOllama instance."""
        resolved_base = base_url or ("/".join(settings.ollama_url.split("/")[:3]) if settings.ollama_url else None)
        cache_key = f"{model_name}-{temperature}-{num_ctx}-{num_gpu}-{format}-{resolved_base}"
        
        if cache_key not in LLMFactory._instances:
            logger.info("Initializing LLM instance: %s (ctx=%dk)", model_name, num_ctx // 1024)
            
            kwargs = dict(
                base_url=resolved_base,
                model=model_name,
                temperature=temperature,
                num_ctx=num_ctx,
                num_predict=settings.max_tokens,
                num_thread=12,
                keep_alive=-1,
            )
            
            if format is not None:
                kwargs["format"] = format
            
            LLMFactory._instances[cache_key] = ChatOllama(**kwargs)
            
        return LLMFactory._instances[cache_key]

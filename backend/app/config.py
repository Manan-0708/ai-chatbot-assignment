import os
# Prevent litellm from attempting to fetch remote cost maps over network
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"

from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./chat.db")
    LLM_API_KEYS: str = os.getenv("LLM_API_KEYS", "mock_key_1,mock_key_2")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "*")
    ENABLE_FAILURE_SIMULATION: bool = os.getenv("ENABLE_FAILURE_SIMULATION", "true").lower() in ("true", "1", "t", "yes")

    @property
    def api_keys_list(self) -> List[str]:
        keys = [k.strip() for k in self.LLM_API_KEYS.split(",") if k.strip()]
        # Also check LLM_API_KEY_1, LLM_API_KEY_2 if present
        k1 = os.getenv("LLM_API_KEY_1")
        k2 = os.getenv("LLM_API_KEY_2")
        if k1 and k1 not in keys:
            keys.append(k1)
        if k2 and k2 not in keys:
            keys.append(k2)
        return keys

    @property
    def origins_list(self) -> List[str]:
        if self.ALLOWED_ORIGINS == "*":
            return ["*"]
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

settings = Settings()

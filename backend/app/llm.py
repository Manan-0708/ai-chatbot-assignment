import time
import logging
from typing import List, Dict, Any, Optional, Tuple
import litellm
from litellm.caching.caching import Cache
from .config import settings

logger = logging.getLogger("ai_chatbot.llm")
logging.basicConfig(level=logging.INFO)

# Enable LiteLLM in-memory / local caching
try:
    litellm.cache = Cache(type="local")
    cache_status = "enabled"
except Exception as e:
    logger.warning("Failed to initialize LiteLLM cache: %s", e)
    cache_status = "disabled"

class AllProvidersUnavailableException(Exception):
    """Raised when all configured LLM providers/keys fail."""
    pass

class SimulatedProviderError(Exception):
    """Raised when X-Simulate-Failure triggers."""
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code

def parse_simulation_header(header_val: Optional[str]) -> Dict[str, int]:
    """Parse X-Simulate-Failure header into a mapping of key_id -> status_code."""
    if not header_val or not settings.ENABLE_FAILURE_SIMULATION:
        return {}
    sim_map = {}
    parts = header_val.split(",")
    for part in parts:
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            try:
                sim_map[k.strip().lower()] = int(v.strip())
            except ValueError:
                continue
    return sim_map

def should_simulate_failure(key_id: str, sim_map: Dict[str, int]) -> Optional[int]:
    """Check if the given key_id (e.g. key_1) or wildcard (*) has a simulated failure."""
    if "*" in sim_map:
        return sim_map["*"]
    if key_id.lower() in sim_map:
        return sim_map[key_id.lower()]
    return None

def is_retryable_error(error: Exception) -> bool:
    """Determine if error is a 429, quota exceeded, or 5xx error."""
    if isinstance(error, SimulatedProviderError):
        return error.status_code == 429 or error.status_code >= 500

    status_code = getattr(error, "status_code", None)
    if status_code and (status_code == 429 or status_code >= 500):
        return True

    err_str = str(error).lower()
    retry_keywords = ["rate limit", "rate_limit", "429", "quota", "500", "502", "503", "504", "overloaded", "server error"]
    return any(kw in err_str for kw in retry_keywords)

def execute_chat_completion(
    messages: List[Dict[str, str]],
    simulate_header: Optional[str] = None
) -> Tuple[str, Dict[str, Any]]:
    """
    Execute chat completion using LiteLLM with key failover, caching, and failure simulation.
    Returns: (response_text, metadata_dict)
    """
    api_keys = settings.api_keys_list
    if not api_keys:
        logger.error("No LLM API keys configured.")
        raise AllProvidersUnavailableException("all providers unavailable")

    sim_map = parse_simulation_header(simulate_header)
    model = settings.LLM_MODEL

    start_time = time.time()
    last_error = None

    for idx, key in enumerate(api_keys):
        key_id = f"key_{idx + 1}"
        logger.info("Attempting LLM call using provider %s", key_id)

        try:
            # Check for simulated failure on this key
            sim_code = should_simulate_failure(key_id, sim_map)
            if sim_code:
                logger.warning("Simulating failure HTTP %d for provider %s", sim_code, key_id)
                raise SimulatedProviderError(sim_code, f"Simulated failure {sim_code} on {key_id}")

            # LiteLLM completion call
            # Caching is active via litellm.cache
            response = litellm.completion(
                model=model,
                messages=messages,
                api_key=key,
                caching=True
            )

            latency_ms = int((time.time() - start_time) * 1000)

            # Determine cache status
            hidden_params = getattr(response, "_hidden_params", {}) or {}
            is_cache = hidden_params.get("cache_hit") is True or getattr(response, "cache_hit", False) is True
            source = "LLM_CACHE" if is_cache else "LIVE_INFERENCE"

            # Extract content
            content = response.choices[0].message.content or ""

            # Extract tokens
            usage = getattr(response, "usage", None)
            input_tokens = getattr(usage, "prompt_tokens", None) if usage else None
            output_tokens = getattr(usage, "completion_tokens", None) if usage else None

            # Fallback accurate token counting if usage is missing
            if input_tokens is None or input_tokens == 0:
                try:
                    input_tokens = litellm.token_counter(model=model, messages=messages)
                except Exception:
                    input_tokens = max(1, sum(len(m.get("content", "").split()) for m in messages))

            if output_tokens is None:
                try:
                    output_tokens = litellm.token_counter(model=model, text=content)
                except Exception:
                    output_tokens = max(1, len(content.split()))

            metadata = {
                "source": source,
                "model": model,
                "latency_ms": latency_ms,
                "input_tokens": int(input_tokens),
                "output_tokens": int(output_tokens)
            }

            return content, metadata

        except Exception as e:
            last_error = e
            # Ensure actual API key is NEVER exposed in logs
            error_msg = str(e).replace(key, "[REDACTED_API_KEY]")
            logger.warning("Provider %s failed: %s", key_id, error_msg)

            if is_retryable_error(e):
                logger.info("Failing over from %s to next provider...", key_id)
                continue
            else:
                # If error is not retryable (e.g. invalid request format), try next or break
                logger.info("Non-retryable error on %s, checking next provider...", key_id)
                continue

    logger.error("All %d configured providers failed.", len(api_keys))
    raise AllProvidersUnavailableException("all providers unavailable")

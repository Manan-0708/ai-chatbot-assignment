import os
# Set testing environment variables before importing app
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
os.environ["DATABASE_URL"] = "sqlite:///./test_chat.db"
os.environ["LLM_API_KEYS"] = "test_key_1,test_key_2"
os.environ["ENABLE_FAILURE_SIMULATION"] = "true"

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.database import init_db, get_db_connection

@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()
    with get_db_connection() as conn:
        with conn:
            conn.execute("DELETE FROM messages")
    yield
    with get_db_connection() as conn:
        with conn:
            conn.execute("DELETE FROM messages")

client = TestClient(app)

def make_mock_litellm_response(content="Hello! How can I help you?", cache_hit=False):
    mock_resp = MagicMock()
    mock_resp.choices = [
        MagicMock(message=MagicMock(content=content))
    ]
    mock_resp.usage = MagicMock(prompt_tokens=12, completion_tokens=8)
    mock_resp._hidden_params = {"cache_hit": cache_hit}
    mock_resp.cache_hit = cache_hit
    return mock_resp

def test_health_endpoint():
    """Verify health endpoint returns status, configured key count, and cache status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["configured_keys"] >= 2
    assert "cache_status" in data

@patch("litellm.completion")
def test_successful_chat_response(mock_completion):
    """Verify standard chat completion and required metadata structure."""
    mock_completion.return_value = make_mock_litellm_response("Test AI response", cache_hit=False)

    payload = {
        "session_id": "test_session_1",
        "message": "Hello AI"
    }
    response = client.post("/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "test_session_1"
    assert data["role"] == "assistant"
    assert data["content"] == "Test AI response"
    
    meta = data["metadata"]
    assert meta["source"] == "LIVE_INFERENCE"
    assert "model" in meta
    assert isinstance(meta["latency_ms"], int)
    assert meta["input_tokens"] > 0
    assert meta["output_tokens"] > 0

@patch("litellm.completion")
def test_multi_turn_conversation(mock_completion):
    """Verify multiple turns are maintained in session history and fed to subsequent turns."""
    mock_completion.side_effect = [
        make_mock_litellm_response("Nice to meet you Alice!"),
        make_mock_litellm_response("Your name is Alice.")
    ]

    session_id = "test_multi_turn"

    # Turn 1
    resp1 = client.post("/chat", json={"session_id": session_id, "message": "My name is Alice"})
    assert resp1.status_code == 200
    assert resp1.json()["content"] == "Nice to meet you Alice!"

    # Turn 2
    resp2 = client.post("/chat", json={"session_id": session_id, "message": "What is my name?"})
    assert resp2.status_code == 200
    assert resp2.json()["content"] == "Your name is Alice."

    # Verify history in database
    history_resp = client.get(f"/sessions/{session_id}/messages")
    assert history_resp.status_code == 200
    history = history_resp.json()
    assert len(history) == 4
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "My name is Alice"
    assert history[1]["role"] == "assistant"
    assert history[2]["role"] == "user"
    assert history[2]["content"] == "What is my name?"
    assert history[3]["role"] == "assistant"

@patch("litellm.completion")
def test_cache_hit(mock_completion):
    """Verify resolution source is LLM_CACHE when cache hit is indicated."""
    mock_completion.return_value = make_mock_litellm_response("Cached response", cache_hit=True)

    response = client.post("/chat", json={
        "session_id": "test_cache",
        "message": "Give me cached response"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["metadata"]["source"] == "LLM_CACHE"

@patch("litellm.completion")
def test_failover_to_second_key(mock_completion):
    """Verify that when key_1 fails with 429, system fails over to key_2 and returns 200."""
    mock_completion.return_value = make_mock_litellm_response("Success via fallback key")

    headers = {"X-Simulate-Failure": "key_1=429"}
    response = client.post(
        "/chat",
        headers=headers,
        json={"session_id": "test_failover", "message": "Trigger failover"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["content"] == "Success via fallback key"
    assert mock_completion.called

@patch("litellm.completion")
def test_all_keys_failing(mock_completion):
    """Verify that when all keys fail, return 503 and do not save failed request in history."""
    headers = {"X-Simulate-Failure": "*=429"}
    session_id = "test_all_fail"

    response = client.post(
        "/chat",
        headers=headers,
        json={"session_id": session_id, "message": "This should fail completely"}
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "all providers unavailable"}

    # Verify failed request was NOT saved in history
    history_resp = client.get(f"/sessions/{session_id}/messages")
    assert history_resp.status_code == 200
    assert len(history_resp.json()) == 0

def test_invalid_input():
    """Verify validation on empty or missing inputs returns 422."""
    # Missing message
    r1 = client.post("/chat", json={"session_id": "test_id"})
    assert r1.status_code == 422

    # Empty message
    r2 = client.post("/chat", json={"session_id": "test_id", "message": "   "})
    assert r2.status_code == 422

    # Missing session_id
    r3 = client.post("/chat", json={"message": "hello"})
    assert r3.status_code == 422

@patch("litellm.completion")
def test_session_history_endpoint(mock_completion):
    """Verify retrieving session history returns messages in chronological order."""
    mock_completion.return_value = make_mock_litellm_response("Echo response")
    session_id = "test_history_order"

    client.post("/chat", json={"session_id": session_id, "message": "Msg 1"})
    client.post("/chat", json={"session_id": session_id, "message": "Msg 2"})

    resp = client.get(f"/sessions/{session_id}/messages")
    assert resp.status_code == 200
    messages = resp.json()
    assert len(messages) == 4
    # Chronological check
    assert messages[0]["content"] == "Msg 1"
    assert messages[1]["role"] == "assistant"
    assert messages[2]["content"] == "Msg 2"
    assert messages[3]["role"] == "assistant"

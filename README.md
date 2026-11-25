# AI Chatbot Full-Stack Application

A lightweight, reliable full-stack AI chatbot built with FastAPI, React (Vite), SQLite, and LiteLLM. It features automatic multi-key fallback, in-memory LiteLLM response caching, persistent session history, and fine-grained latency and token tracking.

---

## 1. Live URLs

- **Frontend (Vercel):** `https://ai-chatbot-frontend-demo.vercel.app` *(or your deployed Vercel URL)*
- **Backend (Render):** `https://ai-chatbot-backend-demo.onrender.com` *(or your deployed Render URL)*
- **API Health Check:** `https://ai-chatbot-backend-demo.onrender.com/health`
- **GitHub Repository:** https://github.com/Manan-0708/ai-chatbot-assignment

> **Note on Deployment:** To deploy live under your personal accounts:
> 1. Push this repository to your GitHub profile (`git push origin main`).
> 2. **Backend (Render):** Create a new Web Service pointing to your repo. Set runtime to Python (or Docker), build command `pip install -r backend/requirements.txt`, and start command `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`. Configure environment variables `LLM_API_KEYS` and `ALLOWED_ORIGINS=*`.
> 3. **Frontend (Vercel):** Import your repository into Vercel, set Root Directory to `frontend`, and configure `VITE_API_BASE_URL` to point to your live Render backend URL.

---

## 2. Run locally: with Docker and without

### Prerequisites
- Python 3.10+
- Node.js 18+ and npm
- Docker & Docker Compose (optional, for containerized run)

---

### Option A: Running with Docker (Recommended)

1. **Clone repository and configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your LLM API keys if making live model calls
   ```

2. **Start the containers:**
   ```bash
   make up
   # OR directly with docker compose:
   docker compose up -d --build
   ```
   - **Frontend:** http://localhost:3000
   - **Backend API:** http://localhost:8000
   - **Health Check:** http://localhost:8000/health

3. **Stop the containers:**
   ```bash
   make down
   # OR:
   docker compose down
   ```

---

### Option B: Running without Docker (Manual Setup)

#### 1. Backend Setup (FastAPI)
```bash
# Navigate to backend directory
cd backend

# Create and activate Python virtual environment
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start FastAPI server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
The backend API is now running at `http://localhost:8000`.

#### 2. Frontend Setup (React + Vite)
```bash
# In a new terminal, navigate to frontend directory
cd frontend

# Install npm dependencies
npm install

# Start Vite development server
npm run dev
```
Open your browser at `http://localhost:3000`.

---

### Running Automated Backend Tests

The test suite validates health, chat completion, multi-turn history, cache hits, failover to fallback keys, complete provider failures, input validation, and session history ordering:
```bash
# From the project root with the virtualenv active:
pytest backend/tests -v
```

---

## 3. Design decisions: key fallback, caching, SQLite session storage

### 1. Key Fallback & Resilience
- **Mechanism:** LiteLLM is initialized with an ordered list of API keys (`LLM_API_KEYS`). When a request arrives, the system attempts the primary provider (`key_1`).
- **Error Handling:** If a transient or quota error occurs (HTTP 429 RateLimit, Quota Exhausted, or 5xx Server Error), the system logs a safe warning (masking the secret key) and automatically cascades to `key_2`.
- **All Providers Unavailable:** If all configured keys fail, the backend returns HTTP 503 with `{"detail": "all providers unavailable"}` and intentionally does **not** persist the failed request into SQLite, ensuring the session history remains clean and uncorrupted.
- **Security:** Raw API keys are never leaked to logs, client responses, or error details.

### 2. LiteLLM Caching
- **Implementation:** Integrated LiteLLM caching (`litellm.cache = Cache(type="local")` with `caching=True`).
- **Resolution Source:** If an identical prompt/context is requested, LiteLLM resolves from the local cache. The backend inspects `response._hidden_params["cache_hit"]` to tag metadata as `LLM_CACHE`. Fresh inference requests are tagged as `LIVE_INFERENCE`.
- **Latency & Tokens:** Cached queries return significantly reduced latency and calculate accurate prompt/completion tokens.

### 3. SQLite Session Storage
- **Automatic Initialization:** SQLite database (`DATABASE_URL`) and tables are created automatically on application startup.
- **Session Isolation:** Each conversation is bound to a unique `session_id`. Messages are stored chronologically with role (`user` or `assistant`), content, and rich JSON metadata.
- **Docker Persistence:** Data persists across container restarts through a Docker named volume (`chat-data`) mounted at `/data/chat.db`.
- **Concurrency & Resource Management:** Uses an explicit connection context manager ensuring clean commits and immediate file closing to prevent lock contention on Windows/Linux.

---

## 4. Verification: how to see failover, cache hits and per-message token usage

### 1. Per-Message Token Usage & Metadata
Each AI response displays the required metadata directly below the response:
- `Source`: `LIVE_INFERENCE` or `LLM_CACHE` (`data-testid="meta-source"`)
- `Model`: Target model name (`data-testid="meta-model"`)
- `Latency`: Execution duration in milliseconds (`data-testid="meta-latency"`)
- `Input Tokens`: Count of prompt tokens (`data-testid="meta-input-tokens"`)
- `Output Tokens`: Count of generated tokens (`data-testid="meta-output-tokens"`)

### 2. Testing Cache Hits
1. Open http://localhost:3000 in your browser.
2. Send the message: `What is the capital of France?`
3. Observe the first response: Source will be **`LIVE_INFERENCE`** with standard latency (e.g., 600–1200ms).
4. Send the exact same message again: `What is the capital of France?`
5. Observe the response: Source changes to **`LLM_CACHE`** with near-instant latency.

### 3. Testing Failover with `X-Simulate-Failure`
The backend supports simulation testing via the `X-Simulate-Failure` header when `ENABLE_FAILURE_SIMULATION=true`.

You can test this easily using the UI toggle **"Settings / Failover Test"** in the top-right header, or via `curl`:

- **Simulate Key 1 Rate Limit (429):**
  ```bash
  curl -X POST http://localhost:8000/chat \
    -H "Content-Type: application/json" \
    -H "X-Simulate-Failure: key_1=429" \
    -d '{"session_id": "test_sess", "message": "Hello via key 2"}'
  ```
  *Result:* The backend detects key 1 failure, fails over to `key_2`, and returns HTTP 200 with a successful response.

- **Simulate Key 1 Internal Server Error (500):**
  ```bash
  curl -X POST http://localhost:8000/chat \
    -H "Content-Type: application/json" \
    -H "X-Simulate-Failure: key_1=500" \
    -d '{"session_id": "test_sess", "message": "Testing 500 failover"}'
  ```
  *Result:* Fails over smoothly to `key_2`.

- **Simulate All Keys Failing (`*=429`):**
  ```bash
  curl -X POST http://localhost:8000/chat \
    -H "Content-Type: application/json" \
    -H "X-Simulate-Failure: *=429" \
    -d '{"session_id": "test_sess", "message": "This must fail"}'
  ```
  *Result:* Returns HTTP 503 with body `{"detail": "all providers unavailable"}` and no message is stored in session history.

---

## 5. Setup Used: your editor and AI tools

- **Editor / IDE:** Visual Studio Code & Antigravity 2.0 IDE
- **AI Coding Agent:** Antigravity (Powered by Google DeepMind)
- **Runtime Environment:** Windows 11 x64, Python 3.11, Node.js 24, Vite 5, React 18

---

## 6. Bonus features (if any)

1. **In-UI Failover Simulation Controls:** Built-in collapsible preset buttons in the chat header to test `key_1=429`, `key_1=500`, `key_1=429,key_2=500`, and `*=429` without needing Postman or terminal commands.
2. **System Prompt Support:** Optional system prompt field in the UI for guiding assistant behavior.
3. **Multi-Stage Dockerfiles:** Minified, production-hardened multi-stage builds for both Python (slimming runtime image) and React (served via Alpine Nginx).
4. **Resilient Offline Fallback:** Automatic handling of local cost map (`LITELLM_LOCAL_MODEL_COST_MAP`) preventing network hangs during air-gapped or sandboxed test runs.

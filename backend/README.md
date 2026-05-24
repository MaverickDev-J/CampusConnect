  # CampusMind Backend

  > Smart Campus AI Knowledge Base — FastAPI · MongoDB · ChromaDB · Gemini AI · LangGraph · JWT Auth

  ---

  ## How to Run

  ```bash
  cd backend
  uv run uvicorn main:app --reload
  ```

  | Resource | URL |
  |---|---|
  | Swagger UI | [http://localhost:8000/docs](http://localhost:8000/docs) |
  | Health Check | `GET /health` |
  | Static Files | `http://localhost:8000/static/pdfs/...` |

  ---

  ## 🔐 Authentication

  ### `POST /api/auth/register`

  The `profile` field changes based on `role`:

  <details>
  <summary><b>👨‍🎓 Student</b> — requires <code>roll_no</code>, <code>branch</code>, <code>year</code></summary>

  ```json
  {
    "email": "jatin.student@tcet.com",
    "name": "Jatin Sharma",
    "password": "secret123",
    "role": "student",
    "profile": {
      "roll_no": "2101",
      "branch": "AI&DS",
      "year": 3
    }
  }
  ```

  > `can_upload` is auto-set to `false`. An admin must grant it via `/api/admin/grant-upload`.

  </details>

  <details>
  <summary><b>👨‍🏫 Faculty</b> — requires <code>department</code></summary>

  ```json
  {
    "email": "jatin.faculty@tcet.com",
    "name": "Prof. Jatin Sharma",
    "password": "secret123",
    "role": "faculty",
    "profile": {
      "department": "AI&DS"
    }
  }
  ```

  </details>

  <details>
  <summary><b>🛡️ Admin</b> — requires <code>admin_secret_key</code></summary>

  ```json
  {
    "email": "jatin.admin@tcet.com",
    "name": "Admin Jatin",
    "password": "secret123",
    "role": "admin",
    "admin_secret_key": "TCET_HACK_2026"
  }
  ```

  > Without the correct `admin_secret_key` → **403 Forbidden**.

  </details>

  ### `POST /api/auth/login`

  Uses `OAuth2PasswordRequestForm` (`username` = email, `password`).

  ```json
  // Response
  { "access_token": "eyJhbG...", "token_type": "bearer" }
  ```

  ### `GET /api/users/me`

  Returns the authenticated user's full profile. Requires `Authorization: Bearer <token>`.

  ### 📋 Allowed Enum Values

  | Field | Allowed Values |
  |---|---|
  | `role` | `admin`, `faculty`, `student` |
  | `branch` / `department` | `AI&DS`, `COMP`, `IT`, `EXTC`, `MECH`, `CIVIL` |
  | `year` | `1`, `2`, `3`, `4` (integers only) |

  ---

  ## 🛠️ API Documentation

  ### Admin Management

  > 🔒 **Auth Level:** Admin Only — all endpoints require `role: "admin"` in JWT.

  | Method | Endpoint | Description |
  |---|---|---|
  | `PATCH` | `/api/admin/grant-upload` | Grants upload permission to a student (CR) |
  | `PATCH` | `/api/admin/revoke-upload` | Revokes upload permission from a student |
  | `GET` | `/api/admin/users` | Lists all users (passwords excluded) |

  **Grant / Revoke — Request Body:**

  ```json
  { "target_user_id": "stu_540d241f85f6" }
  ```

  ```json
  // Response (200)
  { "message": "Upload permission granted", "user_id": "stu_540d241f85f6" }
  ```

  **List Users — Query Params:**

  ```
  GET /api/admin/users                → all users
  GET /api/admin/users?role=student   → students only
  GET /api/admin/users?role=faculty   → faculty only
  ```

  ```json
  // Response (200)
  { "users": [ { "user_id": "...", "email": "...", "role": "...", ... } ], "count": 5 }
  ```

  | Error Case | Status |
  |---|---|
  | Non-admin JWT | `403` |
  | Target user not found | `404` |
  | Target is not a student | `400` |

  ---

  ### File & Knowledge Base

  > 🔒 **Auth Level:** Admin, Faculty, or CR Students (with `can_upload: true`)

  #### `POST /api/upload/file`

  Multipart file upload with streaming SHA-256 deduplication.

  **Form Fields:**

  | Field | Type | Required | Description |
  |---|---|---|---|
  | `file` | `UploadFile` | ✅ | The binary file to upload |
  | `year` | `int` | ✅ | Academic year (`1`–`4`) |
  | `branch` | `str` | ✅ | Branch enum (`COMP`, `AI&DS`, etc.) |
  | `subject` | `str` | ✅ | Free text (e.g., `"Machine Learning"`) |
  | `doc_type` | `str` | ✅ | `lecture` · `notes` · `pyq` · `lab` · `reference` |
  | `unit` | `int` | ❌ | Unit number (optional) |

  **Allowed MIME Types:**

  | Role | PDF | Images (PNG/JPEG/WebP) | Video (MP4/WebM) | Audio |
  |---|---|---|---|---|
  | Admin / Faculty | ✅ | ✅ | ✅ | ❌ |
  | CR Student (`can_upload: true`) | ✅ | ✅ | ❌ | ❌ |
  | Normal Student | ❌ Upload blocked | ❌ Upload blocked | ❌ | ❌ |

  > ⚠️ **Audio files are not supported.** Normal students cannot upload — an admin must first grant `can_upload` via `PATCH /api/admin/grant-upload`.

  **Responses:**

  ```json
  // 202 Accepted — new file uploaded
  {
    "file_id": "file_cd88e078d7f7...",
    "original_name": "Module 02.pdf",
    "file_type": "pdf",
    "status": "pending",
    "message": "Uploaded. Processing in background."
  }
  ```

  ```json
  // 200 OK — duplicate file detected (same SHA-256 hash)
  {
    "file_id": "file_cd88e078d7f7...",
    "message": "File already exists",
    "status": "pending"
  }
  ```

  | Error Case | Status |
  |---|---|
  | Student without `can_upload` | `403` |
  | CR student uploading video | `403` |
  | Unsupported MIME type | `415` |
  | No auth token | `401` |

  #### `GET /api/files`

  > 🔒 **Auth Level:** Any authenticated user (institute content is visible to all roles)

  Lists all institute-wide academic resources with multi-filter support, sorted by newest first.

  **Query Parameters (all optional):**

  | Param | Type | Example | Description |
  |---|---|---|---|
  | `year` | `int` | `?year=3` | Academic year (1–4) |
  | `branch` | `str` | `?branch=COMP` | Branch filter |
  | `subject` | `str` | `?subject=Machine Learning` | Subject name |
  | `doc_type` | `str` | `?doc_type=notes` | `lecture` · `notes` · `pyq` · `lab` · `reference` |
  | `file_type` | `str` | `?file_type=pdf` | `pdf` · `image` · `video` |

  ```json
  // Response (200)
  {
    "files": [
      {
        "file_id": "file_cd88e078d7f7...",
        "original_name": "Module 02.pdf",
        "file_type": "pdf",
        "file_size_bytes": 849220,
        "academic": { "year": 3, "branch": "COMP", "subject": "Machine Learning", "doc_type": "notes" },
        "processing": { "status": "pending", "chunk_count": 0 },
        "uploaded_by": "fac_19664f621900",
        "playback_url": "/static/pdfs/file_cd88e078d7f7.pdf"
      }
    ],
    "count": 1
  }
  ```

  > 💡 **`playback_url`** maps directly to the `/static` mount — use it in the frontend to render or link files without building URLs manually.

  #### `GET /api/files/{file_id}`

  Returns detailed metadata for a single resource by its `file_id`.

  ```json
  // Response (200)
  {
    "file_id": "file_b9b2406793d5...",
    "original_name": "download.jpeg",
    "file_type": "image",
    "playback_url": "/static/images/file_b9b2406793d5.jpeg",
    ...
  }
  ```

  | Error Case | Status |
  |---|---|
  | File not found | `404` |
  | Visibility is not `institute` | `403` |

  > 🔐 **Security:** `storage_path` and `sha256_hash` are **strictly excluded** from all public responses. Only `playback_url` is exposed for file access.

  #### 🖥️ Frontend Integration Note

  > React **Smart Cards** should use the `playback_url` field from the API response to display or link files:
  > - **PDFs** → embed in `<iframe>` or link to `playback_url`
  > - **Images** → render with `<img src={playback_url} />`
  > - **Videos** → play with `<video src={playback_url} />`
  >
  > The URL is ready to use — just prepend your API base URL (e.g., `http://localhost:8000`) for local dev.

  ---

  ## 📁 Storage & Static Serving

  ```
  storage/
  ├── uploads/
  │   ├── pdfs/       ← PDF files
  │   ├── images/     ← PNG, JPEG, WebP
  │   └── videos/     ← MP4, WebM
  └── temp/           ← SHA-256 dedup staging (auto-cleaned)
  ```

  Files are served publicly via the **`/static`** prefix:

  ```
  http://localhost:8000/static/pdfs/file_cd88e078d7f7.pdf
  http://localhost:8000/static/images/file_b9b24067.jpeg
  http://localhost:8000/static/videos/file_a1c3e5f7.mp4
  ```

  ---

  ## 🧠 Vector Database (ChromaDB)

  We use **ChromaDB** in `PersistentClient` mode, stored locally at `./chroma_data/`. No Docker required — data persists across server restarts.

  ```
  chroma_data/              ← auto-created on first startup
  └── campus_vectors/       ← single collection, cosine similarity (HNSW)
  ```

  > Initialized in `database/chroma.py` using the same singleton pattern as `mongo.py`. The collection is created in the FastAPI lifespan alongside MongoDB indexes.

  ---

  ## ⚙️ Ingestion Pipeline

  Every file uploaded via `POST /api/upload/file` triggers a **background ingestion task** (`api/services/ingestion.py`):

  ```mermaid
  graph LR
      A[Upload] --> B{File Type}
      B -->|PDF| C[PyMuPDF Text Extraction]
      C -->|< 50 chars?| D[Gemini Vision OCR Fallback]
      C -->|Text OK| E[Chunking]
      D --> E
      B -->|Image| D
      E --> F[Gemini Embedding API]
      F --> G[ChromaDB Upsert]
      G --> H[MongoDB Status → completed]
  ```

  | Stage | Tool | Detail |
  |---|---|---|
  | Text Extraction | **PyMuPDF** (`fitz`) | Page-by-page `get_text()` |
  | Vision Fallback | **Gemini 2.5 Flash-Lite** → **Flash** | Scanned/handwritten pages & standalone images |
  | Chunking | **LangChain** `RecursiveCharacterTextSplitter` | 800 chars, 100 overlap |
  | Embedding | **Gemini Embedding API** (`gemini-embedding-001`) | `RETRIEVAL_DOCUMENT` task type, batched 100 at a time |
  | Vector Store | **ChromaDB** `campus_vectors` | Cosine similarity, persistent storage |

  **Chunk ID format:** `{file_id}_p{page}_c{chunk}` (e.g., `file_abc123_p2_c3`)

  > 🔄 **Model Fallback:** If `gemini-2.5-flash-lite` hits a rate limit (429), the service automatically waits 1 second and retries with `gemini-2.5-flash`.

  ---

  ## 🏷️ Metadata Strategy

  Every chunk stored in ChromaDB carries **full academic metadata** for scoped RAG searching:

  | Metadata Field | Type | Source | Example |
  |---|---|---|---|
  | `file_id` | `str` | Upload system | `file_cd88e078d7f7` |
  | `file_name` | `str` | Original filename | `Module 02.pdf` |
  | `file_type` | `str` | Upload detection | `pdf` / `image` |
  | `page_number` | `int` | Extraction | `2` |
  | `chunk_index` | `int` | Chunking | `3` |
  | `year` | `int` | Upload form | `3` |
  | `branch` | `str` | Upload form | `COMP` |
  | `subject` | `str` | Upload form | `Machine Learning` |
  | `doc_type` | `str` | Upload form | `notes` |
  | `unit` | `int` | Upload form (optional) | `2` |
  | `visibility` | `str` | Server default | `institute` |
  | `uploaded_by` | `str` | JWT / MongoDB | `fac_19664f621900` |

  > `unit` is only stored when provided — ChromaDB rejects `None` values, so it's omitted if missing.

  > This enables **scoped queries** like: *"Find notes about backpropagation in Year 3 COMP Machine Learning"* — the RAG layer can filter by `year`, `branch`, and `subject` before semantic search.

  ---

  ## 🤖 LangGraph AI Chat

  The chat system orchestrates a **4-node AI agent pipeline** with real-time token streaming via Server-Sent Events (SSE).

  ### Architecture

  ```mermaid
  sequenceDiagram
      participant Client
      participant FastAPI as POST /sessions/{id}/message
      participant Entry as entry_node
      participant Router as router_node
      participant Retriever as retriever_vector_node
      participant Synth as synthesis_node_stream
      participant Gemini as Gemini API
      participant Mongo as MongoDB

      Client->>FastAPI: {"query": "..."}
      FastAPI-->>Client: SSE: status "Analyzing..."
      FastAPI->>Entry: load profile + history + embedding
      Entry->>Gemini: embed_content
      FastAPI-->>Client: SSE: status "Routing..."
      FastAPI->>Router: classify intent (Flash-Lite JSON)
      Router->>Gemini: generate_content (JSON mode)
      alt RAG_SEARCH
          FastAPI-->>Client: SSE: status "Searching..."
          FastAPI->>Retriever: ChromaDB query (top 8)
      end
      FastAPI-->>Client: SSE: status "Generating..."
      FastAPI->>Synth: generate_content_stream
      loop Token streaming
          Synth->>Gemini: stream
          Gemini-->>Synth: chunk
          Synth-->>FastAPI: yield token
          FastAPI-->>Client: SSE: token "..."
      end
      FastAPI->>Mongo: insert_many (user + assistant msgs)
      FastAPI->>Mongo: update session.updated_at
      FastAPI-->>Client: SSE: sources [...]
      FastAPI-->>Client: SSE: done
  ```

  ### Agent Nodes

  | Node | Model | Purpose |
  |---|---|---|
  | `entry_node` | `gemini-embedding-001` | Load user profile from MongoDB, fetch last 6 messages (3 turns), embed the query |
  | `router_node` | `gemini-2.5-flash-lite` | Classify intent → `RAG_SEARCH` · `CONVERSATIONAL` · `OUT_OF_SCOPE` · `DEEP_STUDY` (JSON mode) |
  | `retriever_vector_node` | — | Semantic search in ChromaDB with visibility + academic scope filters (top 8 chunks) |
  | `synthesis_node_stream` | `gemini-2.5-flash` | Streaming response generation — yields real tokens for SSE forwarding |

  ### Router Intents

  | Intent | Action | Example Query |
  |---|---|---|
  | `RAG_SEARCH` | Retriever → Synthesis with sources | "What is backpropagation?" |
  | `CONVERSATIONAL` | Skip retriever → Synthesis from history | "Thanks! Explain that more simply" |
  | `OUT_OF_SCOPE` | Instant polite rejection, no LLM call | "What's the weather?" |
  | `DEEP_STUDY` | _(Deferred)_ — requires Gemini Files API | "Summarize this entire video" |

  ### No Chunks Found Behavior

  When `retriever_vector_node` returns **zero results** from ChromaDB:
  - Sets `no_chunks_found = True` in the state
  - `synthesis_node_stream` detects this flag and instructs Gemini:
    *"No relevant course material was found. Tell the student politely and suggest rephrasing. Do NOT make up information."*
  - This prevents hallucination and gives the student actionable next steps

  ---

  ### 💬 Chat Session Endpoints

  > 🔒 **Auth Level:** Any authenticated user (JWT required)

  | Method | Endpoint | Description |
  |---|---|---|
  | `POST` | `/api/chat/sessions` | Create a new chat session |
  | `GET` | `/api/chat/sessions` | List all sessions for the user (newest first) |
  | `GET` | `/api/chat/sessions/{session_id}/history` | Load chat messages (chronological) |
  | `POST` | `/api/chat/sessions/{session_id}/message` | **Send message & stream AI response (SSE)** |

  #### `POST /api/chat/sessions` — Create Session

  ```json
  // Request
  { "title": "ML Revision", "file_id": "file_abc123..." }  // both optional

  // Response (201)
  { "session_id": "sess_b0b66e9d0f9e", "title": "ML Revision", "file_id": null, "created_at": "..." }
  ```

  > If `file_id` is provided, the file must exist and have `processing.status == "completed"`.

  #### `GET /api/chat/sessions` — List Sessions

  ```json
  // Response (200)
  { "sessions": [ { "session_id": "...", "title": "...", "updated_at": "..." } ], "count": 5 }
  ```

  #### `GET /api/chat/sessions/{session_id}/history` — Load History

  ```json
  // Response (200) — only returns messages you own
  { "messages": [ { "role": "user", "content": "...", "timestamp": "..." }, ... ], "count": 10 }
  ```

  | Error Case | Status |
  |---|---|
  | Session not found | `404` |
  | Not your session | `403` |

  ---

  ### 📡 SSE Streaming Endpoint

  #### `POST /api/chat/sessions/{session_id}/message`

  Sends a query and streams the AI response token-by-token via **Server-Sent Events**.

  ```json
  // Request
  { "query": "Explain backpropagation" }
  ```

  **SSE Event Format:**

  Every SSE line follows the format: `data: {"t": "<event_type>", "d": <payload>}`

  | Event Type | Payload | Description |
  |---|---|---|
  | `status` | `string` | Pipeline stage update ("Analyzing...", "Routing...", "Searching...", "Generating...") |
  | `token` | `string` | A single text chunk from Gemini streaming (the actual AI response, piece by piece) |
  | `sources` | `array` | List of source documents used (file_name, page_number, relevance_score, etc.) |
  | `done` | `""` | Stream complete — all tokens sent, messages persisted to MongoDB |
  | `error` | `string` | Error message if something failed |

  **Example SSE Stream:**

  ```
  data: {"t": "status", "d": "Analyzing your question..."}
  data: {"t": "status", "d": "Routing..."}
  data: {"t": "status", "d": "Searching knowledge base..."}
  data: {"t": "status", "d": "Generating answer..."}
  data: {"t": "token", "d": "Neural networks are "}
  data: {"t": "token", "d": "a fundamental concept "}
  data: {"t": "token", "d": "in artificial intelligence..."}
  data: {"t": "sources", "d": [{"file_name": "Module 02.pdf", "page_number": 5, "relevance_score": 0.87}]}
  data: {"t": "done", "d": ""}
  ```

  **Frontend Integration (JavaScript):**

  ```js
  const response = await fetch(`/api/chat/sessions/${sessionId}/message`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: 'Explain backpropagation' }),
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let aiResponse = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const lines = decoder.decode(value).split('\n');
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const { t, d } = JSON.parse(line.slice(6));
        if (t === 'token')  aiResponse += d;   // append to chat bubble
        if (t === 'status') showStatus(d);      // update status indicator
        if (t === 'sources') showSources(d);    // render source citations
        if (t === 'done')   finalize();          // mark complete
      }
    }
  }
  ```

  **What Happens After Streaming:**

  Once the `done` event fires, the backend has already:
  1. Saved both the user message and AI response to `chat_history` collection
  2. Updated the session's `updated_at` timestamp
  3. No additional API call needed — the history is already persisted




  ## 🔗 Full Upload → Ingest → Search Chain

  ```mermaid
  sequenceDiagram
      participant UI as React UI
      participant API as FastAPI (upload.py)
      participant BG as BackgroundTask (ingestion.py)
      participant Mongo as MongoDB
      participant Chroma as ChromaDB
      participant Gemini as Gemini API

      UI->>API: POST /api/upload/file
      API->>API: Permission check + SHA-256 dedup
      API->>Mongo: Insert file_metadata (status: pending)
      API->>UI: 202 Accepted
      API->>BG: add_task(process_file_background)

      BG->>Mongo: Lookup file_metadata by file_id
      BG->>Mongo: Set status: processing
      BG->>BG: PyMuPDF text extract (per page)
      alt Page < 50 chars (scanned)
          BG->>Gemini: Vision OCR (flash-lite → flash fallback)
      end
      BG->>BG: Chunk text (800 chars, 100 overlap)
      BG->>Gemini: Batch embed (gemini-embedding-001)
      BG->>Chroma: Upsert chunks + academic metadata
      BG->>Mongo: Set status: completed (chunk_count, page_count)
  ```

  ---

  ## 🔌 Shared Dependencies

  > **Rule:** Single source of truth for all DB connections. Never create separate client instances.

  | Module | Exports | Used By |
  |---|---|---|
  | `database/mongo.py` | `get_db()` → Motor DB instance | `auth.py`, `admin.py`, `upload.py`, `ingestion.py`, `chat.py`, `nodes.py` |
  | `database/chroma.py` | `get_chroma_collection()` → campus_vectors | `ingestion.py`, `nodes.py` (retriever_vector_node) |

  ---

  ## 📂 Project Structure

  ```
  backend/
  ├── main.py                          ← App entry point, lifespan, router mounts
  ├── .env                             ← MONGO_URI, JWT_SECRET, GEMINI_API_KEY
  ├── core/
  │   ├── config.py                    ← Pydantic settings (env vars)
  │   └── security.py                  ← JWT encode/decode, password hashing
  ├── database/
  │   ├── mongo.py                     ← Motor async MongoDB singleton
  │   └── chroma.py                    ← ChromaDB PersistentClient singleton
  ├── models/
  │   └── schemas.py                   ← Pydantic models & enums
  ├── api/
  │   ├── dependencies.py              ← get_current_user dependency
  │   ├── agent/                       ← 🧠 LangGraph AI agent module
  │   │   ├── __init__.py
  │   │   ├── state.py                 ← GraphState TypedDict + dataclasses
  │   │   ├── nodes.py                 ← 4 production nodes (entry, router, retriever, synthesis)
  │   │   └── graph.py                 ← LangGraph StateGraph for visualization/testing
  │   ├── routers/
  │   │   ├── auth.py                  ← Register, Login, /users/me
  │   │   ├── admin.py                 ← Grant/revoke upload, list users
  │   │   ├── upload.py                ← File upload + listing endpoints
  │   │   └── chat.py                  ← 💬 Chat sessions + SSE streaming endpoint
  │   └── services/
  │       └── ingestion.py             ← Background AI ingestion pipeline
  ├── scripts/
  │   ├── inspect_chroma.py            ← ChromaDB inspection utility
  │   └── test_sse_chat.py             ← E2E chat SSE test script
  ├── storage/
  │   ├── uploads/{pdfs,images,videos}/
  │   └── temp/                        ← SHA-256 dedup staging
  └── chroma_data/                     ← Persistent vector DB (auto-created)
  ```

  ---

  ## 📦 Tech Stack

  | Component | Technology |
  |---|---|---|
  | Framework | FastAPI |
  | Database | MongoDB (Motor async driver) |
  | Vector DB | ChromaDB (PersistentClient, cosine HNSW) |
  | AI Agent | LangGraph + langchain-core |
  | Auth | PyJWT + bcrypt |
  | File I/O | aiofiles |
  | Text Extraction | PyMuPDF (`fitz`) |
  | Vision OCR | Gemini 2.5 Flash-Lite (fallback: Gemini 2.5 Flash) |
  | Router LLM | Gemini 2.5 Flash-Lite (JSON mode) |
  | Synthesis LLM | Gemini 2.5 Flash (streaming) |
  | Embeddings | Gemini Embedding API (`gemini-embedding-001`) |
  | Chunking | LangChain `RecursiveCharacterTextSplitter` |
  | Streaming | Server-Sent Events (SSE) |
  | Deps | UV package manager |

  ---

  ## 🚀 Quick Test

  ### Upload & Ingestion

  **1. Login & get token:**

  ```bash
  curl -X POST http://localhost:8000/api/auth/login \
    -d "username=jatin.faculty@tcet.com&password=secret123" \
    -H "Content-Type: application/x-www-form-urlencoded"
  ```

  **2. Upload a file (triggers background ingestion):**

  ```bash
  curl -X POST http://localhost:8000/api/upload/file \
    -H "Authorization: Bearer <YOUR_JWT_TOKEN>" \
    -F "file=@./test_upload_files/Module 02.pdf" \
    -F "year=3" \
    -F "branch=COMP" \
    -F "subject=Machine Learning" \
    -F "doc_type=notes" \
    -F "unit=2"
  # Returns 202 Accepted — ingestion starts in background
  ```

  **3. Wait ~30 seconds, then check status:**

  ```bash
  curl -H "Authorization: Bearer <TOKEN>" http://localhost:8000/api/files
  # processing.status should be "completed"
  # processing.chunk_count shows total chunks created
  ```

  ### 💬 Chat (SSE Streaming)

  **4. Create a chat session:**

  ```bash
  curl -X POST http://localhost:8000/api/chat/sessions \
    -H "Authorization: Bearer <TOKEN>" \
    -H "Content-Type: application/json" \
    -d '{"title": "ML Revision"}'
  # Returns: { "session_id": "sess_abc123...", ... }
  ```

  **5. Send a message (SSE streaming response):**

  ```bash
  curl -N -X POST http://localhost:8000/api/chat/sessions/<SESSION_ID>/message \
    -H "Authorization: Bearer <TOKEN>" \
    -H "Content-Type: application/json" \
    -d '{"query": "Explain backpropagation from the uploaded notes"}'
  # Streams SSE events: status → status → token → token → ... → sources → done
  ```

  > ⚡ Use `curl -N` (no-buffer) to see tokens stream in real-time.

  **6. Verify chat history:**

  ```bash
  curl -H "Authorization: Bearer <TOKEN>" \
    http://localhost:8000/api/chat/sessions/<SESSION_ID>/history
  # Returns both user and assistant messages, chronologically sorted
  ```

  **7. Run the full automated test:**

  ```bash
  uv run python scripts/test_sse_chat.py
  # Tests 3 flows: RAG → Conversational → Out-of-Scope
  # Results written to scripts/test_results.txt
  ```

  ---

  ### Verify ChromaDB

  ```python
  import chromadb
  c = chromadb.PersistentClient(path="./chroma_data")
  col = c.get_collection("campus_vectors")
  print(f"Total chunks: {col.count()}")
  result = col.peek(limit=1)
  print(result["metadatas"][0])  # Should show year, branch, subject, etc.
  ```

  ### Check MongoDB

  ```bash
  mongosh
  use campus_ai
  db.file_metadata.find().pretty()
  db.chat_sessions.find().pretty()
  db.chat_history.find().pretty()
  ```

  ---

  ## ✅ Verified E2E Test Results

  ### Upload & Ingestion

  | Test | Status |
  |---|---|
  | Login & JWT | ✅ Pass |
  | PDF Upload (202 Accepted) | ✅ Pass |
  | Background Ingestion → completed | ✅ Pass (35 chunks, 22 pages) |
  | ChromaDB chunks with full metadata | ✅ Pass (year, branch, subject, doc_type, file_type, uploaded_by) |
  | Dedup (re-upload same file) | ✅ Pass (200, "File already exists") |
  | Filter `?branch=COMP` | ✅ Pass (1 result) |
  | Filter `?branch=ECE` | ✅ Pass (0 results) |

  ### Chat Sessions

  | Test | Status |
  |---|---|
  | Create session (with/without file_id) | ✅ Pass |
  | List sessions (newest first) | ✅ Pass |
  | Load history (ownership verified) | ✅ Pass |
  | Unauthorized access attempt | ✅ 403 Forbidden |

  ### LangGraph SSE Chat

  | Test | Intent | Tokens | Chars | DB | Status |
  |---|---|---|---|---|---|
  | "Explain neural networks" | CONVERSATIONAL | 17 chunks | 3,758 | 2 msgs ✅ | Detailed markdown response |
  | "Explain that more simply" | CONVERSATIONAL | 18 chunks | 3,522 | 4 msgs ✅ | Used chat history context |
  | "What is the weather?" | OUT_OF_SCOPE | 2 chunks | 146 | 6 msgs ✅ | Polite rejection |

  ---

  ## 🔧 How to Operate ChromaDB

  ```bash
  # Summary (default) — shows all files, chunk counts, pages
  uv run python scripts/inspect_chroma.py

  # Peek at first N chunks with full text
  uv run python scripts/inspect_chroma.py --peek 5

  # All chunks for a specific file
  uv run python scripts/inspect_chroma.py --file_id file_04a24c917017469db1c8fd5384a6f60a

  # Text search across all chunks
  uv run python scripts/inspect_chroma.py --search "neural network"

  # Metadata breakdown (unique years, branches, subjects, etc.)
  uv run python scripts/inspect_chroma.py --stats

  # Export everything as JSON
  uv run python scripts/inspect_chroma.py --export > chunks.json
  ```
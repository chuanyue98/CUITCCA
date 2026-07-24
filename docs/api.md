# API Reference

Base URL: `/`

All endpoints are prefixed as shown. The FastAPI app also exposes auto-generated interactive docs at `/docs` (Swagger UI) and `/redoc` (ReDoc), which are the live source of truth.

## Chat & Query

### POST /graph/chat_stream
Stream a QA answer using the active conversation context (session-scoped chat history).

**Auth:** None (rate-limited per IP).

**Request:** `application/x-www-form-urlencoded`
- `query` (string, required, max_length=5000): The user's question.

**Response:** `text/plain` (token-level streaming body).

**Notes:** Uses session-scoped chat history. Abortable via `AbortController`.

### POST /graph/query_stream
Stream a QA answer without conversation context (stateless).

**Auth:** None (rate-limited per IP).

**Request:** `application/x-www-form-urlencoded`
- `query` (string, required, max_length=5000)

**Response:** `text/plain` (token-level streaming body).

**Notes:** Stateless — does not update chat history.

### POST /graph/query
Non-streaming QA answer.

**Auth:** None (rate-limited per IP).

**Request:** `application/x-www-form-urlencoded`
- `query` (string, required, max_length=5000)

**Response:** JSON (`QueryResponse`)
```json
{ "response": "..." }
```

### POST /graph/workflow_query
Non-streaming QA answer via QAWorkflow (session-scoped history).

**Auth:** None (rate-limited per IP).

**Request:** `application/x-www-form-urlencoded`
- `query` (string, required, max_length=5000)

**Response:** JSON (`QueryResponse`)

### POST /graph/workflow_query_stream
Streaming QA answer via QAWorkflow (stateless).

**Auth:** None (rate-limited per IP).

**Request:** `application/x-www-form-urlencoded`
- `query` (string, required, max_length=5000)

**Response:** `text/plain` (token-level streaming body).

### POST /graph/query_sources
Fetch source nodes for the last query in the current session.

**Auth:** None.

**Request:** None.

**Response:** JSON (`QuerySourcesResponse`)
```json
{
  "source_nodes": [
    { "id": "...", "text": "...", "score": 0.85 }
  ]
}
```

**Notes:** Returns 400 if no query has been made in the current session.

### POST /graph/create
Reset the server-side conversation context for the current session.

**Auth:** None.

**Request:** None.

**Response:** JSON `{ "status": "ok" }`

### POST /graph/query_history
Return conversation history for the current session.

**Auth:** None.

**Request:** None.

**Response:** JSON
```json
{
  "history": [
    { "role": "USER", "content": "..." },
    { "role": "ASSISTANT", "content": "..." }
  ]
}
```

**Notes:** Returns 404 if no chat graph is available for the session.

### POST /graph/agent
Legacy agent endpoint (deprecated, routes to QAWorkflow). No session history.

**Auth:** None.

### POST /graph/query_router
Internal QA endpoint via QAWorkflow (no session history).

**Auth:** None.

### WS /graph/query
WebSocket QA endpoint. Sends a plain-text response per query message.

**Auth:** API key required (`CUITCCA_API_KEY` passed as `token` query parameter).

**Protocol:** Send a query text, receive a plain-text response. Closes on disconnect.

## Index Management

### GET /index/
Health check endpoint.

**Response:** JSON `{ "status": "ok", "load": "ok" }`

### GET /index/list
List all index names.

**Response:** JSON (`IndexListResponse`)
```json
{ "indexes": ["index_a", "index_b"] }
```

### POST /index/create
Create a new index.

**Request:** `application/x-www-form-urlencoded`
- `index_name` (string, required, max_length=100): Will be sanitized (non-alphanumeric chars replaced with `_`).

**Response:** JSON
```json
{ "status": "success", "msg": "index <name> created", "index_name": "<name>" }
```

**Notes:** Returns 400 if the index already exists.

### GET /index/{index_name}/info
List all nodes in an index.

**Response:** JSON `{ "docs": [...] }`

### POST /index/{index_name}/query
QA query scoped to a specific index.

**Request:** `application/x-www-form-urlencoded`
- `query` (string, required, max_length=5000)

**Response:** JSON (`QueryResponse`)

### POST /index/delete
Delete an index by name.

**Request:** `application/x-www-form-urlencoded`
- `index_name` (string, required, max_length=100)

**Response:** JSON `{ "status": "deleted" }`

### POST /index/{index_name}/uploadFile
Upload and parse a single file into the index.

**Request:** `multipart/form-data`
- `file` (file, required): Supported types: `.txt`, `.pdf`, `.md`, `.csv`, `.xlsx`, `.docx`. Max 200 MB.

**Response:** JSON (`UploadResponse`) `{ "status": "inserted" }`

### POST /index/{index_name}/uploadFiles
Upload and parse multiple files into the index (single batch insert, generates one summary).

**Request:** `multipart/form-data`
- `files` (file[], required): Same supported types and size limit as `uploadFile`.

**Response:** JSON (`UploadResponse`) `{ "status": "inserted" }`

### POST /index/{index_name}/upload_file_by_QA
Generate QA pairs from a file and ingest them into the index.

**Request:** `multipart/form-data`
- `file` (file, required)
- `prompt` (string, optional, max_length=5000)

**Response:** JSON `{ "status": "ok" }`

### POST /index/{index_name}/insertdoc
Insert raw text as a document node.

**Request:** `application/x-www-form-urlencoded`
- `text` (string, required, max_length=50000)
- `doc_id` (string, optional, max_length=200)

**Response:** JSON `{ "status": "ok" }`

### POST /index/{index_name}/update
Update a node's text content by node ID.

**Request:** `application/x-www-form-urlencoded`
- `nodeId` (string, required): Node ID as a query string parameter.
- `text` (string, required, max_length=10000)

**Response:** JSON `{ "status": "updated" }`

**Notes:** Returns 404 if the node does not exist.

### POST /index/{index_name}/deleteDoc
Delete all nodes belonging to a document by `doc_id`.

**Request:** `application/x-www-form-urlencoded`
- `doc_id` (string, required, max_length=200): Passed as a query string parameter.

**Response:** JSON `{ "status": "deleted" }`

### POST /index/{index_name}/deleteNode
Delete a single node by `node_id`.

**Request:** `application/x-www-form-urlencoded`
- `node_id` (string, required, max_length=200): Passed as a query string parameter.

**Response:** JSON `{ "status": "deleted" }`

### POST /index/{index_name}/save
Persist index to disk.

**Response:** JSON `{ "status": "ok" }`

### GET /index/{index_name}/get_summary
Get the index summary text.

**Response:** JSON `{ "summary": "..." }`

### POST /index/{index_name}/set_summary
Set the index summary text.

**Request:** `application/x-www-form-urlencoded`
- `summary` (string, required, max_length=5000)

**Response:** JSON `{ "status": "ok", "summary": "..." }`

### POST /index/{index_name}/generate_summary
Auto-generate and save an index summary.

**Response:** JSON `{ "status": "ok", "summary": "..." }`

### POST /index/{index_name}/getfile
Export the index as a plain-text file.

**Response:** JSON `{ "status": "ok" }`

### POST /index/{index_name}/evaluator
Run a response evaluator QA query against the index (internal debug endpoint).

**Request:** `application/x-www-form-urlencoded`
- `query` (string, required, max_length=5000)

**Response:** JSON `{ "result": "..." }`

## Response Synthesizer

### POST /response/{index_name}/query
Synthesize a response using selectable `ResponseMode` and `PromptType`.

**Request:** `application/x-www-form-urlencoded`
- `query` (string, required): The user's question.
- `response_mode` (string, required): See `/docs` for enum values.
- `prompt_type` (string, required): See `/docs` for enum values.

**Response:** JSON (`QueryResponse`)

## Management

### GET /manage/stats
Return access statistics.

**Auth:** API key required (`CUITCCA_API_KEY`).

**Response:** JSON (`StatsResponse`)
```json
{
  "total_visits": 0,
  "ip_count": 0,
  "user_visits": {},
  "endpoint_visits": {}
}
```

### POST /manage/feedback
Submit user feedback.

**Auth:** API key required (`CUITCCA_API_KEY`).

**Request:** JSON body
```json
{
  "email": "user@example.com",
  "message": "反馈内容"
}
```

**Response:** JSON (`FeedbackResponse`) `{ "message": "Feedback received" }`

### GET /manage/feedback
List recent user feedback entries.

**Auth:** API key required (`CUITCCA_API_KEY`).

**Query Parameters:**
- `limit` (int, default=100)

**Response:** JSON (`FeedbackListResponse`)
```json
{
  "feedback": [
    {
      "created_at": "...",
      "client_ip": "...",
      "email": null,
      "message": "..."
    }
  ]
}
```

### POST /manage/env
Hot-update `OPENAI_API_KEY` and `OPENAI_API_BASE` in `.env` and reload the LLM backend.

**Auth:** API key required (`CUITCCA_API_KEY`).

**Request:** `application/x-www-form-urlencoded`
- `openai_api_key` (string, required, max_length=200)
- `openai_base_url` (string, optional, default=`https://api.openai.com/v1`, max_length=500)

**Response:** JSON (`EnvUpdateResponse`) `{ "message": "环境变量已更新" }`

**Notes:** Triggers an audit log entry with the last 4 characters of the key. Reloads `Settings.llm` atomically.

## WebSocket

### WS /graph/query
Per-session WebSocket QA endpoint.

**Auth:** API key required — pass `token` query parameter matching `CUITCCA_API_KEY`.

**Protocol:** Send plain text query, receive plain text response. Connection closes on `WebSocketDisconnect` or server error.

## Models

| Model | Fields |
|---|---|
| `QueryResponse` | `response: str` |
| `QuerySourcesResponse` | `source_nodes: list[SourceNode]` |
| `SourceNode` | `id: str`, `text: str`, `score: float | None` |
| `UploadResponse` | `status: str` |
| `IndexListResponse` | `indexes: list[str]` |
| `StatsResponse` | `total_visits: int`, `ip_count: int`, `user_visits: dict`, `endpoint_visits: dict` |
| `FeedbackResponse` | `message: str` |
| `FeedbackListResponse` | `feedback: list[FeedbackEntry]` |
| `FeedbackEntry` | `created_at: str`, `client_ip: str`, `email: str | None`, `message: str` |
| `EnvUpdateResponse` | `message: str` |

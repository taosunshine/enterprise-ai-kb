# Security and operations

## Upload limits

Uploads accept PDF, DOCX, Markdown, TXT, CSV, HTML, PNG, JPEG, and WebP files. The API validates
the suffix and file signature where applicable, rejects binary-looking text files, and streams
files with a hard byte limit.

Configure:

```dotenv
UPLOAD_MAX_BYTES=26214400
UPLOAD_MAX_DOCUMENTS_PER_KB=100
UPLOAD_RATE_LIMIT=10
UPLOAD_RATE_WINDOW_SECONDS=60
```

## Rate limits

Authentication, document upload, and chat rate-limit events are stored in PostgreSQL. A rejected
request returns HTTP `429` with a `Retry-After` header.

```dotenv
AUTH_RATE_LIMIT=10
AUTH_RATE_WINDOW_SECONDS=60
CHAT_RATE_LIMIT=30
CHAT_RATE_WINDOW_SECONDS=60
```

## Audit logs

Authenticated users can query their own operation history:

```http
GET /api/audit-logs?limit=100
```

Audit records contain operation metadata only. Passwords, tokens, API keys, questions, answers,
and document content are not recorded.

## Secret files

For Docker deployments, place one value per file in `secrets/secret_key`,
`secrets/llm_api_key`, and optionally `secrets/vision_api_key` and `secrets/rerank_api_key`.
Compose mounts the directory read-only and configures `DATABASE_URL_FILE`, `SECRET_KEY_FILE`,
`LLM_API_KEY_FILE`, `VISION_API_KEY_FILE`, and `RERANK_API_KEY_FILE`.

Environment variables remain available as a local-development fallback. Secret files and `.env`
files are ignored by Git.

## Database backups

The `backup` Compose service creates a compressed PostgreSQL dump immediately after startup and
then once per configured interval:

```dotenv
BACKUP_INTERVAL_SECONDS=86400
BACKUP_RETENTION_DAYS=7
```

Backups are written to the ignored local `backups/` directory.

Restore a selected backup into a stopped or disposable database after verifying its path:

```powershell
docker compose exec -T backup sh -c "gzip -dc /backups/knowledge_base_TIMESTAMP.sql.gz" |
  docker compose exec -T postgres psql -U knowledge -d knowledge_base
```

Regularly test restores in a separate environment. A backup that has never been restored is not
yet a proven backup.

## Continuous quality gate

The automated gate runs backend tests, Ruff, and the frontend production build:

```powershell
.\scripts\quality-gate.ps1 -SkipLiveEvaluation
```

The full gate additionally creates an isolated knowledge base, uploads every supported document
from a directory, runs the real-business evaluation set three times, and fails when any configured
threshold is missed:

```powershell
.\scripts\quality-gate.ps1 `
  -DocumentsDir "C:\path\to\knowledge-base-documents"
```

Supported formats are PDF, DOCX, Markdown, TXT, CSV, HTML, PNG, JPEG, and WebP. Evaluation cases may specify
`expected_documents` so citation accuracy requires both relevant evidence and the correct source
document. GitHub Actions runs the automated gate on every push and pull request; the live RAG gate
remains local because it requires private model credentials and business documents.

## OCR, tables, and image understanding

PDF and DOCX tables are extracted into Markdown table chunks. Pages with little extractable text
are rendered and sent to the configured vision model for OCR. Embedded document images and
standalone PNG, JPEG, and WebP files are converted into searchable factual descriptions.

The vision API must implement OpenAI-compatible multimodal chat completions. It reuses the LLM
configuration by default, or can be configured separately:

```dotenv
VISION_ENABLED=true
VISION_API_KEY=
VISION_BASE_URL=
VISION_MODEL=
VISION_TIMEOUT_SECONDS=90
VISION_MAX_IMAGES_PER_DOCUMENT=20
OCR_MIN_PAGE_CHARACTERS=80
```

Vision failures degrade gracefully: text and locally extracted tables continue processing. Limit
the number of analyzed images to control latency and cost, and include scanned pages, tables, and
charts in the live quality-gate dataset before production use.

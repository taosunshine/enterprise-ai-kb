# Security and operations

## Upload limits

Uploads accept PDF, Markdown, and TXT files. The API validates the suffix, rejects invalid PDF
headers and binary-looking text files, and streams files with a hard byte limit.

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
`secrets/llm_api_key`, and optionally `secrets/rerank_api_key`. Compose mounts the directory
read-only and configures `DATABASE_URL_FILE`, `SECRET_KEY_FILE`, `LLM_API_KEY_FILE`, and
`RERANK_API_KEY_FILE`.

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

Supported formats are PDF, DOCX, Markdown, TXT, CSV, and HTML. Evaluation cases may specify
`expected_documents` so citation accuracy requires both relevant evidence and the correct source
document. GitHub Actions runs the automated gate on every push and pull request; the live RAG gate
remains local because it requires private model credentials and business documents.

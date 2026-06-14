# Local secrets

Place one secret value per file in this directory:

- `secret_key`
- `llm_api_key`
- `rerank_api_key` (optional)
- `database_url` (optional production database connection string)

The secret files are ignored by Git and mounted read-only into the backend and worker containers.
Environment variables remain supported as a local-development fallback.

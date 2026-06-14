.PHONY: up down test eval quality

up:
	docker compose up --build

down:
	docker compose down

test:
	cd backend && pytest

eval:
	cd backend && python -m evaluation.evaluate --document "$(DOCUMENT)"

quality:
	powershell -ExecutionPolicy Bypass -File scripts/quality-gate.ps1 -DocumentsDir "$(DOCUMENTS_DIR)"

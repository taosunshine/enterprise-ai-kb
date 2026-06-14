param(
    [string]$DocumentsDir = "",
    [string]$Dataset = "backend/evaluation/datasets/huawei_business_multi_document_2026_06_14.json",
    [int]$Rounds = 3,
    [switch]$SkipLiveEvaluation
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Push-Location "$root/backend"
try {
    & ".\.venv\Scripts\python.exe" -m pytest -q
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & ".\.venv\Scripts\ruff.exe" check app tests evaluation alembic
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}

Push-Location "$root/frontend"
try {
    npm run build
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}

if (-not $SkipLiveEvaluation) {
    if (-not $DocumentsDir) {
        throw "DocumentsDir is required unless -SkipLiveEvaluation is supplied."
    }
    Push-Location "$root/backend"
    try {
        & ".\.venv\Scripts\python.exe" -m evaluation.evaluate `
            --dataset "$root/$Dataset" `
            --documents-dir "$DocumentsDir" `
            --rounds $Rounds `
            --fail-under
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    finally {
        Pop-Location
    }
}

# Windows (PowerShell) :  .\make.ps1 setup | serve | n8n | test | lint | eval
# Si l'exécution de scripts est bloquée :
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
param([string]$cmd = "help")

$venv = ".venv"
$bin = "$venv\Scripts"

switch ($cmd) {
    "setup" {
        py -3 -m venv $venv
        & "$bin\python.exe" -m pip install -U pip
        & "$bin\pip.exe" install -r requirements-dev.txt
        if (-not (Test-Path .env)) { Copy-Item .env.example .env }
        & "$bin\pre-commit.exe" install
        Write-Host "OK. Activez l'environnement : .\.venv\Scripts\Activate.ps1"
    }
    "serve" { & "$bin\uvicorn.exe" api.main:app --reload --port 8000 }
    "n8n"   { $env:N8N_USER_FOLDER = "$PWD\.n8n"; npx --yes n8n@2.42.3 }
    "test"  { & "$bin\pytest.exe" }
    "lint"  { & "$bin\ruff.exe" check . }
    "fmt"   { & "$bin\ruff.exe" check --fix .; & "$bin\ruff.exe" format . }
    "eval"  { & "$bin\python.exe" -m eval.eval_router; & "$bin\python.exe" -m eval.eval_retrieval }
    "index" { & "$bin\python.exe" -m rag.build_index --force }
    "index-dense" {
        & "$bin\pip.exe" install -r requirements-rag.txt
        & "$bin\python.exe" -m rag.build_index --force --dense --model BAAI/bge-m3
    }
    default {
        Write-Host "Commandes : setup, serve, n8n, test, lint, fmt, eval, index, index-dense"
    }
}

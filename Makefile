# Linux / macOS. Sous Windows : .\make.ps1 <commande>
PY ?= python3
VENV := .venv
BIN := $(VENV)/bin

.PHONY: help setup serve n8n test lint fmt eval index index-dense clean

help:
	@echo "setup  : crée .venv, installe les dépendances, copie .env"
	@echo "serve  : lance l'API sur http://localhost:8000 (docs : /docs)"
	@echo "n8n    : lance n8n sur http://localhost:5678 (Node.js 24 ou plus requis)"
	@echo "test   : lance les tests"
	@echo "lint   : vérifie le style (ruff)"
	@echo "eval   : lance les évaluations disponibles"
	@echo "index  : ingère le corpus, crée les chunks A et B (BM25)"
	@echo "index-dense : + embeddings BGE-M3 (installe requirements-rag.txt)"

setup:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -U pip
	$(BIN)/pip install -r requirements-dev.txt
	@test -f .env || cp .env.example .env
	$(BIN)/pre-commit install || true
	@echo "OK. Activez l'environnement : source $(VENV)/bin/activate"

serve:
	$(BIN)/uvicorn api.main:app --reload --port 8000

n8n:
	N8N_USER_FOLDER=$(CURDIR)/.n8n npx --yes n8n@2.42.3

test:
	$(BIN)/pytest

lint:
	$(BIN)/ruff check .

fmt:
	$(BIN)/ruff check --fix . && $(BIN)/ruff format .

eval:
	$(BIN)/python -m eval.eval_router
	$(BIN)/python -m eval.eval_retrieval

index:
	$(BIN)/python -m rag.build_index --force

index-dense:
	$(BIN)/pip install -r requirements-rag.txt
	$(BIN)/python -m rag.build_index --force --dense --model BAAI/bge-m3

clean:
	rm -rf .pytest_cache .ruff_cache logs

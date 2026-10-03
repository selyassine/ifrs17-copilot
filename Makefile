# Linux / macOS. Sous Windows : .\make.ps1 <commande>
PY ?= python3
VENV := .venv
BIN := $(VENV)/bin

.PHONY: help setup serve n8n test lint fmt eval index clean

help:
	@echo "setup  : crée .venv, installe les dépendances, copie .env"
	@echo "serve  : lance l'API sur http://localhost:8000 (docs : /docs)"
	@echo "n8n    : lance n8n sur http://localhost:5678 (Node.js requis)"
	@echo "test   : lance les tests"
	@echo "lint   : vérifie le style (ruff)"
	@echo "eval   : lance les évaluations disponibles"
	@echo "index  : construit l'index RAG (S2)"

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
	N8N_USER_FOLDER=$(CURDIR)/.n8n npx n8n

test:
	$(BIN)/pytest

lint:
	$(BIN)/ruff check .

fmt:
	$(BIN)/ruff check --fix . && $(BIN)/ruff format .

eval:
	$(BIN)/python -m eval.eval_router

index:
	@echo "Arrive en S2 : python -m rag.build_index"

clean:
	rm -rf .pytest_cache .ruff_cache logs

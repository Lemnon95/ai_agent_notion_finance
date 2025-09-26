# =========================
# Makefile – Utility per sviluppo Python + Bot Telegram + Notion
# =========================
# Questo file automatizza le attività tipiche del progetto:
# - Creazione/uso dell'ambiente virtuale
# - Installazione dipendenze
# - Esecuzione dell'applicazione e degli script
# - Linting/formatting, type-checking, test
# - Verifiche sullo schema Notion e dump tassonomia
# - Esecuzione del bot Telegram in locale (polling)
#
# Nota: i comandi che usano l'ambiente virtuale attivano la venv inline.
#       Non è necessario fare `source .venv/bin/activate` manualmente.
# =========================

# Interprete Python usato dal progetto
PYTHON = python3

# Directory dell'ambiente virtuale
VENV = .venv

# Shortcut per "attivare" l'ambiente virtuale all'interno di una riga di Make
# In pratica esegue i comandi successivi con il PATH della venv
ACTIVATE = . $(VENV)/bin/activate;

# Forziamo l'uso di /usr/bin/env bash per compatibilità con comandi bash
SHELL := /usr/bin/env bash

# Target di default: mostra l'elenco comandi
.DEFAULT_GOAL := help

# Segnaliamo a make che questi target non producono file con lo stesso nome
.PHONY: help venv install run clean format lint type test check \
        schema-verify taxonomy-dump smoke-llm smoke-llm-batch bot-env bot

# -------------------------------------------------------------------
# HELP
# -------------------------------------------------------------------
help: ## Mostra questo aiuto
	@echo "Comandi disponibili:"
	@grep -E '^[a-zA-Z0-9_.-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "} {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# -------------------------------------------------------------------
# AMBIENTE VIRTUALE & DIPENDENZE
# -------------------------------------------------------------------

venv: ## Crea la venv e installa le dipendenze (pip + requirements.txt)
	$(PYTHON) -m venv $(VENV)
	$(ACTIVATE) pip install -U pip
	$(ACTIVATE) pip install -r requirements.txt

install: ## Re-installa le dipendenze nella venv già esistente
	$(ACTIVATE) pip install -r requirements.txt

# -------------------------------------------------------------------
# ESECUZIONE APPLICAZIONE & PULIZIA
# -------------------------------------------------------------------

run: ## Avvia l'applicazione principale (main.py) dentro la venv
	$(ACTIVATE) $(PYTHON) main.py

clean: ## Pulisce venv, cache Python e log temporanei
	rm -rf $(VENV) __pycache__ **/__pycache__ *.pyc *.pyo *.pyd *.log

# -------------------------------------------------------------------
# QUALITÀ DEL CODICE: Linting, Formatting, Tipi, Test
# -------------------------------------------------------------------
# format: applica fix automatici con ruff e formatta con black
# lint:   controlla stile con ruff e verifica che black sia già applicato
# type:   type-checking statico con mypy
# test:   esegue i test con pytest
# check:  esegue lint + type + test in sequenza (comando completo)

format: ## Applica fix (ruff) e formatta (black)
	$(ACTIVATE) $(PYTHON) -m ruff check . --fix
	$(ACTIVATE) $(PYTHON) -m black .

lint: ## Controlla lo stile (ruff) e che il codice sia già formattato (black --check)
	$(ACTIVATE) $(PYTHON) -m ruff check .
	$(ACTIVATE) $(PYTHON) -m black --check .

type: ## Type checking con mypy
	$(ACTIVATE) $(PYTHON) -m mypy .

test: ## Esegue i test (pytest)
	$(ACTIVATE) $(PYTHON) -m pytest -q

check: ## Esegue lint + type + test (pipeline qualità)
	@$(MAKE) lint
	@$(MAKE) type
	@$(MAKE) test

# -------------------------------------------------------------------
# NOTION: Verifica Schema e Tassonomia + Smoke LLM
# -------------------------------------------------------------------
# Questi target usano script Python nella cartella "scripts/".
# PYTHONPATH è impostato per permettere import come se si fosse nella root del progetto.

schema-verify: ## Verifica lo schema del DB Notion (tipi base, relation non vuote, ecc.)
	$(ACTIVATE) PYTHONPATH=$(CURDIR) $(PYTHON) scripts/schema_verify.py

taxonomy-dump: ## Stampa liste effettive lette da Notion (Accounts/Outcome/Income)
	$(ACTIVATE) PYTHONPATH=$(CURDIR) $(PYTHON) scripts/taxonomy_dump.py

smoke-llm: ## Scrive una pagina di test su Notion usando LLM (single)
	$(ACTIVATE) PYTHONPATH=$(CURDIR) $(PYTHON) scripts/smoke_llm.py

smoke-llm-batch: ## Variante batch dello smoke test LLM su Notion
	$(ACTIVATE) PYTHONPATH=$(CURDIR) $(PYTHON) scripts/smoke_llm_batch.py

# -------------------------------------------------------------------
# BOT TELEGRAM (Polling locale)
# -------------------------------------------------------------------
# BOT_SCRIPT: entrypoint dello script che avvia il bot in modalità polling
PY := PYTHONPATH=. python3
BOT_SCRIPT := scripts/run_bot.py

bot-env: ## Avvia il bot leggendo le variabili da .env (fallisce se .env manca)
	@if [ ! -f .env ]; then echo "Error: .env non trovato"; exit 1; fi
	set -a; . ./.env; set +a; \
	if [ -f .venv/bin/activate ]; then . .venv/bin/activate; fi; \
	$(PY) $(BOT_SCRIPT)

bot: ## Avvia il bot assicurandosi che TELEGRAM_BOT_TOKEN sia impostata nell'ambiente
	@if [ -f .env ]; then set -a; . ./.env; set +a; fi; \
	if [ -z "$$TELEGRAM_BOT_TOKEN" ]; then \
		echo "Error: TELEGRAM_BOT_TOKEN non impostato."; \
		exit 1; \
	fi; \
	if [ -f .venv/bin/activate ]; then . .venv/bin/activate; fi; \
	$(PY) $(BOT_SCRIPT)

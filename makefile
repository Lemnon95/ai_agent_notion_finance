PYTHON=python3
VENV=.venv
ACTIVATE=. $(VENV)/bin/activate;

.PHONY: venv install run clean

venv:
	$(PYTHON) -m venv $(VENV)
	$(ACTIVATE) pip install -U pip
	$(ACTIVATE) pip install -r requirements.txt

install:
	$(ACTIVATE) pip install -r requirements.txt

run:
	$(ACTIVATE) $(PYTHON) main.py

clean:
	rm -rf $(VENV) __pycache__ **/__pycache__ *.pyc *.pyo *.pyd *.log


# Linting and Testing

format:
	$(ACTIVATE) $(PYTHON) -m ruff check . --fix
	$(ACTIVATE) $(PYTHON) -m black .

lint:
	$(ACTIVATE) $(PYTHON) -m ruff check .
	$(ACTIVATE) $(PYTHON) -m black --check .
type:
	$(ACTIVATE) $(PYTHON) -m mypy .
test:
	$(ACTIVATE) $(PYTHON) -m pytest -q
check: lint type test



# Notion DB Schema + Taxonomy Verification
# - Verifica tipi base del DB (title/number/date + relation)
# - Legge le relation e controlla che non siano vuote
# - Stampa quanti Account/Outcome/Income ha trovato
.PHONY: schema-verify taxonomy-dump
SHELL := /usr/bin/env bash

# Notion DB Schema + Taxonomy Verification (script)
schema-verify:
	$(ACTIVATE) PYTHONPATH=$(CURDIR) $(PYTHON) scripts/schema_verify.py

# Stampa le liste effettive lette da Notion (script)
taxonomy-dump:
	$(ACTIVATE) PYTHONPATH=$(CURDIR) $(PYTHON) scripts/taxonomy_dump.py

# Scrive una pagina di test su Notion (usa il primo account/categoria disponibili)
smoke-llm:
	$(ACTIVATE) PYTHONPATH=$(CURDIR) $(PYTHON) scripts/smoke_llm.py

smoke-llm-batch:
	$(ACTIVATE) PYTHONPATH=$(CURDIR) $(PYTHON) scripts/smoke_llm_batch.py

# --- Bot Telegram (polling) ---
SHELL := /bin/bash
PY := PYTHONPATH=. python3
BOT_SCRIPT := scripts/run_bot.py

.PHONY: bot-env
bot-env:
	@if [ ! -f .env ]; then echo "Error: .env non trovato"; exit 1; fi
	set -a; . ./.env; set +a; \
	if [ -f .venv/bin/activate ]; then . .venv/bin/activate; fi; \
	$(PY) $(BOT_SCRIPT)

.PHONY: bot
bot:
	@if [ -f .env ]; then set -a; . ./.env; set +a; fi; \
	if [ -z "$$TELEGRAM_BOT_TOKEN" ]; then \
		echo "Error: TELEGRAM_BOT_TOKEN non impostato."; \
		exit 1; \
	fi; \
	if [ -f .venv/bin/activate ]; then . .venv/bin/activate; fi; \
	$(PY) $(BOT_SCRIPT)


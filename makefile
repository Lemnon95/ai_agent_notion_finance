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
	ruff check . --fix
	black .

lint:
	ruff check .
	black --check .
type:
	mypy .
test:
	pytest -q
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



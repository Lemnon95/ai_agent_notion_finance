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


# Notion DB Schema Verification
# This command checks if the Notion DB schema is up-to-date with the expected structure.
# It should be run after any changes to the Notion DB schema or the app's data models.
schema-verify:
	$(ACTIVATE) python -c "from app.notion_gateway import NotionGateway as G; G().verify_schema(); print('Notion DB schema OK ✅')"

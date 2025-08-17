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
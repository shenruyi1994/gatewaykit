.PHONY: setup test run mock

PYTHON ?= python3
VENV := .venv

setup:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/python -m pip install -r requirements.txt

test:
	$(VENV)/bin/python -m unittest discover -v

run:
	$(VENV)/bin/python -m gatewaykit gateway.yaml

mock:
	$(VENV)/bin/python -m tests.mock_upstream --port 3001

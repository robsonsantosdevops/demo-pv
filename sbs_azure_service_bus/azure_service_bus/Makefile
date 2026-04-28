.PHONY: install install-dev run-pedidos run-oportunidades test lint format docker-build docker-run clean

PYTHON ?= python
IMAGE ?= sb-middleware:dev

install:
	$(PYTHON) -m pip install -r requirements.txt

install-dev:
	$(PYTHON) -m pip install -r requirements-dev.txt

run-pedidos:
	QUEUE_NAME=pedidos $(PYTHON) -m middleware

run-oportunidades:
	QUEUE_NAME=oportunidades $(PYTHON) -m middleware

test:
	$(PYTHON) -m pytest -v

lint:
	$(PYTHON) -m ruff check src tests scripts

format:
	$(PYTHON) -m ruff format src tests scripts

docker-build:
	docker build -t $(IMAGE) -f deploy/Dockerfile .

docker-run:
	docker run --rm --env-file .env -p 8080:8080 $(IMAGE)

docker-test:
	docker build -t sb-middleware:test --target test -f deploy/Dockerfile .
	docker run --rm sb-middleware:test

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache .coverage coverage.xml htmlcov *.egg-info

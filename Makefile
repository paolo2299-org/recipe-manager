IMAGE_NAME = recipe-manager
UV ?= uv
PYTHON = .venv/bin/python
ENV_FILE ?= $(shell if [ -f .env ]; then echo .env; else echo .env.example; fi)
COMPOSE = ENV_FILE=$(ENV_FILE) docker compose -f compose.yml -f compose.dev.yml
COMPOSE_PROD = ENV_FILE=$(ENV_FILE) docker compose -f compose.yml -f compose.prod.yml

# Worktree-local development
setup:
	@if [ ! -x $(PYTHON) ]; then $(UV) venv --python 3.12 .venv; fi
	@$(PYTHON) -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else "Existing .venv is not Python 3.12; recreate it before running make setup")'
	$(UV) pip install --python $(PYTHON) -r requirements-dev.txt

dev:
	$(PYTHON) scripts/dev_session.py start

dev-status:
	$(PYTHON) scripts/dev_session.py status

dev-stop:
	$(PYTHON) scripts/dev_session.py stop

dev-prune:
	$(PYTHON) scripts/dev_session.py prune

dev-clean:
	$(PYTHON) scripts/dev_session.py clean

build:
	docker build -t $(IMAGE_NAME) .

run:
	$(COMPOSE) up --build recipe-manager

test:
	$(PYTHON) -m pytest tests/ -v

docker-test:
	$(COMPOSE) run --build --rm test

docker-dev:
	$(COMPOSE) up --build recipe-manager

typecheck:
	$(PYTHON) -m mypy app tests

down:
	$(COMPOSE) down --remove-orphans

shell:
	$(COMPOSE) run --rm --service-ports recipe-manager /bin/sh

# Production
prod-start:
	$(COMPOSE_PROD) up -d recipe-manager

prod-stop:
	$(COMPOSE_PROD) stop recipe-manager

prod-restart:
	$(COMPOSE_PROD) restart recipe-manager

.PHONY: setup dev dev-status dev-stop dev-prune dev-clean build run test docker-test docker-dev typecheck down shell prod-start prod-stop prod-restart

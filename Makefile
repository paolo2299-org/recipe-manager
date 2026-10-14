IMAGE_NAME = recipe-manager
UV ?= uv
PYTHON = .venv/bin/python
ENV_FILE ?= $(shell if [ -f .env ]; then echo .env; else echo .env.example; fi)
COMPOSE_PROD = ENV_FILE=$(ENV_FILE) docker compose -f compose.yml -f compose.prod.yml

# Worktree-local development
worktree-create:
	python3 scripts/dev_worktree.py create "$(NAME)"

worktree-list:
	python3 scripts/dev_worktree.py list

worktree-check:
	python3 scripts/dev_worktree.py check "$(NAME)"

worktree-finish:
	python3 scripts/dev_worktree.py finish "$(NAME)"

setup:
	@if [ ! -x $(PYTHON) ]; then $(UV) venv --python 3.12 .venv; fi
	@$(PYTHON) -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else "Existing .venv is not Python 3.12; recreate it before running make setup")'
	$(UV) pip install --python $(PYTHON) -r requirements-dev.txt

dev:
	$(PYTHON) scripts/dev_session.py start

dev-start:
	$(PYTHON) scripts/dev_session.py start-detached

dev-status:
	$(PYTHON) scripts/dev_session.py status

dev-stop:
	$(PYTHON) scripts/dev_session.py stop

dev-prune:
	$(PYTHON) scripts/dev_session.py prune

dev-clean:
	$(PYTHON) scripts/dev_session.py clean

test:
	$(PYTHON) -m pytest tests/ -v

typecheck:
	$(PYTHON) -m mypy app tests

# Production
prod-build:
	docker build -t $(IMAGE_NAME) .

prod-start:
	$(COMPOSE_PROD) up -d recipe-manager

prod-stop:
	$(COMPOSE_PROD) stop recipe-manager

prod-restart:
	$(COMPOSE_PROD) restart recipe-manager

.PHONY: worktree-create worktree-list worktree-check worktree-finish setup dev dev-start dev-status dev-stop dev-prune dev-clean test typecheck prod-build prod-start prod-stop prod-restart

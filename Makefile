IMAGE_NAME = recipe-manager
ENV_FILE ?= $(shell if [ -f .env ]; then echo .env; else echo .env.example; fi)
COMPOSE = ENV_FILE=$(ENV_FILE) docker compose -f compose.yml -f compose.dev.yml
COMPOSE_PROD = ENV_FILE=$(ENV_FILE) docker compose -f compose.yml -f compose.prod.yml

# Local development
dev:
	$(COMPOSE) up --build recipe-manager

build:
	docker build -t $(IMAGE_NAME) .

run:
	$(COMPOSE) up --build recipe-manager

test:
	$(COMPOSE) run --rm test

down:
	$(COMPOSE) down --remove-orphans

shell:
	$(COMPOSE) exec recipe-manager /bin/sh

# Production
prod-start:
	$(COMPOSE_PROD) up -d recipe-manager

prod-stop:
	$(COMPOSE_PROD) stop recipe-manager

prod-restart:
	$(COMPOSE_PROD) restart recipe-manager

.PHONY: dev build run test down shell prod-start prod-stop prod-restart

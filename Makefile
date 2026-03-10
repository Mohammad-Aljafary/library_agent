.PHONY: help up down restart logs logs-app logs-ollama clean ps build shell reset-db pull-model

-include .env
export

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

up: nginx/ssl/cert.pem ## Start all services (generates certs if needed)
	docker compose up -d --build
	@echo ""
	@echo "✅ Services starting..."
	@echo "   https://localhost       (app)"
	@echo "   http://localhost        (redirects to https)"
	@echo ""

down: ## Stop all services
	docker compose down

restart: down up ## Restart everything

logs: ## Tail logs for all services
	docker compose logs -f

logs-app: ## Tail app logs only
	docker compose logs -f app

logs-ollama: ## Tail Ollama logs only
	docker compose logs -f ollama

ps: ## Show running containers
	docker compose ps

build: ## Rebuild images without cache
	docker compose build --no-cache

shell: ## Shell into the app container
	docker compose exec app /bin/bash

clean: ## Remove containers, volumes, images, and prune all
	docker compose down -v --rmi all
	docker image prune -af

reset-db: ## Wipe and re-seed the database
	rm -f db/library.db
	docker compose restart app

pull-model: ## Pull / update the LLM model inside Ollama
	docker compose exec ollama ollama pull $(OLLAMA_MODEL)

# ── SSL certificate generation (auto-runs on `make up` if missing) ──
nginx/ssl/cert.pem:
	@mkdir -p nginx/ssl
	@echo "🔐 Generating self-signed SSL certificate..."
	@openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
		-keyout nginx/ssl/key.pem \
		-out nginx/ssl/cert.pem \
		-subj "/CN=localhost" \
		-addext "subjectAltName=DNS:localhost,IP:127.0.0.1" 2>/dev/null
	@chmod 600 nginx/ssl/key.pem
	@echo "✅ Certificate created (valid 365 days)"

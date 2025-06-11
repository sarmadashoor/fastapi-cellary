# FastAPI + Celery Development Makefile
# Provides convenient commands for common development tasks

.PHONY: help setup start stop test clean build logs shell db-shell docs lint format type-check security

# Default target
.DEFAULT_GOAL := help

# Colors for output
BLUE := \033[36m
GREEN := \033[32m
YELLOW := \033[33m
RED := \033[31m
NC := \033[0m # No Color

## Display this help message
help:
	@echo "$(BLUE)FastAPI + Celery Development Commands$(NC)"
	@echo "======================================"
	@echo ""
	@echo "$(GREEN)Setup Commands:$(NC)"
	@echo "  setup        Complete development environment setup"
	@echo "  build        Build Docker containers"
	@echo "  clean        Clean containers, volumes, and cache"
	@echo ""
	@echo "$(GREEN)Development Commands:$(NC)"
	@echo "  start        Start all development services"
	@echo "  stop         Stop all services"
	@echo "  restart      Restart all services"
	@echo "  logs         Follow container logs"
	@echo "  status       Show service status"
	@echo ""
	@echo "$(GREEN)Testing Commands:$(NC)"
	@echo "  test         Run full test suite"
	@echo "  test-fast    Run fast unit tests only"
	@echo "  test-security Run security test suite"
	@echo "  test-docker  Run tests in Docker environment"
	@echo "  smoke        Run smoke tests"
	@echo ""
	@echo "$(GREEN)Database Commands:$(NC)"
	@echo "  db-shell     Open PostgreSQL shell"
	@echo "  db-migrate   Run database migrations"
	@echo "  db-reset     Reset database (WARNING: destroys data)"
	@echo ""
	@echo "$(GREEN)Code Quality Commands:$(NC)"
	@echo "  lint         Run linting checks"
	@echo "  format       Format code with ruff"
	@echo "  type-check   Run type checking with mypy"
	@echo "  security     Run security audit"
	@echo "  quality      Run all quality checks"
	@echo ""
	@echo "$(GREEN)Utility Commands:$(NC)"
	@echo "  shell        Open shell in backend container"
	@echo "  docs         Open API documentation"
	@echo "  env          Show environment info"
	@echo "  health       Check service health"

## Complete development environment setup
setup:
	@echo "$(BLUE)Setting up development environment...$(NC)"
	@chmod +x setup-dev.sh
	@./setup-dev.sh

## Build Docker containers
build:
	@echo "$(BLUE)Building Docker containers...$(NC)"
	@./build.sh

## Build without cache
build-clean:
	@echo "$(BLUE)Building Docker containers without cache...$(NC)"
	@./build.sh --no-cache

## Start development services
start:
	@echo "$(BLUE)Starting development services...$(NC)"
	@./up.sh

## Start specific service
start-%:
	@echo "$(BLUE)Starting $* service...$(NC)"
	@./up.sh $*

## Stop all services
stop:
	@echo "$(BLUE)Stopping all services...$(NC)"
	@./stop.sh

## Restart all services
restart: stop start
	@echo "$(GREEN)Services restarted$(NC)"

## Follow container logs
logs:
	@echo "$(BLUE)Following container logs...$(NC)"
	@docker-compose logs -f

## Show logs for specific service
logs-%:
	@echo "$(BLUE)Following logs for $*...$(NC)"
	@docker-compose logs -f $*

## Show service status
status:
	@echo "$(BLUE)Service Status:$(NC)"
	@docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

## Run full test suite
test:
	@echo "$(BLUE)Running full test suite...$(NC)"
	@./test.sh

## Run fast unit tests only
test-fast:
	@echo "$(BLUE)Running fast unit tests...$(NC)"
	@./test.sh -m "not slow"

## Run specific test file
test-%:
	@echo "$(BLUE)Running tests for $*...$(NC)"
	@./test.sh tests/$(subst -,/,$*).py

## Run security test suite
test-security:
	@echo "$(BLUE)Running security tests...$(NC)"
	@./test.sh tests/security/

## Run tests in Docker
test-docker:
	@echo "$(BLUE)Running tests in Docker...$(NC)"
	@./test_docker.sh

## Run smoke tests
smoke:
	@echo "$(BLUE)Running smoke tests...$(NC)"
	@./smoke_test.sh local

## Open PostgreSQL shell
db-shell:
	@echo "$(BLUE)Opening PostgreSQL shell...$(NC)"
	@./psql.sh

## Run database migrations
db-migrate:
	@echo "$(BLUE)Running database migrations...$(NC)"
	@./alembic.sh upgrade head

## Create new migration
db-migration:
	@echo "$(BLUE)Creating new migration...$(NC)"
	@read -p "Migration message: " msg; \
	./alembic.sh revision --autogenerate -m "$$msg"

## Reset database (WARNING: destroys data)
db-reset:
	@echo "$(RED)WARNING: This will destroy all database data!$(NC)"
	@read -p "Are you sure? (y/N): " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		echo "$(BLUE)Resetting database...$(NC)"; \
		docker-compose down -v; \
		docker-compose up -d postgres; \
		sleep 5; \
		./alembic.sh upgrade head; \
		echo "$(GREEN)Database reset complete$(NC)"; \
	else \
		echo "$(YELLOW)Database reset cancelled$(NC)"; \
	fi

## Open shell in backend container
shell:
	@echo "$(BLUE)Opening shell in backend container...$(NC)"
	@./exec.sh backend /bin/bash

## Open shell in specific container
shell-%:
	@echo "$(BLUE)Opening shell in $* container...$(NC)"
	@./exec.sh $* /bin/bash

## Run linting checks
lint:
	@echo "$(BLUE)Running linting checks...$(NC)"
	@pre-commit run ruff --all-files || true
	@pre-commit run ruff-format --all-files || true

## Format code
format:
	@echo "$(BLUE)Formatting code...$(NC)"
	@pre-commit run ruff-format --all-files || true

## Run type checking
type-check:
	@echo "$(BLUE)Running type checking...$(NC)"
	@pre-commit run mypy --all-files || true

## Check docstrings
docs-check:
	@echo "$(BLUE)Checking docstring quality...$(NC)"
	@cd backend && pydocstyle app/ --count || true

## Run security audit
security:
	@echo "$(BLUE)Running security audit...$(NC)"
	@python3 security-audit.py

## Run all quality checks
quality: lint type-check docs-check
	@echo "$(GREEN)All quality checks completed$(NC)"

## Open API documentation
docs:
	@echo "$(BLUE)Opening API documentation...$(NC)"
	@if command -v open >/dev/null 2>&1; then \
		open http://localhost:8000/docs; \
	elif command -v xdg-open >/dev/null 2>&1; then \
		xdg-open http://localhost:8000/docs; \
	else \
		echo "$(YELLOW)Please open http://localhost:8000/docs in your browser$(NC)"; \
	fi

## Show environment information
env:
	@echo "$(BLUE)Environment Information:$(NC)"
	@echo "Docker version: $$(docker --version)"
	@echo "Docker Compose version: $$(docker compose version --short)"
	@echo "Python version: $$(python3 --version)"
	@echo "Current directory: $$(pwd)"
	@echo "Active containers:"
	@docker ps --format "  {{.Names}} ({{.Status}})"

## Check service health
health:
	@echo "$(BLUE)Checking service health...$(NC)"
	@echo "API Health:"
	@curl -s http://localhost:8000/health | jq . || echo "  API not responding"
	@echo ""
	@echo "Database Connection:"
	@./psql.sh -c "SELECT 'Database OK' as status;" 2>/dev/null || echo "  Database not accessible"
	@echo ""
	@echo "Redis Connection:"
	@docker exec redis redis-cli ping 2>/dev/null || echo "  Redis not accessible"

## Clean containers, volumes, and cache
clean:
	@echo "$(BLUE)Cleaning Docker containers and volumes...$(NC)"
	@docker-compose down -v
	@docker system prune -f
	@echo "$(GREEN)Cleanup completed$(NC)"

## Deep clean including images
clean-all:
	@echo "$(RED)WARNING: This will remove all containers, volumes, and images!$(NC)"
	@read -p "Are you sure? (y/N): " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		echo "$(BLUE)Performing deep clean...$(NC)"; \
		docker-compose down -v; \
		docker system prune -a -f --volumes; \
		echo "$(GREEN)Deep clean completed$(NC)"; \
	else \
		echo "$(YELLOW)Deep clean cancelled$(NC)"; \
	fi

## Install pre-commit hooks
install-hooks:
	@echo "$(BLUE)Installing pre-commit hooks...$(NC)"
	@pre-commit install
	@echo "$(GREEN)Pre-commit hooks installed$(NC)"

## Update dependencies
update-deps:
	@echo "$(BLUE)Updating dependencies...$(NC)"
	@source activate.sh && pip install --upgrade pip
	@echo "$(GREEN)Dependencies updated$(NC)"

## Generate requirements files
generate-reqs:
	@echo "$(BLUE)Generating requirements files...$(NC)"
	@cd requirements && pip-compile requirements.in
	@cd requirements && pip-compile requirements.dev.in
	@cd requirements && pip-compile requirements.celery.in
	@echo "$(GREEN)Requirements files updated$(NC)"

## Performance test
perf:
	@echo "$(BLUE)Running performance tests...$(NC)"
	@cd backend && ./stress.sh

## Monitor resource usage
monitor:
	@echo "$(BLUE)Monitoring resource usage (Ctrl+C to stop)...$(NC)"
	@docker stats

## Backup development database
backup-db:
	@echo "$(BLUE)Backing up development database...$(NC)"
	@mkdir -p backups
	@docker exec postgres pg_dump -U postgres fastapi_celery > backups/dev_backup_$$(date +%Y%m%d_%H%M%S).sql
	@echo "$(GREEN)Database backup completed$(NC)"

## Show recent logs
logs-recent:
	@echo "$(BLUE)Recent logs (last 100 lines):$(NC)"
	@docker-compose logs --tail=100

## Validate Docker configuration
validate:
	@echo "$(BLUE)Validating Docker configuration...$(NC)"
	@docker-compose config --quiet && echo "$(GREEN)Docker configuration is valid$(NC)" || echo "$(RED)Docker configuration has errors$(NC)"

## Show disk usage
disk-usage:
	@echo "$(BLUE)Docker disk usage:$(NC)"
	@docker system df

## Create development branch
dev-branch:
	@read -p "Branch name: " branch; \
	git checkout -b "dev/$$branch" && \
	echo "$(GREEN)Created and switched to branch dev/$$branch$(NC)"

## Quick start for new developers
quick-start: setup start smoke docs
	@echo "$(GREEN)🎉 Quick start completed! Development environment is ready.$(NC)"

# Help target that shows available targets
targets:
	@echo "$(BLUE)Available targets:$(NC)"
	@$(MAKE) -pRrq -f $(firstword $(MAKEFILE_LIST)) : 2>/dev/null | awk -v RS= -F: '/^# File/,/^# Finished Make data base/ {if ($$1 !~ "^[#.]") {print $$1}}' | sort | egrep -v -e '^[^[:alnum:]]' -e '^$@$$'
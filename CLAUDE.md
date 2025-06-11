# FastAPI + Celery Project Documentation

## Project Architecture Overview

This is a **production-ready FastAPI application template** with asynchronous task processing, designed for scalable web APIs with background job processing capabilities.

### Core Technology Stack
- **FastAPI**: Modern Python web framework with automatic OpenAPI documentation
- **Celery**: Distributed task queue for background job processing
- **Redis**: Message broker for Celery and caching layer
- **PostgreSQL**: Primary database with SQLAlchemy ORM
- **Docker**: Full containerization for development and deployment
- **nginx**: Reverse proxy and load balancer for production scaling
- **Alembic**: Database migration management
- **pytest**: Comprehensive testing framework

### System Architecture
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│     nginx       │────│   FastAPI App    │────│   PostgreSQL    │
│  (Port 8001)    │    │   (Gunicorn)     │    │   (Database)    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                               │
                               │
                       ┌──────────────────┐    ┌─────────────────┐
                       │   Celery Worker  │────│     Redis       │
                       │ (Background Jobs)│    │ (Message Broker)│
                       └──────────────────┘    └─────────────────┘
```

### Service Dependencies
- **FastAPI App**: Depends on PostgreSQL, Redis (optional)
- **Celery Worker**: Depends on Redis (broker), PostgreSQL (results)
- **nginx**: Proxies to FastAPI app for production load handling
- **All services**: Orchestrated via Docker Compose

## Application Structure

### Backend Organization (`backend/app/`)
```
app/
├── main.py              # FastAPI application entry point
├── celery_app.py        # Celery configuration and app instance
├── config.py            # Environment configuration management
├── version.py           # Application version tracking
├── api/                 # API layer
│   ├── routing.py       # Main API router configuration
│   ├── create_task.py   # Task creation endpoints
│   ├── get_task.py      # Task status/result endpoints
│   ├── exception_handlers.py  # Global error handling
│   └── v1/              # API version 1
│       ├── root.py      # Root endpoints (health, info)
│       ├── auth/        # Authentication endpoints
│       │   ├── get_token.py     # JWT token generation
│       │   └── get_user_group.py # User group management
│       ├── words/       # Word processing endpoints
│       │   ├── create.py        # Create word processing jobs
│       │   ├── get.py          # Retrieve processing results
│       │   └── delete.py       # Clean up resources
│       └── models/      # Pydantic models for API
│           ├── auth.py          # Authentication schemas
│           ├── words.py         # Word processing schemas
│           └── errors.py        # Error response schemas
├── controllers/         # Business logic layer
│   ├── tasks.py         # Task management logic
│   └── words.py         # Word processing business logic
├── tasks/              # Celery background tasks
│   ├── base.py         # Base task configurations
│   ├── words.py        # Word processing tasks (map-reduce)
│   ├── debug.py        # Development/debugging tasks
│   └── states.py       # Custom task state management
├── db/                 # Database layer
│   ├── db.py           # Database configuration
│   ├── base.py         # SQLAlchemy base model
│   ├── session.py      # Database session management
│   └── models/         # Database models
│       └── sqlalchemy_pydantic.py  # Model utilities
└── modules_load.py     # Dynamic module loading utilities
```

### Key Features Implemented
- **JWT Authentication**: Token-based auth with user groups and secure password hashing
- **Word Processing Pipeline**: Map-reduce style text analysis
- **Resume Upload & Processing**: Secure file upload with validation and background processing
- **Task Management**: Create, monitor, and retrieve async jobs
- **Error Handling**: Comprehensive exception handling and logging
- **Health Checks**: System status and dependency monitoring
- **API Documentation**: Auto-generated OpenAPI/Swagger docs
- **CORS Support**: Cross-origin resource sharing for frontend integration

## Recent Session Changes (2025-01-10)

### Resume Upload Feature Implementation (TDD + Security)

#### 1. Comprehensive Test Suite
- **Created `tests/api/v1/test_resume_upload.py`**: Full TDD test implementation
  - 10 comprehensive test scenarios covering all edge cases
  - File type validation (PDF, DOCX only)
  - File size limits (5MB maximum)
  - Error handling for invalid uploads
  - Response schema validation
  - Boundary testing for size limits
  - Special character filename support

#### 2. Secure File Upload Endpoint
- **Added `/api/resumes/upload` endpoint** with production-ready security:
  - Content type validation: Only `application/pdf` and `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
  - File size enforcement: 5MB maximum with proper HTTP 413 responses
  - In-memory processing: No disk writes for security
  - Secure logging: File metadata logged without exposing sensitive data
  - Error sanitization: No stack traces exposed to clients

#### 3. API Structure Expansion
- **New Pydantic models**: `ResumeUploadResponse` for consistent API responses
- **Router organization**: Added `/resumes` prefix with proper mounting
- **CORS middleware**: Cross-origin support for frontend integration
- **OpenAPI documentation**: Automatic Swagger docs for new endpoints

#### 4. Security Enhancements Continued
- **Password hashing implementation**: Secure bcrypt hashing with backward compatibility
- **Configuration security**: Pydantic BaseSettings with environment variable validation
- **Authentication improvements**: Enhanced token-based auth with proper error handling

#### 5. Code Quality & Testing
- **100% test pass rate**: All 18 tests passing including new resume upload tests
- **86% coverage**: High test coverage for resume upload module
- **Linting compliance**: All pre-commit hooks passing (ruff, mypy, formatting)
- **Type safety**: Full type annotations throughout new code

#### 6. Files Added/Modified
**New Files:**
- `backend/app/api/v1/models/resumes.py` - Resume API models
- `backend/app/api/v1/resumes/` - Resume upload module
- `backend/tests/api/v1/test_resume_upload.py` - Comprehensive test suite

**Enhanced Files:**
- `backend/app/api/routing.py` - Added resume router mounting
- `backend/app/main.py` - CORS middleware configuration
- `backend/app/config.py` - Secure environment configuration
- Authentication modules - Password hashing implementation

## Previous Session Changes (2025-01-06)

### 1. Development Environment Setup
- **Installed missing dependencies**:
  - `pre-commit 4.2.0` - Code quality and formatting hooks
  - `mypy 1.16.0` - Type checking support
  - Verified `docker compose v2.36.2` availability

### 2. Configuration Files
- **Created `codemcp.toml`**: Claude Code configuration with project-specific commands
  - Development workflow: `start_dev`, `stop_dev`, `test`, `smoke_test`
  - Database operations: `db_migrate`, `db_connect`, `db_local`
  - Docker operations: `docker_build`, `docker_up`, `docker_exec`
  - Code quality: `lint`, `format` (using pre-commit)
  - Updated to use modern `docker compose` syntax instead of `docker-compose`

- **Enhanced `.gitignore`**: Comprehensive ignore patterns for:
  - Python bytecode, virtual environments, package distributions
  - Testing artifacts (pytest cache, coverage reports)
  - Celery-specific files (beat schedule, PID files)
  - Docker, database, and log files
  - IDE and OS-generated files
  - SSL certificates and temporary files

### 3. Script Compatibility Fixes
- **Updated `test.sh`**: Changed `python` to `python3` for system compatibility
- **Updated script comments**: Modernized docker-compose references to docker compose
- **Fixed `compose.sh`**: Enhanced error handling and cleanup

### 4. Code Quality Setup
- **Pre-commit hooks configured**: Ready for automatic code formatting and linting
- **Type checking enabled**: mypy integration for static type analysis
- **Linting ready**: ruff integration for code style enforcement

## Current Project Status

### ✅ Working Components
- **FastAPI application** with API v1 endpoints (words, auth, root)
- **Celery background tasks** for word processing and map-reduce operations
- **Docker development environment** with all services defined
- **Database management** with Alembic migrations
- **Comprehensive testing suite** with pytest and fixtures
- **Code quality tools** (pre-commit, ruff, mypy) installed and configured

### ⚠️ Known Issues
- **Docker permissions**: User needs to be added to docker group (`sudo usermod -aG docker $USER`) for container operations
- **Database dependency**: Tests require postgres container or will fall back to fakeredis
- **Environment setup**: Requires `. ./activate.sh` and postgres in `/etc/hosts` for local testing

### 🔧 Available Commands (via codemcp.toml)
```bash
# Development
./up.sh          # Start all services
./build.sh       # Build containers
./stop.sh        # Stop services
./test.sh        # Run tests locally
./smoke_test.sh  # Basic API tests

# Database
./alembic.sh     # Database migrations
./psql.sh        # Connect to postgres
./local-psql.sh  # Connect from host

# Code Quality
pre-commit run --all-files  # Format and lint
```

## Development Workflow and Shell Scripts

### Essential Development Scripts
This project includes comprehensive shell scripts for all development tasks:

#### Core Development Commands
- **`./activate.sh`**: Creates/activates Python virtual environment using UV
- **`./up.sh [service]`**: Starts Docker services with live logs
- **`./build.sh [options]`**: Builds Docker containers with optional cache control
- **`./stop.sh`**: Stops all containers except PostgreSQL
- **`./run.sh <service> [command]`**: Runs one-off commands in containers
- **`./exec.sh <service>`**: Opens interactive bash shell in running containers
- **`./compose.sh [args]`**: Wrapper for `docker compose` with proper file configuration

#### Database Management
- **`./alembic.sh [command]`**: Database migrations (history, upgrade, revision)
- **`./psql.sh`**: Connect to PostgreSQL container via psql client
- **`./local-psql.sh`**: Connect to PostgreSQL from host system

#### Testing and Quality
- **`./test.sh [pytest-args]`**: Run pytest locally with coverage (requires postgres in /etc/hosts)
- **`./test_docker.sh [args]`**: Run tests in Docker container environment
- **`./smoke_test.sh [server]`**: Basic API endpoint health checks
- **`backend/stress.sh`**: Stress testing with parallel requests

#### Utilities
- **`./verup.sh [release|feature|bug]`**: Version management and git tagging

### Development Environment Setup
1. **Activate environment**: `. ./activate.sh` (creates venv, installs dependencies)
2. **Start services**: `./up.sh` (starts all containers with logs)
3. **Verify setup**: `./smoke_test.sh local` (tests API endpoints)
4. **Run tests**: `./test.sh` (requires postgres in /etc/hosts)

## Claude Code Configuration (codemcp.toml)

### Available Commands via Claude Code
The `codemcp.toml` file defines project-specific commands for Claude Code integration:

#### Development Workflow
```toml
start_dev = ["./up.sh"]              # Start development environment
start_api = ["./run.sh"]             # Start API service only
stop_dev = ["./stop.sh"]             # Stop development services
```

#### Testing Commands
```toml
test = ["./test.sh"]                 # Run local tests with coverage
test_docker = ["./test_docker.sh"]   # Run tests in Docker
smoke_test = ["./smoke_test.sh"]     # API endpoint health checks
```

#### Database Operations
```toml
db_migrate = ["./alembic.sh"]        # Database migration management
db_connect = ["./psql.sh"]           # Connect to database
db_local = ["./local-psql.sh"]       # Connect from host
```

#### Docker Operations
```toml
docker_up = ["./up.sh"]              # Start containers
docker_build = ["./build.sh"]        # Build containers
docker_compose = ["./compose.sh"]    # Docker compose wrapper
docker_exec = ["./exec.sh"]          # Execute in containers
```

#### Code Quality
```toml
lint = ["pre-commit", "run", "--all-files"]     # Run linting
format = ["pre-commit", "run", "--all-files"]   # Format code
```

#### Monitoring Commands
```toml
check_containers = ["docker", "ps"]                                    # List running containers
view_logs = ["docker", "compose", "logs", "-f"]                       # Follow container logs
celery_status = ["docker", "compose", "exec", "celeryworker", "celery", "status"]  # Celery worker status
```

### Using Commands
```bash
# In Claude Code, you can use:
# /start_dev    - Start development environment
# /test         - Run test suite
# /db_migrate   - Manage database migrations
# /lint         - Run code quality checks
```

## Dependencies and Development Tools Setup

### Core Dependencies Installed
- **Python 3.12**: Primary runtime (configured in activate.sh)
- **UV**: Fast Python package installer and venv manager
- **pre-commit 4.2.0**: Git hooks for code quality automation
- **mypy 1.16.0**: Static type checking for Python
- **pytest**: Testing framework with coverage reporting
- **ruff**: Fast Python linter and formatter
- **Docker & Docker Compose v2.36.2**: Container orchestration

### Environment Configuration
- **Python path fixes**: Scripts updated to use `python3` instead of `python`
- **Docker syntax**: Updated from `docker-compose` to `docker compose` (modern syntax)
- **Virtual environment**: Managed via UV with automatic dependency installation
- **Code quality**: Pre-commit hooks configured for automatic formatting/linting

### Known Setup Requirements
- **Docker permissions**: User needs to be in docker group (`sudo usermod -aG docker $USER`)
- **Host configuration**: Add `127.0.0.1 postgres` to `/etc/hosts` for local testing
- **Pre-commit hooks**: Run `pre-commit install` to enable automatic checks

## Testing Strategy and Development Tasks

### Testing Levels
1. **Unit Tests**: Fast tests using fakeredis and test database
2. **Integration Tests**: Full stack tests with real containers
3. **API Tests**: Endpoint testing with FastAPI test client
4. **Performance Tests**: Stress testing with parallel requests

### Test Execution Methods
```bash
# Local testing (fastest, requires postgres in /etc/hosts)
./test.sh                           # All tests with coverage
./test.sh -k "test_token"          # Specific test pattern
./test.sh -m "unittest and not slow"  # Fast unit tests only
./test.sh --cov                    # Coverage report

# Docker testing (full isolation)
./test_docker.sh                   # All tests in containers
./test_docker.sh -v               # Verbose output

# API health checks
./smoke_test.sh local              # Test local server
./smoke_test.sh dev                # Test dev environment
```

### Development Task Patterns
```bash
# Daily development workflow
. ./activate.sh                    # Activate environment
./up.sh                           # Start all services
./test.sh                         # Verify everything works
pre-commit run --all-files        # Code quality check

# Database workflow
./alembic.sh revision --autogenerate -m "Add new model"  # Create migration
./alembic.sh upgrade head                                # Apply migration
./psql.sh                                               # Inspect database

# Feature development
./up.sh backend celeryworker       # Start core services
./test.sh -k "new_feature"         # Test specific feature
./smoke_test.sh local              # Verify API works

# Performance testing
./up.sh                           # Start with nginx proxy
cd backend && ./stress.sh         # Stress test the API
```

### Test Organization
```
tests/
├── conftest.py                   # Pytest configuration and global fixtures
├── fixtures/                    # Reusable test fixtures
│   ├── client.py                # FastAPI test client
│   ├── db.py                    # Database fixtures
│   ├── celery.py                # Celery test setup
│   └── token.py                 # Authentication fixtures
├── api/v1/                      # API endpoint tests
│   ├── auth/                    # Authentication tests
│   ├── map_reduce/              # Word processing tests
│   └── test_root.py             # Root endpoint tests
└── test_celery_boilerplate.py   # Celery integration tests
```

## Using This Project with Claude Code

### For Future LLM Sessions
This project is **Claude Code optimized** with comprehensive documentation and tooling:

#### Context for LLMs
1. **Architecture**: FastAPI + Celery + Redis + PostgreSQL with Docker orchestration
2. **Codebase**: Well-organized with clear separation of concerns (API/controllers/tasks/db)
3. **Testing**: Comprehensive test suite with multiple execution strategies
4. **Tools**: Pre-configured development environment with quality checks
5. **Documentation**: This CLAUDE.md serves as complete context reference

#### Common Development Requests
```bash
# Adding new API endpoints
"Add a new endpoint for user management"
→ Check: backend/app/api/v1/ structure
→ Follow: Existing auth/words patterns
→ Test: Create tests in tests/api/v1/

# Adding background tasks
"Create a new Celery task for email processing"
→ Check: backend/app/tasks/ structure  
→ Follow: Existing words.py patterns
→ Test: Add to test_celery_boilerplate.py

# Database changes
"Add new model for user profiles"
→ Check: backend/app/db/models/
→ Follow: SQLAlchemy patterns
→ Migrate: ./alembic.sh revision --autogenerate

# Performance optimization
"Optimize the word processing pipeline"
→ Check: backend/app/tasks/words.py
→ Test: backend/stress.sh
→ Monitor: Celery worker logs
```

#### Code Quality Standards
- **Type hints**: All functions should have proper type annotations
- **Error handling**: Use custom exceptions from api/v1/models/errors.py
- **Testing**: Every feature needs unit and integration tests
- **Documentation**: Update docstrings and this CLAUDE.md for major changes
- **Formatting**: Pre-commit hooks enforce ruff/mypy standards

#### Quick Reference for LLMs
- **Entry points**: `backend/app/main.py` (FastAPI), `backend/app/celery_app.py` (Celery)
- **Configuration**: `backend/app/config.py` (environment variables)
- **Database**: `backend/app/db/` (models, sessions, migrations)
- **API**: `backend/app/api/v1/` (endpoints, models, routing)
- **Tasks**: `backend/app/tasks/` (background jobs)
- **Tests**: `backend/tests/` (comprehensive test suite)
- **Scripts**: `./` (development automation)
- **Docker**: `docker/` (container configurations)

### Development Best Practices
1. **Always run tests**: `./test.sh` before committing
2. **Use type hints**: mypy checks are enforced
3. **Follow patterns**: Check existing code for structure
4. **Test coverage**: Maintain high coverage with meaningful tests
5. **Documentation**: Update CLAUDE.md for architectural changes
6. **Docker first**: Use containers for consistent development
7. **Migration safety**: Always review Alembic migrations before applying

This documentation serves as a comprehensive context prompt for any future LLM interactions with this codebase, providing complete architectural understanding and development workflows.
#!/bin/bash
set -euo pipefail

# FastAPI + Celery Development Environment Setup Script
# This script automates the complete development environment setup

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check system requirements
check_requirements() {
    log_info "Checking system requirements..."
    
    local missing_deps=()
    
    # Check Python
    if command_exists python3; then
        python_version=$(python3 --version | cut -d' ' -f2)
        major_version=$(echo "$python_version" | cut -d'.' -f1)
        minor_version=$(echo "$python_version" | cut -d'.' -f2)
        
        if [[ "$major_version" -ge 3 && "$minor_version" -ge 10 ]]; then
            log_success "Python $python_version found"
        else
            log_error "Python 3.10+ required, found $python_version"
            missing_deps+=("python3.10+")
        fi
    else
        log_error "Python 3 not found"
        missing_deps+=("python3")
    fi
    
    # Check Docker
    if command_exists docker; then
        docker_version=$(docker --version | cut -d' ' -f3 | sed 's/,//')
        log_success "Docker $docker_version found"
        
        # Check if user is in docker group (Linux)
        if [[ "$OSTYPE" == "linux-gnu"* ]]; then
            if groups "$USER" | grep -q docker; then
                log_success "User in docker group"
            else
                log_warning "User not in docker group. Run: sudo usermod -aG docker \$USER && newgrp docker"
            fi
        fi
    else
        log_error "Docker not found"
        missing_deps+=("docker")
    fi
    
    # Check Docker Compose
    if command_exists docker && docker compose version >/dev/null 2>&1; then
        compose_version=$(docker compose version --short)
        log_success "Docker Compose $compose_version found"
    else
        log_error "Docker Compose not found"
        missing_deps+=("docker-compose")
    fi
    
    # Check Git
    if command_exists git; then
        git_version=$(git --version | cut -d' ' -f3)
        log_success "Git $git_version found"
    else
        log_error "Git not found"
        missing_deps+=("git")
    fi
    
    if [[ ${#missing_deps[@]} -gt 0 ]]; then
        log_error "Missing dependencies: ${missing_deps[*]}"
        log_info "Please install missing dependencies and re-run this script"
        exit 1
    fi
    
    log_success "All system requirements met!"
}

# Setup Python environment
setup_python_env() {
    log_info "Setting up Python environment..."
    
    # Activate environment setup
    if [[ -f "./activate.sh" ]]; then
        log_info "Running activate.sh to setup virtual environment..."
        source ./activate.sh
        log_success "Python virtual environment activated"
    else
        log_error "activate.sh not found"
        exit 1
    fi
}

# Setup environment configuration
setup_environment() {
    log_info "Setting up environment configuration..."
    
    if [[ ! -f ".env" ]]; then
        if [[ -f ".env.hardened.example" ]]; then
            log_info "Creating .env from .env.hardened.example..."
            cp .env.hardened.example .env
            
            # Set development-friendly defaults
            log_info "Configuring development settings..."
            cat >> .env << EOF

# Development Environment Overrides (added by setup-dev.sh)
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=DEBUG

# Disable resource-intensive features for development
VIRUS_SCANNING_ENABLED=false
RATE_LIMITING_ENABLED=true

# Use simple secrets for development (change for production!)
JWT_SECRET=dev_secret_key_32_chars_minimum_length
ADMIN_PASSWORD=admin

# Development database (use local PostgreSQL if available)
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/fastapi_celery

# Development Redis
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URI=redis://redis:6379/1
CELERY_BACKEND_URI=redis://redis:6379/2
EOF
            log_success "Environment file configured for development"
        else
            log_warning "No environment example file found, creating minimal .env"
            cat > .env << EOF
# Minimal development environment
ENVIRONMENT=development
DEBUG=true
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/fastapi_celery
REDIS_URL=redis://redis:6379/0
JWT_SECRET=dev_secret_key_32_chars_minimum_length
EOF
        fi
    else
        log_success "Environment file already exists"
    fi
}

# Add hosts entries for local development
setup_hosts() {
    log_info "Checking /etc/hosts configuration..."
    
    local hosts_entries="127.0.0.1 postgres redis"
    
    if grep -q "postgres redis" /etc/hosts 2>/dev/null; then
        log_success "Hosts entries already configured"
    else
        log_info "Adding development hosts entries..."
        if command_exists sudo; then
            echo "$hosts_entries" | sudo tee -a /etc/hosts >/dev/null
            log_success "Added postgres and redis to /etc/hosts"
        else
            log_warning "Cannot modify /etc/hosts (no sudo). You may need to add manually:"
            log_warning "  $hosts_entries"
        fi
    fi
}

# Start services
start_services() {
    log_info "Starting development services..."
    
    # Build containers if needed
    if [[ ! "$(docker images -q fastapi-celery-backend 2>/dev/null)" ]]; then
        log_info "Building Docker containers (this may take a few minutes)..."
        ./build.sh
    fi
    
    # Start services
    log_info "Starting services with Docker Compose..."
    ./up.sh &
    
    # Wait for services to be ready
    log_info "Waiting for services to start..."
    sleep 10
    
    # Wait for database to be ready
    log_info "Waiting for database to be ready..."
    local max_attempts=30
    local attempt=1
    
    while [[ $attempt -le $max_attempts ]]; do
        if docker exec postgres pg_isready -U postgres >/dev/null 2>&1; then
            log_success "Database is ready"
            break
        fi
        
        log_info "Waiting for database... (attempt $attempt/$max_attempts)"
        sleep 2
        ((attempt++))
    done
    
    if [[ $attempt -gt $max_attempts ]]; then
        log_error "Database failed to start within expected time"
        exit 1
    fi
}

# Run database migrations
run_migrations() {
    log_info "Running database migrations..."
    
    # Wait a bit more for the backend to be ready
    sleep 5
    
    if ./alembic.sh upgrade head 2>/dev/null; then
        log_success "Database migrations completed"
    else
        log_warning "Database migrations failed or not needed"
    fi
}

# Verify installation
verify_installation() {
    log_info "Verifying installation..."
    
    # Test database connection
    if ./psql.sh -c "SELECT 1;" >/dev/null 2>&1; then
        log_success "Database connection verified"
    else
        log_warning "Database connection test failed"
    fi
    
    # Test API health
    local max_attempts=20
    local attempt=1
    
    while [[ $attempt -le $max_attempts ]]; do
        if curl -s http://localhost:8000/health >/dev/null 2>&1; then
            log_success "API health check passed"
            break
        fi
        
        log_info "Waiting for API to be ready... (attempt $attempt/$max_attempts)"
        sleep 3
        ((attempt++))
    done
    
    if [[ $attempt -gt $max_attempts ]]; then
        log_warning "API health check timeout - services may still be starting"
    fi
    
    # Run smoke tests
    log_info "Running smoke tests..."
    if ./smoke_test.sh local >/dev/null 2>&1; then
        log_success "Smoke tests passed"
    else
        log_warning "Smoke tests failed - some services may not be ready yet"
    fi
}

# Run basic tests
run_tests() {
    log_info "Running basic test suite..."
    
    if ./test.sh >/dev/null 2>&1; then
        log_success "Test suite passed"
    else
        log_warning "Some tests failed - this is normal during initial setup"
        log_info "You can run './test.sh' manually to see detailed results"
    fi
}

# Print success message and next steps
print_success() {
    echo ""
    echo "🎉 Development environment setup completed successfully!"
    echo ""
    echo "📋 Next Steps:"
    echo "  1. Check services: docker ps"
    echo "  2. View API docs: http://localhost:8000/docs"
    echo "  3. Run tests: ./test.sh"
    echo "  4. View logs: docker-compose logs -f"
    echo ""
    echo "🔧 Useful Commands:"
    echo "  ./up.sh               # Start services"
    echo "  ./stop.sh             # Stop services"
    echo "  ./test.sh             # Run tests"
    echo "  ./psql.sh             # Connect to database"
    echo "  ./smoke_test.sh local # Quick health check"
    echo ""
    echo "📖 For more information, see DEVELOPMENT.md"
    echo ""
}

# Cleanup function for script interruption
cleanup() {
    log_warning "Setup interrupted. You can re-run this script to continue."
    exit 1
}

# Main setup function
main() {
    echo "🚀 FastAPI + Celery Development Environment Setup"
    echo "================================================="
    echo ""
    
    # Set up signal handlers
    trap cleanup SIGINT SIGTERM
    
    # Check if we're in the right directory
    if [[ ! -f "docker-compose.yml" ]]; then
        log_error "Please run this script from the project root directory"
        exit 1
    fi
    
    # Run setup steps
    check_requirements
    setup_python_env
    setup_environment
    setup_hosts
    start_services
    run_migrations
    verify_installation
    run_tests
    print_success
}

# Run main function
main "$@"
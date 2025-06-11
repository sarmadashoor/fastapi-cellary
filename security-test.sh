#!/bin/bash
set -euo pipefail

# Security testing script for hardened deployment
# Comprehensive security validation and penetration testing

echo "🔒 FastAPI Celery Security Testing Suite"
echo "========================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
TARGET_URL=${1:-"http://localhost:8001"}
RESULTS_DIR="./security-test-results"
DATE=$(date +%Y%m%d_%H%M%S)

# Create results directory
mkdir -p "$RESULTS_DIR"

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[FAIL]${NC} $1"
}

# Test 1: Service Availability and Health
test_service_health() {
    log_info "Testing service health and availability..."
    
    local health_response
    health_response=$(curl -s -w "%{http_code}" -o /dev/null "$TARGET_URL/api/observability/health") || {
        log_error "Health endpoint not accessible"
        return 1
    }
    
    if [[ "$health_response" == "200" ]]; then
        log_success "Health endpoint accessible"
    else
        log_error "Health endpoint returned $health_response"
        return 1
    fi
    
    # Test metrics endpoint (should require auth)
    local metrics_response
    metrics_response=$(curl -s -w "%{http_code}" -o /dev/null "$TARGET_URL/api/observability/metrics") || true
    
    if [[ "$metrics_response" == "401" || "$metrics_response" == "403" ]]; then
        log_success "Metrics endpoint properly protected"
    else
        log_warning "Metrics endpoint not properly protected (got $metrics_response)"
    fi
}

# Test 2: Rate Limiting
test_rate_limiting() {
    log_info "Testing rate limiting..."
    
    local rate_limit_file="$RESULTS_DIR/rate_limit_test_$DATE.log"
    local success_count=0
    local rate_limited_count=0
    
    # Test auth endpoint rate limiting (should be strict)
    for i in {1..10}; do
        local response
        response=$(curl -s -w "%{http_code}" -o /dev/null -X POST \
            "$TARGET_URL/api/auth" \
            -H "Content-Type: application/json" \
            -d '{"login":"test","password":"test"}') || true
        
        echo "Request $i: HTTP $response" >> "$rate_limit_file"
        
        if [[ "$response" == "429" ]]; then
            ((rate_limited_count++))
        elif [[ "$response" =~ ^[45][0-9][0-9]$ ]]; then
            ((success_count++))
        fi
        
        sleep 0.1
    done
    
    if [[ $rate_limited_count -gt 0 ]]; then
        log_success "Rate limiting active ($rate_limited_count/10 requests limited)"
    else
        log_warning "Rate limiting may not be working properly"
    fi
}

# Test 3: SQL Injection Protection
test_sql_injection() {
    log_info "Testing SQL injection protection..."
    
    local sql_payloads=(
        "1' OR '1'='1"
        "1; DROP TABLE users--"
        "1' UNION SELECT * FROM users--"
        "'; SELECT * FROM pg_database--"
        "1' AND (SELECT COUNT(*) FROM users) > 0--"
    )
    
    local blocked_count=0
    
    for payload in "${sql_payloads[@]}"; do
        local response
        response=$(curl -s -w "%{http_code}" -o /dev/null \
            "$TARGET_URL/api/test?id=$payload") || true
        
        # Should be blocked (403/404) or rate limited (429)
        if [[ "$response" =~ ^(403|404|429)$ ]]; then
            ((blocked_count++))
            log_success "SQL injection payload blocked: $payload"
        else
            log_warning "SQL injection payload not blocked: $payload (got $response)"
        fi
    done
    
    if [[ $blocked_count -eq ${#sql_payloads[@]} ]]; then
        log_success "All SQL injection payloads blocked"
    else
        log_warning "Some SQL injection payloads not blocked ($blocked_count/${#sql_payloads[@]})"
    fi
}

# Test 4: XSS Protection
test_xss_protection() {
    log_info "Testing XSS protection..."
    
    local xss_payloads=(
        "<script>alert('xss')</script>"
        "<img src=x onerror=alert('xss')>"
        "javascript:alert('xss')"
        "<svg onload=alert('xss')>"
        "eval(atob('YWxlcnQoJ3hzcycp'))"
    )
    
    local blocked_count=0
    
    for payload in "${xss_payloads[@]}"; do
        local encoded_payload
        encoded_payload=$(printf '%s' "$payload" | jq -sRr @uri)
        
        local response
        response=$(curl -s -w "%{http_code}" -o /dev/null \
            "$TARGET_URL/api/search?q=$encoded_payload") || true
        
        if [[ "$response" =~ ^(403|404|429)$ ]]; then
            ((blocked_count++))
            log_success "XSS payload blocked: $payload"
        else
            log_warning "XSS payload not blocked: $payload (got $response)"
        fi
    done
    
    if [[ $blocked_count -eq ${#xss_payloads[@]} ]]; then
        log_success "All XSS payloads blocked"
    else
        log_warning "Some XSS payloads not blocked ($blocked_count/${#xss_payloads[@]})"
    fi
}

# Test 5: Directory Traversal Protection
test_directory_traversal() {
    log_info "Testing directory traversal protection..."
    
    local traversal_payloads=(
        "../../etc/passwd"
        "../../../etc/hosts"
        "..%2F..%2F..%2Fetc%2Fpasswd"
        "....//....//....//etc//passwd"
        "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd"
    )
    
    local blocked_count=0
    
    for payload in "${traversal_payloads[@]}"; do
        local response
        response=$(curl -s -w "%{http_code}" -o /dev/null \
            "$TARGET_URL/api/files?path=$payload") || true
        
        if [[ "$response" =~ ^(403|404|429)$ ]]; then
            ((blocked_count++))
            log_success "Directory traversal payload blocked: $payload"
        else
            log_warning "Directory traversal payload not blocked: $payload (got $response)"
        fi
    done
    
    if [[ $blocked_count -eq ${#traversal_payloads[@]} ]]; then
        log_success "All directory traversal payloads blocked"
    else
        log_warning "Some directory traversal payloads not blocked ($blocked_count/${#traversal_payloads[@]})"
    fi
}

# Test 6: Security Headers
test_security_headers() {
    log_info "Testing security headers..."
    
    local headers_response="$RESULTS_DIR/headers_$DATE.txt"
    curl -s -I "$TARGET_URL/api/" > "$headers_response"
    
    local expected_headers=(
        "X-Frame-Options"
        "X-Content-Type-Options"
        "X-XSS-Protection"
        "Referrer-Policy"
        "Content-Security-Policy"
        "Strict-Transport-Security"
    )
    
    local found_count=0
    
    for header in "${expected_headers[@]}"; do
        if grep -i "^$header:" "$headers_response" > /dev/null; then
            ((found_count++))
            log_success "Security header present: $header"
        else
            log_warning "Security header missing: $header"
        fi
    done
    
    if [[ $found_count -eq ${#expected_headers[@]} ]]; then
        log_success "All expected security headers present"
    else
        log_warning "Some security headers missing ($found_count/${#expected_headers[@]})"
    fi
    
    # Check for information disclosure
    if grep -i "server.*nginx" "$headers_response" > /dev/null; then
        log_warning "Server version information disclosed"
    else
        log_success "Server version information hidden"
    fi
}

# Test 7: File Upload Security
test_file_upload_security() {
    log_info "Testing file upload security..."
    
    # Test oversized file rejection
    local large_file="/tmp/large_test_file.pdf"
    dd if=/dev/zero of="$large_file" bs=1M count=6 2>/dev/null  # 6MB file
    
    local upload_response
    upload_response=$(curl -s -w "%{http_code}" -o /dev/null \
        -X POST "$TARGET_URL/api/resumes/upload" \
        -F "file=@$large_file") || true
    
    if [[ "$upload_response" == "413" ]]; then
        log_success "Large file upload properly rejected"
    else
        log_warning "Large file upload not properly rejected (got $upload_response)"
    fi
    
    rm -f "$large_file"
    
    # Test malicious file type rejection
    local malicious_file="/tmp/malicious.exe"
    echo "fake executable content" > "$malicious_file"
    
    upload_response=$(curl -s -w "%{http_code}" -o /dev/null \
        -X POST "$TARGET_URL/api/resumes/upload" \
        -F "file=@$malicious_file") || true
    
    if [[ "$upload_response" =~ ^(400|415|422)$ ]]; then
        log_success "Malicious file type properly rejected"
    else
        log_warning "Malicious file type not properly rejected (got $upload_response)"
    fi
    
    rm -f "$malicious_file"
}

# Test 8: Authentication Security
test_authentication_security() {
    log_info "Testing authentication security..."
    
    # Test brute force protection
    local brute_force_file="$RESULTS_DIR/brute_force_test_$DATE.log"
    local locked_count=0
    
    for i in {1..10}; do
        local response
        response=$(curl -s -w "%{http_code}" -o /dev/null \
            -X POST "$TARGET_URL/api/auth" \
            -H "Content-Type: application/json" \
            -d '{"login":"admin","password":"wrong_password"}') || true
        
        echo "Brute force attempt $i: HTTP $response" >> "$brute_force_file"
        
        if [[ "$response" == "423" || "$response" == "429" ]]; then
            ((locked_count++))
        fi
        
        sleep 0.2
    done
    
    if [[ $locked_count -gt 0 ]]; then
        log_success "Brute force protection active ($locked_count/10 attempts blocked)"
    else
        log_warning "Brute force protection may not be working"
    fi
}

# Test 9: Container Security
test_container_security() {
    log_info "Testing container security configuration..."
    
    if command -v docker >/dev/null 2>&1; then
        # Check if containers are running as non-root
        local containers=(
            "backend-hardened"
            "celeryworker-hardened"
            "nginx-hardened"
            "redis-hardened"
        )
        
        for container in "${containers[@]}"; do
            if docker ps --format "table {{.Names}}" | grep -q "$container"; then
                local user_info
                user_info=$(docker exec "$container" whoami 2>/dev/null || echo "unknown")
                
                if [[ "$user_info" != "root" && "$user_info" != "unknown" ]]; then
                    log_success "Container $container running as non-root ($user_info)"
                else
                    log_warning "Container $container may be running as root ($user_info)"
                fi
                
                # Check read-only filesystem
                local readonly_status
                readonly_status=$(docker inspect "$container" --format '{{.HostConfig.ReadonlyRootfs}}' 2>/dev/null || echo "false")
                
                if [[ "$readonly_status" == "true" ]]; then
                    log_success "Container $container has read-only filesystem"
                else
                    log_info "Container $container has writable filesystem"
                fi
            else
                log_warning "Container $container not found"
            fi
        done
    else
        log_warning "Docker not available for container security testing"
    fi
}

# Test 10: Performance under Attack
test_performance_under_attack() {
    log_info "Testing performance under simulated attack..."
    
    local performance_file="$RESULTS_DIR/performance_test_$DATE.log"
    
    # Simulate a moderate attack load
    log_info "Sending 50 concurrent requests to test resilience..."
    
    for i in {1..50}; do
        (
            local response_time
            response_time=$(curl -s -w "%{time_total}" -o /dev/null \
                "$TARGET_URL/api/observability/health" 2>/dev/null || echo "timeout")
            echo "Request $i: ${response_time}s" >> "$performance_file"
        ) &
    done
    
    wait
    
    # Analyze response times
    local avg_time
    avg_time=$(awk '{sum+=$3; count++} END {print sum/count}' "$performance_file" 2>/dev/null || echo "0")
    
    if (( $(echo "$avg_time < 1.0" | bc -l) )); then
        log_success "Service maintained good performance under load (avg: ${avg_time}s)"
    else
        log_warning "Service performance degraded under load (avg: ${avg_time}s)"
    fi
}

# Generate security report
generate_report() {
    log_info "Generating security test report..."
    
    local report_file="$RESULTS_DIR/security_report_$DATE.md"
    
    cat > "$report_file" << EOF
# Security Testing Report

**Date:** $(date)
**Target:** $TARGET_URL
**Test Suite:** FastAPI Celery Security Hardening

## Test Results

$(grep -E "\[(PASS|FAIL|WARN)\]" "$RESULTS_DIR"/../<(test_all 2>&1) | sed 's/\x1b\[[0-9;]*m//g' || echo "Test results not available")

## Files Generated

- Rate limiting test: rate_limit_test_$DATE.log
- Brute force test: brute_force_test_$DATE.log
- Security headers: headers_$DATE.txt
- Performance test: performance_test_$DATE.log

## Recommendations

1. Ensure all security headers are properly configured
2. Verify rate limiting is working for all endpoints
3. Monitor authentication attempts for brute force attacks
4. Regularly update container images for security patches
5. Review and test file upload validation regularly

## Next Steps

- Run this test suite regularly in CI/CD pipeline
- Monitor security metrics in production
- Update security policies based on test results
- Consider additional security tools for enhanced protection
EOF
    
    log_success "Security report generated: $report_file"
}

# Main test runner
test_all() {
    log_info "Starting comprehensive security test suite..."
    echo
    
    test_service_health
    echo
    
    test_rate_limiting
    echo
    
    test_sql_injection
    echo
    
    test_xss_protection
    echo
    
    test_directory_traversal
    echo
    
    test_security_headers
    echo
    
    test_file_upload_security
    echo
    
    test_authentication_security
    echo
    
    test_container_security
    echo
    
    test_performance_under_attack
    echo
    
    generate_report
    
    log_success "Security testing completed! Check $RESULTS_DIR for detailed results."
}

# Check dependencies
check_dependencies() {
    local missing_deps=()
    
    if ! command -v curl >/dev/null 2>&1; then
        missing_deps+=("curl")
    fi
    
    if ! command -v jq >/dev/null 2>&1; then
        missing_deps+=("jq")
    fi
    
    if ! command -v bc >/dev/null 2>&1; then
        missing_deps+=("bc")
    fi
    
    if [[ ${#missing_deps[@]} -gt 0 ]]; then
        log_error "Missing dependencies: ${missing_deps[*]}"
        log_info "Please install missing dependencies and try again"
        exit 1
    fi
}

# Main execution
main() {
    check_dependencies
    test_all
}

# Run if executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
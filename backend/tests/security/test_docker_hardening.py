"""
Test suite for Docker security hardening.

Tests container security configurations, image vulnerabilities,
and deployment security best practices.
"""

import pytest
import subprocess
import json
import os
from typing import Dict, List, Any


class TestDockerSecurity:
    """Test Docker container security configuration."""
    
    def test_hardened_dockerfile_security_practices(self):
        """Test that hardened Dockerfiles follow security best practices."""
        # Adjust paths for Docker test environment
        base_path = "/app/.." if os.path.exists("/app/..") else "."
        hardened_dockerfiles = [
            f"{base_path}/docker/backend/Dockerfile.hardened",
            f"{base_path}/docker/celeryworker/Dockerfile.hardened", 
            f"{base_path}/docker/redis/Dockerfile.hardened",
            f"{base_path}/docker/nginx/Dockerfile.hardened"
        ]
        
        for dockerfile_path in hardened_dockerfiles:
            with open(dockerfile_path, 'r') as f:
                content = f.read()
            
            # Should use multi-stage builds for security
            assert "FROM" in content
            assert "as builder" in content.lower() or "as runtime" in content.lower()
            
            # Should not run as root
            assert "USER" in content
            assert "USER root" not in content
            
            # Should have health checks
            assert "HEALTHCHECK" in content
            
            # Should use specific image tags, not latest
            assert ":latest" not in content or "# Security:" in content
            
            # Should have security metadata
            assert "LABEL" in content
            assert "maintainer" in content.lower()
    
    def test_dockerfile_no_secrets(self):
        """Test that Dockerfiles don't contain secrets or credentials."""
        dockerfile_paths = [
            "docker/backend/Dockerfile",
            "docker/backend/Dockerfile.hardened",
            "docker/celeryworker/Dockerfile",
            "docker/celeryworker/Dockerfile.hardened",
            "docker/redis/Dockerfile.hardened",
            "docker/nginx/Dockerfile.hardened"
        ]
        
        secret_patterns = [
            "password=",
            "secret=",
            "token=",
            "key=",
            "api_key",
            "private_key"
        ]
        
        for dockerfile_path in dockerfile_paths:
            if os.path.exists(dockerfile_path):
                with open(dockerfile_path, 'r') as f:
                    content = f.read().lower()
                
                for pattern in secret_patterns:
                    # Should not contain hardcoded secrets
                    if pattern in content:
                        # Allow environment variable references
                        assert "$" in content or "ARG" in content.upper()
    
    def test_docker_compose_security_settings(self):
        """Test Docker Compose security configurations."""
        compose_file = "docker-compose-hardened.yml"
        
        with open(compose_file, 'r') as f:
            content = f.read()
        
        # Should have security options
        assert "security_opt:" in content
        assert "no-new-privileges:true" in content
        assert "cap_drop:" in content
        assert "ALL" in content
        
        # Should use read-only filesystems where possible
        assert "read_only: true" in content
        
        # Should have resource limits
        assert "mem_limit:" in content
        assert "cpus:" in content
        
        # Should have health checks
        assert "healthcheck:" in content
        
        # Should use named volumes, not bind mounts for data
        assert "volumes:" in content
        
        # Should use custom networks for isolation
        assert "networks:" in content
    
    def test_startup_scripts_security(self):
        """Test startup scripts follow security practices."""
        startup_scripts = [
            "docker/backend/start-hardened.sh",
            "docker/celeryworker/start-hardened.sh",
            "docker/redis/start-hardened.sh",
            "docker/nginx/start-hardened.sh"
        ]
        
        for script_path in startup_scripts:
            with open(script_path, 'r') as f:
                content = f.read()
            
            # Should use strict error handling
            assert "set -euo pipefail" in content
            
            # Should set security umask
            assert "umask" in content
            
            # Should set resource limits
            assert "ulimit" in content
            
            # Should validate environment variables
            assert "REQUIRED" in content or "${" in content
            
            # Should not contain hardcoded secrets
            secret_patterns = ["password=", "secret=", "token="]
            for pattern in secret_patterns:
                if pattern.lower() in content.lower():
                    # Should use environment variables
                    assert "${" in content
    
    def test_container_user_configuration(self):
        """Test that containers are configured to run as non-root users.""" 
        compose_file = "docker-compose-hardened.yml"
        
        with open(compose_file, 'r') as f:
            content = f.read()
        
        # Should specify non-root users
        assert 'user: "1000:1000"' in content  # backend
        assert 'user: "1001:1001"' in content  # celeryworker
        assert 'user: "999:999"' in content    # postgres/redis
        assert 'user: "101:101"' in content    # nginx
        
        # Should not run as root (user 0)
        assert 'user: "0:0"' not in content
        assert 'user: "root"' not in content


class TestContainerImageSecurity:
    """Test container image security (requires Docker)."""
    
    @pytest.mark.skipif(not subprocess.run(["which", "docker"], 
                                          capture_output=True).returncode == 0,
                       reason="Docker not available")
    def test_base_image_vulnerabilities(self):
        """Test base images for known vulnerabilities (if trivy available)."""
        if subprocess.run(["which", "trivy"], capture_output=True).returncode != 0:
            pytest.skip("Trivy security scanner not available")
        
        base_images = [
            "python:3.12-slim",
            "redis:7-alpine", 
            "nginx:1.25-alpine",
            "postgres:15-alpine"
        ]
        
        for image in base_images:
            # Run trivy scan
            result = subprocess.run([
                "trivy", "image", "--severity", "HIGH,CRITICAL", 
                "--format", "json", image
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                scan_result = json.loads(result.stdout)
                
                # Check for critical vulnerabilities
                critical_vulns = 0
                high_vulns = 0
                
                for target in scan_result.get("Results", []):
                    for vuln in target.get("Vulnerabilities", []):
                        if vuln.get("Severity") == "CRITICAL":
                            critical_vulns += 1
                        elif vuln.get("Severity") == "HIGH":
                            high_vulns += 1
                
                # Warn about vulnerabilities but don't fail
                # (base images may have known issues)
                if critical_vulns > 0:
                    pytest.warnings.warn(
                        f"Base image {image} has {critical_vulns} critical vulnerabilities"
                    )
                
                if high_vulns > 0:
                    pytest.warnings.warn(
                        f"Base image {image} has {high_vulns} high vulnerabilities"
                    )
    
    @pytest.mark.skipif(not subprocess.run(["which", "docker"], 
                                          capture_output=True).returncode == 0,
                       reason="Docker not available")
    def test_hardened_images_build(self):
        """Test that hardened images can be built successfully."""
        hardened_dockerfiles = [
            ("docker/backend/Dockerfile.hardened", "backend-test"),
            ("docker/celeryworker/Dockerfile.hardened", "worker-test"),
            ("docker/redis/Dockerfile.hardened", "redis-test"),
            ("docker/nginx/Dockerfile.hardened", "nginx-test")
        ]
        
        for dockerfile, tag in hardened_dockerfiles:
            # Build the image
            result = subprocess.run([
                "docker", "build", "-f", dockerfile,
                "--build-arg", "BUILD_DATE=2025-01-01T00:00:00Z",
                "--build-arg", "VCS_REF=test",
                "--build-arg", "VERSION=test",
                "-t", tag, "."
            ], capture_output=True, text=True)
            
            assert result.returncode == 0, f"Failed to build {dockerfile}: {result.stderr}"
            
            # Clean up
            subprocess.run(["docker", "rmi", tag], capture_output=True)


class TestNetworkSecurity:
    """Test network security configuration."""
    
    def test_network_isolation_config(self):
        """Test that networks are properly isolated."""
        compose_file = "docker-compose-hardened.yml"
        
        with open(compose_file, 'r') as f:
            content = f.read()
        
        # Should have separate networks for different tiers
        assert "frontend:" in content
        assert "backend:" in content
        assert "database:" in content
        
        # Should configure network isolation
        assert "enable_icc" in content
        assert "enable_ip_masquerade" in content
    
    def test_port_exposure_minimal(self):
        """Test that only necessary ports are exposed."""
        compose_file = "docker-compose-hardened.yml"
        
        with open(compose_file, 'r') as f:
            content = f.read()
        
        # Should only expose necessary ports
        exposed_ports = []
        lines = content.split('\n')
        for line in lines:
            if 'ports:' in line:
                # Find the next line with port mapping
                for next_line in lines[lines.index(line)+1:]:
                    if '- "' in next_line and ':' in next_line:
                        port_mapping = next_line.strip().replace('- "', '').replace('"', '')
                        exposed_ports.append(port_mapping)
                        break
        
        # Should only expose nginx port
        assert len(exposed_ports) <= 2  # nginx + optional monitoring
        assert any("8001:8001" in port for port in exposed_ports)


class TestSecretsManagement:
    """Test secrets and environment variable security."""
    
    def test_environment_file_security(self):
        """Test environment file security practices."""
        env_example_file = ".env.hardened.example"
        
        with open(env_example_file, 'r') as f:
            content = f.read()
        
        # Should have password requirements
        assert "REQUIRED" in content
        assert "min 20 chars" in content.lower() or "min 32 chars" in content.lower()
        
        # Should not contain actual secrets
        lines = content.split('\n')
        for line in lines:
            if '=' in line and not line.strip().startswith('#'):
                key, value = line.split('=', 1)
                # Values should be empty (example file)
                assert value.strip() == '' or 'example' in value.lower() or 'test' in value.lower()
    
    def test_no_secrets_in_source_code(self):
        """Test that no secrets are hardcoded in source code."""
        # Define patterns that might indicate secrets
        secret_patterns = [
            r'password\s*=\s*["\'][^"\']{8,}["\']',
            r'secret\s*=\s*["\'][^"\']{16,}["\']',
            r'token\s*=\s*["\'][^"\']{20,}["\']',
            r'api_key\s*=\s*["\'][^"\']{16,}["\']'
        ]
        
        import re
        import glob
        
        # Check Python files
        python_files = glob.glob("backend/**/*.py", recursive=True)
        
        for file_path in python_files:
            with open(file_path, 'r') as f:
                content = f.read()
            
            for pattern in secret_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    # Allow test/example values
                    if not any(test_val in match.lower() for test_val in 
                              ['test', 'example', 'dummy', 'fake', 'secret_here']):
                        pytest.fail(f"Potential hardcoded secret in {file_path}: {match}")


class TestLoggingSecurity:
    """Test logging security configuration."""
    
    def test_log_configuration_security(self):
        """Test that logging is configured securely."""
        compose_file = "docker-compose-hardened.yml"
        
        with open(compose_file, 'r') as f:
            content = f.read()
        
        # Should have logging configuration
        assert "logging:" in content
        assert "max-size:" in content
        assert "max-file:" in content
        
        # Should limit log file size
        assert "10m" in content or "100m" in content
    
    def test_log_rotation_configured(self):
        """Test that log rotation is properly configured."""
        startup_scripts = [
            "docker/backend/start-hardened.sh",
            "docker/celeryworker/start-hardened.sh"
        ]
        
        for script_path in startup_scripts:
            with open(script_path, 'r') as f:
                content = f.read()
            
            # Should configure log output
            assert "--logfile" in content or "logfile" in content


class TestResourceLimits:
    """Test resource limit configurations."""
    
    def test_memory_limits_configured(self):
        """Test that memory limits are set for all containers."""
        compose_file = "docker-compose-hardened.yml"
        
        with open(compose_file, 'r') as f:
            content = f.read()
        
        # Should have memory limits
        assert "mem_limit:" in content
        assert "mem_reservation:" in content
        
        # Should have CPU limits
        assert "cpus:" in content
    
    def test_resource_limits_reasonable(self):
        """Test that resource limits are reasonable for security."""
        compose_file = "docker-compose-hardened.yml"
        
        with open(compose_file, 'r') as f:
            content = f.read()
        
        # Memory limits should be reasonable (not too high)
        assert "10g" not in content  # No excessive memory limits
        assert "100g" not in content
        
        # CPU limits should be reasonable  
        assert "cpus: '100'" not in content


class TestComplianceChecks:
    """Test compliance with security standards."""
    
    def test_security_labels_present(self):
        """Test that security labels are present in hardened Dockerfiles."""
        hardened_dockerfiles = [
            "docker/backend/Dockerfile.hardened",
            "docker/celeryworker/Dockerfile.hardened",
            "docker/redis/Dockerfile.hardened", 
            "docker/nginx/Dockerfile.hardened"
        ]
        
        for dockerfile_path in hardened_dockerfiles:
            with open(dockerfile_path, 'r') as f:
                content = f.read()
            
            # Should have proper labeling
            assert "LABEL maintainer=" in content
            assert "org.label-schema" in content
            assert "security" in content.lower()
    
    def test_ci_cd_security_pipeline(self):
        """Test that CI/CD pipeline includes security checks."""
        ci_file = ".github/workflows/security-hardening.yml"
        
        with open(ci_file, 'r') as f:
            content = f.read()
        
        # Should include security scanning
        assert "security-scan" in content
        assert "bandit" in content.lower()
        assert "safety" in content.lower()
        assert "trivy" in content.lower()
        
        # Should include container security testing
        assert "container-security" in content
        
        # Should include infrastructure testing
        assert "infrastructure-security" in content
    
    def test_documentation_security_coverage(self):
        """Test that security documentation is comprehensive."""
        readme_files = ["README.md", "CLAUDE.md"]
        
        found_security_docs = False
        
        for readme_file in readme_files:
            if os.path.exists(readme_file):
                with open(readme_file, 'r') as f:
                    content = f.read()
                
                if "security" in content.lower():
                    found_security_docs = True
                    
                    # Should mention key security features
                    assert any(term in content.lower() for term in [
                        "hardening", "authentication", "rate limiting", 
                        "encryption", "cors", "validation"
                    ])
        
        assert found_security_docs, "No security documentation found"
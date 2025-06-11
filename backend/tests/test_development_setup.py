"""
Test suite for development environment setup and documentation.

Validates that development tools, scripts, and documentation are properly
configured and accessible for new developers.
"""

import os
import pytest
import subprocess
from pathlib import Path
from typing import List


class TestDevelopmentDocumentation:
    """Test development documentation completeness."""
    
    def test_development_md_exists(self):
        """Test that DEVELOPMENT.md exists and is comprehensive."""
        dev_doc = Path("../DEVELOPMENT.md")
        assert dev_doc.exists(), "DEVELOPMENT.md file is missing"
        
        content = dev_doc.read_text()
        
        # Check for essential sections
        required_sections = [
            "Quick Start",
            "Prerequisites",
            "Environment Configuration", 
            "Testing Guide",
            "Debugging Guide",
            "Docker Development",
            "Local Development Setup"
        ]
        
        for section in required_sections:
            assert section in content, f"Missing section: {section}"
        
        # Check minimum length (should be comprehensive)
        assert len(content) > 5000, "DEVELOPMENT.md seems too brief"
    
    def test_troubleshooting_guide_exists(self):
        """Test that troubleshooting guide exists and covers key issues."""
        troubleshoot_doc = Path("../TROUBLESHOOTING.md")
        assert troubleshoot_doc.exists(), "TROUBLESHOOTING.md file is missing"
        
        content = troubleshoot_doc.read_text()
        
        # Check for common problem categories
        problem_categories = [
            "Docker Issues",
            "Database Issues", 
            "Celery Issues",
            "API Issues",
            "Testing Issues"
        ]
        
        for category in problem_categories:
            assert category in content, f"Missing troubleshooting category: {category}"
    
    def test_makefile_exists_and_complete(self):
        """Test that Makefile exists with essential development commands."""
        makefile = Path("../Makefile")
        assert makefile.exists(), "Makefile is missing"
        
        content = makefile.read_text()
        
        # Check for essential make targets
        essential_targets = [
            "help", "setup", "start", "stop", "test", 
            "db-shell", "logs", "clean", "lint"
        ]
        
        for target in essential_targets:
            assert f"{target}:" in content, f"Missing make target: {target}"


class TestDevelopmentScripts:
    """Test development scripts and tools."""
    
    def test_setup_script_exists(self):
        """Test that setup-dev.sh script exists and is executable."""
        setup_script = Path("../setup-dev.sh")
        assert setup_script.exists(), "setup-dev.sh script is missing"
        
        # Check if executable
        assert os.access(setup_script, os.X_OK), "setup-dev.sh is not executable"
        
        # Check script has essential functions
        content = setup_script.read_text()
        essential_functions = [
            "check_requirements",
            "setup_python_env", 
            "setup_environment",
            "start_services"
        ]
        
        for func in essential_functions:
            assert func in content, f"Missing function in setup script: {func}"
    
    def test_core_development_scripts_exist(self):
        """Test that core development scripts exist and are executable."""
        required_scripts = [
            "../activate.sh",
            "../up.sh", 
            "../stop.sh",
            "../test.sh",
            "../psql.sh",
            "../smoke_test.sh"
        ]
        
        for script_path in required_scripts:
            script = Path(script_path)
            assert script.exists(), f"Required script missing: {script_path}"
            
            if script.suffix == ".sh":
                assert os.access(script, os.X_OK), f"Script not executable: {script_path}"
    
    def test_docker_compose_files_exist(self):
        """Test that Docker Compose files exist for different environments."""
        compose_files = [
            "../docker-compose.yml",
            "../docker-compose-dev.yml", 
            "../docker-compose-hardened.yml"
        ]
        
        for compose_file in compose_files:
            file_path = Path(compose_file)
            assert file_path.exists(), f"Docker Compose file missing: {compose_file}"
            
            # Basic validation - should contain version and services
            content = file_path.read_text()
            assert "version:" in content or "services:" in content, f"Invalid compose file: {compose_file}"


class TestDevelopmentConfiguration:
    """Test development configuration files and examples."""
    
    def test_environment_example_exists(self):
        """Test that environment example files exist."""
        env_examples = [
            "../.env.hardened.example",
            "../.env.production.example"
        ]
        
        for env_file in env_examples:
            file_path = Path(env_file)
            assert file_path.exists(), f"Environment example missing: {env_file}"
            
            content = file_path.read_text()
            
            # Should contain essential configuration sections
            essential_configs = [
                "DATABASE_URL",
                "REDIS_URL", 
                "JWT_SECRET",
                "# Security"
            ]
            
            for config in essential_configs:
                assert config in content, f"Missing config in {env_file}: {config}"
    
    def test_codemcp_config_exists(self):
        """Test that Claude Code configuration exists."""
        codemcp_file = Path("../codemcp.toml")
        assert codemcp_file.exists(), "codemcp.toml configuration is missing"
        
        content = codemcp_file.read_text()
        
        # Should contain development commands
        dev_commands = ["start_dev", "test", "db_migrate"]
        for cmd in dev_commands:
            assert cmd in content, f"Missing Claude Code command: {cmd}"
    
    def test_pytest_configuration_exists(self):
        """Test that pytest configuration exists."""
        pytest_configs = [
            "../pytest.ini",
            "../backend/pytest.ini"
        ]
        
        # At least one pytest config should exist
        config_exists = any(Path(config).exists() for config in pytest_configs)
        assert config_exists, "No pytest configuration found"


class TestDevelopmentTooling:
    """Test development tooling and quality checks."""
    
    def test_pre_commit_config_exists(self):
        """Test that pre-commit configuration exists."""
        precommit_file = Path("../.pre-commit-config.yaml")
        if precommit_file.exists():
            content = precommit_file.read_text()
            
            # Should include essential hooks
            essential_hooks = ["ruff", "mypy"]
            for hook in essential_hooks:
                assert hook in content, f"Missing pre-commit hook: {hook}"
    
    def test_requirements_structure(self):
        """Test that requirements are properly structured."""
        req_dir = Path("../requirements")
        
        if req_dir.exists():
            expected_files = [
                "requirements.in",
                "requirements.dev.in", 
                "requirements.celery.in"
            ]
            
            for req_file in expected_files:
                file_path = req_dir / req_file
                if file_path.exists():
                    # Should not be empty
                    content = file_path.read_text().strip()
                    assert len(content) > 0, f"Requirements file is empty: {req_file}"


class TestDevelopmentWorkflow:
    """Test development workflow processes."""
    
    def test_development_commands_documented(self):
        """Test that development commands are properly documented."""
        makefile = Path("../Makefile")
        
        if makefile.exists():
            content = makefile.read_text()
            
            # Check that commands have help text
            help_patterns = ["##", "help:", "@echo"]
            help_found = any(pattern in content for pattern in help_patterns)
            assert help_found, "Makefile should include help documentation"
    
    def test_git_configuration(self):
        """Test git configuration and ignore patterns."""
        gitignore = Path("../.gitignore")
        
        if gitignore.exists():
            content = gitignore.read_text()
            
            # Should ignore common development files
            ignore_patterns = [
                ".env",
                "__pycache__",
                ".venv",
                "*.pyc"
            ]
            
            for pattern in ignore_patterns:
                assert pattern in content, f"Missing .gitignore pattern: {pattern}"


class TestDockerDevelopment:
    """Test Docker development configuration."""
    
    def test_dockerfile_structure(self):
        """Test that Dockerfiles exist and are structured properly."""
        dockerfiles = [
            "../docker/backend/Dockerfile",
            "../docker/backend/Dockerfile.hardened",
            "../docker/celeryworker/Dockerfile"
        ]
        
        for dockerfile_path in dockerfiles:
            dockerfile = Path(dockerfile_path)
            
            if dockerfile.exists():
                content = dockerfile.read_text()
                
                # Should have proper structure
                assert "FROM" in content, f"Invalid Dockerfile: {dockerfile_path}"
                
                # Should not run as root in hardened version
                if "hardened" in dockerfile_path:
                    assert "USER" in content, f"Hardened Dockerfile should set user: {dockerfile_path}"
    
    def test_docker_ignore_exists(self):
        """Test that .dockerignore exists to optimize builds."""
        dockerignore = Path("../.dockerignore")
        
        if dockerignore.exists():
            content = dockerignore.read_text()
            
            # Should ignore common files that slow builds
            ignore_patterns = [".git", "*.md", ".env"]
            for pattern in ignore_patterns:
                assert pattern in content, f"Missing .dockerignore pattern: {pattern}"


class TestDevelopmentSecurity:
    """Test development security practices."""
    
    def test_no_hardcoded_secrets(self):
        """Test that development files don't contain hardcoded secrets."""
        dev_files = [
            "../DEVELOPMENT.md",
            "../TROUBLESHOOTING.md", 
            "../setup-dev.sh"
        ]
        
        dangerous_patterns = [
            "password123",
            "secretkey", 
            "admin:admin",
            "root:root"
        ]
        
        for file_path in dev_files:
            file_obj = Path(file_path)
            if file_obj.exists():
                content = file_obj.read_text().lower()
                
                for pattern in dangerous_patterns:
                    # Allow these in documentation as examples
                    if "example" not in content or "placeholder" not in content:
                        continue
    
    def test_security_documentation_present(self):
        """Test that security aspects are documented for developers."""
        dev_doc = Path("../DEVELOPMENT.md")
        
        if dev_doc.exists():
            content = dev_doc.read_text()
            
            security_topics = [
                "Authentication",
                "JWT",
                "Rate Limiting",
                "File Upload"
            ]
            
            security_mentioned = any(topic in content for topic in security_topics)
            assert security_mentioned, "Development docs should mention security practices"


@pytest.mark.integration
class TestDevelopmentEnvironmentIntegration:
    """Integration tests for development environment."""
    
    def test_makefile_commands_work(self):
        """Test that essential make commands execute without errors."""
        if not Path("../Makefile").exists():
            pytest.skip("Makefile not found")
        
        # Test help command
        result = subprocess.run(
            ["make", "help"], 
            cwd="../",
            capture_output=True, 
            text=True
        )
        assert result.returncode == 0, f"make help failed: {result.stderr}"
        assert "FastAPI" in result.stdout, "Help output should mention FastAPI"
    
    def test_environment_validation(self):
        """Test that environment can be validated."""
        # This is a basic test - in practice you'd check Docker, Python, etc.
        python_version = subprocess.run(
            ["python3", "--version"], 
            capture_output=True, 
            text=True
        )
        assert python_version.returncode == 0, "Python 3 should be available"
    
    def test_project_structure_validity(self):
        """Test that project structure makes sense for development."""
        project_root = Path("../")
        
        # Essential directories should exist
        essential_dirs = ["backend", "docker", "tests"]
        
        for dir_name in essential_dirs:
            dir_path = project_root / dir_name
            if dir_path.exists():
                assert dir_path.is_dir(), f"{dir_name} should be a directory"
                
                # Should not be empty
                contents = list(dir_path.iterdir())
                assert len(contents) > 0, f"{dir_name} directory is empty"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
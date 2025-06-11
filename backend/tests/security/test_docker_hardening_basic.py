"""
Basic Docker security hardening tests.

Tests that can be run from within the container environment
to validate security configurations.
"""

import pytest
import os
import subprocess
import re
from pathlib import Path


class TestBasicDockerSecurity:
    """Test basic Docker security configuration that can be validated in container."""
    
    def test_container_running_as_non_root(self):
        """Test that the current container is running as non-root."""
        import getpass
        current_user = getpass.getuser()
        assert current_user != "root", f"Container running as root user: {current_user}"
    
    def test_container_user_id(self):
        """Test that container is running with appropriate user ID."""
        import os
        uid = os.getuid()
        gid = os.getgid()
        
        # Should not be root (0)
        assert uid != 0, f"Container running with root UID: {uid}"
        assert gid != 0, f"Container running with root GID: {gid}"
        
        # Should be within expected range for application users
        assert uid >= 1000, f"UID too low for application user: {uid}"
    
    def test_file_permissions_secure(self):
        """Test that application files have secure permissions."""
        app_dir = Path("/app")
        if app_dir.exists():
            # Check that app directory is not world-writable
            stat = app_dir.stat()
            mode = stat.st_mode
            
            # Check that others don't have write permission (o+w)
            assert not (mode & 0o002), "App directory is world-writable"
            
            # Check Python files are not executable by others
            for py_file in app_dir.rglob("*.py"):
                py_stat = py_file.stat()
                py_mode = py_stat.st_mode
                # Should not be world-writable
                assert not (py_mode & 0o002), f"Python file {py_file} is world-writable"
    
    def test_environment_variables_security(self):
        """Test that security-related environment variables are set."""
        # Python security settings should be enabled
        assert os.environ.get("PYTHONUNBUFFERED") == "1"
        assert os.environ.get("PYTHONDONTWRITEBYTECODE") == "1"
        
        # Python hash seed should be set for security
        pythonhashseed = os.environ.get("PYTHONHASHSEED")
        assert pythonhashseed is not None
        assert pythonhashseed != "" and pythonhashseed != "0"
    
    def test_process_limits(self):
        """Test that process limits are configured."""
        try:
            import resource
            
            # Check file descriptor limit
            soft_fd, hard_fd = resource.getrlimit(resource.RLIMIT_NOFILE)
            assert soft_fd > 0, "File descriptor limit not set"
            assert soft_fd <= 65536, "File descriptor limit too high"
            
            # Check process limit
            soft_proc, hard_proc = resource.getrlimit(resource.RLIMIT_NPROC)
            assert soft_proc > 0, "Process limit not set"
            assert soft_proc <= 4096, "Process limit too high"
            
        except ImportError:
            pytest.skip("Resource module not available")
    
    def test_no_development_tools(self):
        """Test that development tools are not installed in production image."""
        dev_tools = ["gcc", "g++", "make", "cmake", "git"]
        
        for tool in dev_tools:
            result = subprocess.run(["which", tool], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                pytest.warnings.warn(f"Development tool {tool} found in production image")
    
    def test_package_manager_cache_cleaned(self):
        """Test that package manager caches are cleaned."""
        cache_dirs = [
            "/var/cache/apt/archives",
            "/var/lib/apt/lists",
            "/tmp",
            "/var/tmp"
        ]
        
        for cache_dir in cache_dirs:
            if os.path.exists(cache_dir):
                files = list(Path(cache_dir).iterdir()) if Path(cache_dir).is_dir() else []
                if len(files) > 5:  # Allow some files but not excessive caching
                    pytest.warnings.warn(f"Cache directory {cache_dir} contains {len(files)} files")
    
    def test_sensitive_files_not_present(self):
        """Test that sensitive files are not present in the container."""
        sensitive_files = [
            "/etc/shadow",
            "/etc/ssh/ssh_host_rsa_key",
            "/root/.ssh/id_rsa",
            "/home/*/.ssh/id_rsa"
        ]
        
        for sensitive_file in sensitive_files:
            if "*" in sensitive_file:
                import glob
                matches = glob.glob(sensitive_file)
                assert len(matches) == 0, f"Sensitive files found: {matches}"
            else:
                assert not os.path.exists(sensitive_file), f"Sensitive file exists: {sensitive_file}"
    
    def test_network_configuration(self):
        """Test network configuration security."""
        try:
            # Test that we can't bind to privileged ports
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            
            try:
                sock.bind(("", 80))
                pytest.fail("Should not be able to bind to privileged port 80")
            except PermissionError:
                # This is expected for non-root users
                pass
            except OSError as e:
                if "Permission denied" in str(e):
                    pass  # Expected
                else:
                    raise
            finally:
                sock.close()
                
        except ImportError:
            pytest.skip("Socket module not available")
    
    def test_readonly_filesystem_areas(self):
        """Test that certain filesystem areas are read-only or protected."""
        protected_areas = ["/etc", "/bin", "/sbin", "/usr/bin", "/usr/sbin"]
        
        for area in protected_areas:
            if os.path.exists(area):
                # Try to create a test file to see if it's writable
                test_file = os.path.join(area, "security_test_file")
                try:
                    with open(test_file, "w") as f:
                        f.write("test")
                    # If we get here, the area is writable (not ideal)
                    os.remove(test_file)
                    pytest.warnings.warn(f"Protected area {area} is writable")
                except (PermissionError, OSError):
                    # This is expected - area should be read-only
                    pass
    
    def test_python_security_settings(self):
        """Test Python-specific security settings."""
        import sys
        
        # Check Python optimization
        if hasattr(sys, "flags"):
            # In production, optimization should be enabled
            if os.environ.get("PYTHONOPTIMIZE"):
                assert sys.flags.optimize > 0, "Python optimization not enabled"
        
        # Check that __pycache__ creation is disabled
        assert os.environ.get("PYTHONDONTWRITEBYTECODE") == "1"
        
        # Check hash randomization
        hash_random = os.environ.get("PYTHONHASHSEED")
        assert hash_random != "0", "Python hash randomization disabled"


class TestApplicationSecurity:
    """Test application-level security within the container."""
    
    def test_application_files_present(self):
        """Test that required application files are present."""
        required_files = [
            "/app/main.py",
            "/app/config.py",
            "/app/logging_config.py"
        ]
        
        for file_path in required_files:
            assert os.path.exists(file_path), f"Required file missing: {file_path}"
    
    def test_configuration_security(self):
        """Test application configuration security."""
        # Import should work without errors
        import sys
        sys.path.insert(0, '/app')
        
        try:
            from app.config import get_config
            config = get_config()
            
            # JWT secret should be set and strong
            jwt_secret = getattr(config, 'JWT_SECRET', None)
            if jwt_secret:
                assert len(jwt_secret) >= 32, "JWT secret too short"
            
            # Database URL should not contain plaintext passwords in logs
            db_url = getattr(config, 'DATABASE_URL', '')
            if db_url and "://" in db_url:
                # Basic check that it's not obviously insecure
                assert "password" not in db_url.lower() or "localhost" in db_url.lower()
                
        except ImportError as e:
            pytest.skip(f"Could not import config: {e}")
    
    def test_logging_configuration(self):
        """Test that logging is configured securely."""
        try:
            import sys
            sys.path.insert(0, '/app')
            
            from app.logging_config import get_logger
            logger = get_logger("test")
            
            # Logger should be configured
            assert logger is not None
            assert len(logger.handlers) > 0
            
        except ImportError as e:
            pytest.skip(f"Could not import logging config: {e}")
    
    def test_no_debug_mode(self):
        """Test that debug mode is disabled in production."""
        debug_indicators = [
            "DEBUG=true",
            "DEBUG=True", 
            "DEVELOPMENT_MODE=true",
            "FLASK_DEBUG=1"
        ]
        
        for indicator in debug_indicators:
            key, value = indicator.split("=")
            env_value = os.environ.get(key, "").lower()
            assert env_value not in ["true", "1", "yes"], f"Debug mode enabled: {key}={env_value}"


class TestDependencySecurity:
    """Test dependency security within the container."""
    
    def test_python_version_security(self):
        """Test that Python version is recent and secure."""
        import sys
        
        version = sys.version_info
        
        # Should be Python 3.8+ for security features
        assert version.major == 3, f"Not using Python 3: {version}"
        assert version.minor >= 8, f"Python version too old: {version}"
        
        # Warn if not on a recent version
        if version.minor < 11:
            pytest.warnings.warn(f"Python version {version} may have security vulnerabilities")
    
    def test_critical_packages_present(self):
        """Test that critical security packages are available."""
        critical_packages = [
            "cryptography",
            "passlib", 
            "bcrypt",
            "jwt"
        ]
        
        for package in critical_packages:
            try:
                __import__(package)
            except ImportError:
                pytest.warnings.warn(f"Critical security package {package} not available")
    
    def test_no_vulnerable_packages(self):
        """Test for obviously vulnerable package versions."""
        # Check for old versions of security-critical packages
        vulnerable_versions = {
            "urllib3": "1.26.0",  # Example - should be newer
            "requests": "2.25.0",  # Example - should be newer
            "cryptography": "3.0.0"  # Example - should be newer
        }
        
        for package, min_version in vulnerable_versions.items():
            try:
                module = __import__(package)
                if hasattr(module, "__version__"):
                    version = module.__version__
                    # Basic version comparison (simplified)
                    if version < min_version:
                        pytest.warnings.warn(f"Package {package} version {version} may be vulnerable")
            except ImportError:
                pass  # Package not installed
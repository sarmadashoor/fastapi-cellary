"""
Test suite for Celery worker security hardening.

Tests task signature validation, worker isolation, and result backend security.
"""

import pytest
import os
import time
from unittest.mock import Mock, patch, MagicMock
from celery.exceptions import SecurityError

from app.tasks.security import (
    SecureTask, TaskSignatureValidator, WorkerSecurityManager,
    RedisSecurityManager, secure_task
)


class TestSecureTask:
    """Test secure task implementation."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.secure_task = SecureTask()
        self.secure_task.name = "test_task"
    
    def test_secure_task_initialization(self):
        """Test secure task initializes correctly."""
        assert hasattr(self.secure_task, 'security_logger')
        assert self.secure_task.security_logger is not None
    
    def test_apply_async_adds_security_headers(self):
        """Test that apply_async adds security headers."""
        with patch.object(SecureTask, '__bases__', (Mock,)):
            mock_super = Mock()
            mock_super.apply_async.return_value = Mock()
            
            with patch('builtins.super', return_value=mock_super):
                options = {}
                self.secure_task.apply_async(args=('test',), kwargs={'key': 'value'}, **options)
                
                # Check that headers were added
                assert 'headers' in options
                assert 'security_version' in options['headers']
                assert 'timestamp' in options['headers']
                assert 'source' in options['headers']
                assert options['headers']['security_version'] == '1.0'
                assert options['headers']['source'] == 'fastapi-celery-app'
    
    def test_validate_task_args_size_limit(self):
        """Test task arguments size validation."""
        # Create overly large arguments
        large_arg = 'x' * (1024 * 1024 + 1)  # 1MB + 1 byte
        
        with pytest.raises(SecurityError, match="Task arguments exceed size limit"):
            self.secure_task._validate_task_args((large_arg,))
    
    def test_validate_task_args_dangerous_patterns(self):
        """Test detection of dangerous patterns in arguments."""
        dangerous_args = [
            "eval('malicious code')",
            "exec('harmful code')",
            "__import__('os').system('rm -rf /')"
        ]
        
        for dangerous_arg in dangerous_args:
            with pytest.raises(SecurityError, match="Dangerous pattern detected"):
                self.secure_task._validate_task_args((dangerous_arg,))
    
    def test_validate_task_kwargs_size_limit(self):
        """Test task kwargs size validation."""
        # Create overly large kwargs
        large_value = 'x' * (1024 * 1024 + 1)  # 1MB + 1 byte
        large_kwargs = {'key': large_value}
        
        with pytest.raises(SecurityError, match="Task kwargs exceed size limit"):
            self.secure_task._validate_task_kwargs(large_kwargs)
    
    def test_validate_task_kwargs_dangerous_keys(self):
        """Test detection of dangerous keys in kwargs."""
        dangerous_kwargs = [
            {'__class__': 'dangerous'},
            {'__globals__': 'malicious'},
            {'__builtins__': 'harmful'}
        ]
        
        for dangerous_kwarg in dangerous_kwargs:
            with pytest.raises(SecurityError, match="Dangerous key detected"):
                self.secure_task._validate_task_kwargs(dangerous_kwarg)
    
    def test_validate_safe_args_and_kwargs(self):
        """Test that safe arguments and kwargs pass validation."""
        safe_args = ('normal_string', 123, {'safe': 'dict'})
        safe_kwargs = {'normal_key': 'normal_value', 'number': 456}
        
        # Should not raise any exceptions
        self.secure_task._validate_task_args(safe_args)
        self.secure_task._validate_task_kwargs(safe_kwargs)


class TestTaskSignatureValidator:
    """Test task signature validation."""
    
    def setup_method(self):
        """Setup test fixtures."""
        os.environ['CELERY_SECURITY_KEY'] = 'test_secret_key_for_signatures'
        self.validator = TaskSignatureValidator()
    
    def teardown_method(self):
        """Cleanup after tests."""
        if 'CELERY_SECURITY_KEY' in os.environ:
            del os.environ['CELERY_SECURITY_KEY']
    
    def test_signature_generation(self):
        """Test task signature generation."""
        task_name = "test_task"
        args = ('arg1', 'arg2')
        kwargs = {'key1': 'value1', 'key2': 'value2'}
        
        signature = self.validator.sign_task(task_name, args, kwargs)
        
        assert signature is not None
        assert len(signature) == 64  # SHA256 hex digest length
        assert isinstance(signature, str)
    
    def test_signature_verification_success(self):
        """Test successful signature verification."""
        task_name = "test_task"
        args = ('arg1', 'arg2')
        kwargs = {'key1': 'value1'}
        
        signature = self.validator.sign_task(task_name, args, kwargs)
        is_valid = self.validator.verify_task_signature(task_name, args, kwargs, signature)
        
        assert is_valid is True
    
    def test_signature_verification_failure(self):
        """Test signature verification failure with tampered data."""
        task_name = "test_task"
        args = ('arg1', 'arg2')
        kwargs = {'key1': 'value1'}
        
        signature = self.validator.sign_task(task_name, args, kwargs)
        
        # Verify with tampered arguments
        tampered_args = ('tampered_arg1', 'arg2')
        is_valid = self.validator.verify_task_signature(task_name, tampered_args, kwargs, signature)
        
        assert is_valid is False
    
    def test_signature_deterministic(self):
        """Test that signature generation is deterministic."""
        task_name = "test_task"
        args = ('arg1', 'arg2')
        kwargs = {'key2': 'value2', 'key1': 'value1'}  # Different order
        
        signature1 = self.validator.sign_task(task_name, args, kwargs)
        signature2 = self.validator.sign_task(task_name, args, kwargs)
        
        assert signature1 == signature2
    
    def test_no_secret_key_behavior(self):
        """Test behavior when no secret key is configured."""
        if 'CELERY_SECURITY_KEY' in os.environ:
            del os.environ['CELERY_SECURITY_KEY']
        
        validator = TaskSignatureValidator()
        
        signature = validator.sign_task("test", (), {})
        assert signature == ''
        
        is_valid = validator.verify_task_signature("test", (), {}, "any_signature")
        assert is_valid is True  # Should skip validation


class TestWorkerSecurityManager:
    """Test worker security management."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.worker_security = WorkerSecurityManager()
        self.mock_app = Mock()
        self.mock_app.conf = Mock()
    
    def test_security_manager_initialization(self):
        """Test security manager initializes with correct defaults."""
        assert self.worker_security.resource_limits['max_memory_mb'] == 512
        assert self.worker_security.resource_limits['max_execution_time'] == 300
        assert self.worker_security.resource_limits['max_tasks_per_child'] == 50
    
    def test_configure_worker_security(self):
        """Test worker security configuration."""
        self.worker_security.configure_worker_security(self.mock_app)
        
        # Verify security configuration was applied
        self.mock_app.conf.update.assert_called_once()
        
        # Check the configuration parameters
        call_args = self.mock_app.conf.update.call_args[1]
        assert call_args['task_reject_on_worker_lost'] is True
        assert call_args['task_acks_late'] is True
        assert call_args['worker_prefetch_multiplier'] == 1
        assert call_args['task_time_limit'] == 300
        assert call_args['task_soft_time_limit'] == 270
        assert call_args['worker_max_tasks_per_child'] == 50
        assert call_args['accept_content'] == ['json']
        assert call_args['task_serializer'] == 'json'
        assert call_args['result_serializer'] == 'json'
    
    def test_secure_task_routes(self):
        """Test secure task routing configuration."""
        routes = self.worker_security._get_secure_task_routes()
        
        assert 'app.tasks.words.*' in routes
        assert 'app.workers.resume_parser.*' in routes
        assert 'app.tasks.debug.*' in routes
        assert '*' in routes
        
        assert routes['app.tasks.words.*']['queue'] == 'processing'
        assert routes['app.workers.resume_parser.*']['queue'] == 'file_processing'
        assert routes['app.tasks.debug.*']['queue'] == 'debug'
        assert routes['*']['queue'] == 'default'
    
    @patch.dict(os.environ, {
        'CELERY_MAX_MEMORY_MB': '1024',
        'CELERY_MAX_EXECUTION_TIME': '600',
        'CELERY_MAX_TASKS_PER_CHILD': '100'
    })
    def test_environment_variable_configuration(self):
        """Test configuration from environment variables."""
        worker_security = WorkerSecurityManager()
        
        assert worker_security.resource_limits['max_memory_mb'] == 1024
        assert worker_security.resource_limits['max_execution_time'] == 600
        assert worker_security.resource_limits['max_tasks_per_child'] == 100


class TestRedisSecurityManager:
    """Test Redis backend security management."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.redis_security = RedisSecurityManager()
    
    def test_redis_security_manager_initialization(self):
        """Test Redis security manager initialization."""
        assert hasattr(self.redis_security, 'redis_password')
        assert hasattr(self.redis_security, 'redis_ssl_enabled')
    
    def test_secure_redis_config_basic(self):
        """Test basic Redis configuration."""
        config = self.redis_security.get_secure_redis_config()
        
        assert 'host' in config
        assert 'port' in config
        assert 'db' in config
        assert 'socket_timeout' in config
        assert 'socket_connect_timeout' in config
        assert 'socket_keepalive' in config
        assert 'connection_pool_kwargs' in config
        assert 'health_check_interval' in config
        
        assert config['socket_timeout'] == 30.0
        assert config['socket_connect_timeout'] == 30.0
        assert config['socket_keepalive'] is True
        assert config['health_check_interval'] == 30
    
    @patch.dict(os.environ, {
        'REDIS_PASSWORD': 'test_password',
        'REDIS_HOST': 'test_host',
        'REDIS_PORT': '6380'
    })
    def test_secure_redis_config_with_auth(self):
        """Test Redis configuration with authentication."""
        redis_security = RedisSecurityManager()
        config = redis_security.get_secure_redis_config()
        
        assert config['password'] == 'test_password'
        assert config['host'] == 'test_host'
        assert config['port'] == 6380
    
    @patch.dict(os.environ, {
        'REDIS_SSL_ENABLED': 'true',
        'REDIS_SSL_CA_CERTS': '/path/to/ca.crt',
        'REDIS_SSL_CERT_FILE': '/path/to/cert.crt',
        'REDIS_SSL_KEY_FILE': '/path/to/key.key'
    })
    def test_secure_redis_config_with_ssl(self):
        """Test Redis configuration with SSL."""
        redis_security = RedisSecurityManager()
        config = redis_security.get_secure_redis_config()
        
        assert config['ssl'] is True
        assert config['ssl_check_hostname'] is False
        assert config['ssl_cert_reqs'] is None
        assert config['ssl_ca_certs'] == '/path/to/ca.crt'
        assert config['ssl_certfile'] == '/path/to/cert.crt'
        assert config['ssl_keyfile'] == '/path/to/key.key'
    
    def test_validate_redis_security(self):
        """Test Redis security validation."""
        mock_redis = Mock()
        mock_redis.info.return_value = {'auth': True}
        mock_redis.connection_pool.connection_kwargs = {'ssl': True}
        mock_redis.config_get.return_value = {}
        mock_redis.execute_command.return_value = ['default user']
        
        results = self.redis_security.validate_redis_security(mock_redis)
        
        assert 'authentication_enabled' in results
        assert 'ssl_enabled' in results
        assert 'acl_enabled' in results
        assert 'dangerous_commands' in results
        assert 'security_issues' in results
        
        assert results['authentication_enabled'] is True
        assert results['ssl_enabled'] is True


class TestSecureTaskDecorator:
    """Test secure task decorator."""
    
    def test_secure_task_decorator(self):
        """Test that secure task decorator works correctly."""
        @secure_task()
        def sample_task(x, y):
            return x + y
        
        # Check that the task is wrapped properly
        assert hasattr(sample_task, '__wrapped__')
        assert callable(sample_task)
    
    def test_secure_task_execution_logging(self):
        """Test that secure task execution is logged."""
        with patch('app.tasks.security.security_logger') as mock_logger:
            @secure_task()
            def sample_task(x, y):
                return x + y
            
            result = sample_task(2, 3)
            assert result == 5
            
            # Check that success was logged
            mock_logger.info.assert_called()
            call_args = mock_logger.info.call_args
            assert 'Secure task completed successfully' in call_args[0][0]
    
    def test_secure_task_failure_logging(self):
        """Test that secure task failures are logged."""
        with patch('app.tasks.security.security_logger') as mock_logger:
            @secure_task()
            def failing_task():
                raise ValueError("Test error")
            
            with pytest.raises(ValueError):
                failing_task()
            
            # Check that failure was logged
            mock_logger.error.assert_called()
            call_args = mock_logger.error.call_args
            assert 'Secure task failed' in call_args[0][0]


class TestCelerySignalHandlers:
    """Test Celery signal handlers for security monitoring."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.worker_security = WorkerSecurityManager()
    
    def test_signal_handler_registration(self):
        """Test that signal handlers are registered."""
        mock_app = Mock()
        
        with patch('app.tasks.security.task_prerun') as mock_prerun:
            with patch('app.tasks.security.task_postrun') as mock_postrun:
                with patch('app.tasks.security.task_failure') as mock_failure:
                    with patch('app.tasks.security.worker_ready') as mock_ready:
                        self.worker_security._register_security_signals()
                        
                        # Verify that signal handlers were connected
                        mock_prerun.connect.assert_called()
                        mock_postrun.connect.assert_called()
                        mock_failure.connect.assert_called()
                        mock_ready.connect.assert_called()


class TestTaskSecurityValidation:
    """Test task security validation scenarios."""
    
    def test_task_with_valid_signature(self):
        """Test task execution with valid signature."""
        validator = TaskSignatureValidator()
        validator.secret_key = 'test_key'
        
        task_name = "secure_task"
        args = ('safe_arg',)
        kwargs = {'safe_key': 'safe_value'}
        
        signature = validator.sign_task(task_name, args, kwargs)
        is_valid = validator.verify_task_signature(task_name, args, kwargs, signature)
        
        assert is_valid is True
    
    def test_task_size_limits(self):
        """Test task size limits are enforced."""
        secure_task = SecureTask()
        
        # Test argument size limit
        large_args = ('x' * (1024 * 1024 + 1),)  # > 1MB
        with pytest.raises(SecurityError):
            secure_task._validate_task_args(large_args)
        
        # Test kwargs size limit
        large_kwargs = {'key': 'x' * (1024 * 1024 + 1)}  # > 1MB
        with pytest.raises(SecurityError):
            secure_task._validate_task_kwargs(large_kwargs)
    
    def test_dangerous_pattern_detection(self):
        """Test detection of dangerous patterns in task data."""
        secure_task = SecureTask()
        
        dangerous_patterns = [
            "eval('malicious')",
            "exec('harmful')",
            "__import__('os')"
        ]
        
        for pattern in dangerous_patterns:
            with pytest.raises(SecurityError):
                secure_task._validate_task_args((pattern,))


class TestResourceLimits:
    """Test resource limit enforcement."""
    
    def test_memory_limit_configuration(self):
        """Test memory limit configuration."""
        with patch.dict(os.environ, {'CELERY_MAX_MEMORY_MB': '1024'}):
            worker_security = WorkerSecurityManager()
            assert worker_security.resource_limits['max_memory_mb'] == 1024
    
    def test_execution_time_limit_configuration(self):
        """Test execution time limit configuration."""
        with patch.dict(os.environ, {'CELERY_MAX_EXECUTION_TIME': '600'}):
            worker_security = WorkerSecurityManager()
            assert worker_security.resource_limits['max_execution_time'] == 600
    
    def test_tasks_per_child_limit_configuration(self):
        """Test tasks per child limit configuration."""
        with patch.dict(os.environ, {'CELERY_MAX_TASKS_PER_CHILD': '100'}):
            worker_security = WorkerSecurityManager()
            assert worker_security.resource_limits['max_tasks_per_child'] == 100


@pytest.mark.integration
class TestCelerySecurityIntegration:
    """Integration tests for Celery security hardening."""
    
    def test_celery_app_security_configuration(self):
        """Test that Celery app is configured with security settings."""
        from app.celery_app import celery_app
        
        # Check security-related configuration
        assert celery_app.conf.task_reject_on_worker_lost is True
        assert celery_app.conf.task_acks_late is True
        assert celery_app.conf.worker_prefetch_multiplier == 1
        assert celery_app.conf.accept_content == ['json']
        assert celery_app.conf.task_serializer == 'json'
        assert celery_app.conf.result_serializer == 'json'
    
    def test_worker_resource_limits(self):
        """Test worker resource limits are configured."""
        from app.celery_app import celery_app
        
        assert celery_app.conf.task_time_limit == 300
        assert celery_app.conf.task_soft_time_limit == 270
        assert celery_app.conf.worker_max_tasks_per_child == 50
        assert celery_app.conf.worker_max_memory_per_child == 512000
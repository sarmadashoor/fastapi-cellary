"""
Celery worker security hardening.

Implements task signature validation, worker isolation, and result backend security.
"""

import os
import time
import hashlib
import hmac
import json
from typing import Any, Dict, Optional, List
from functools import wraps
from celery import Task
from celery.exceptions import SecurityError, WorkerLostError
from celery.signals import (
    task_prerun, task_postrun, task_failure, task_retry,
    worker_ready, worker_shutdown, beat_init
)

from app.logging_config import get_logger

logger = get_logger(__name__)
security_logger = get_logger("celery.security")


class SecureTask(Task):
    """Base task class with security hardening."""
    
    def __init__(self):
        super().__init__()
        self.security_logger = security_logger
        
    def apply_async(self, args=None, kwargs=None, **options):
        """Override apply_async to add security validation."""
        # Add security headers
        options.setdefault('headers', {})
        options['headers'].update({
            'security_version': '1.0',
            'timestamp': int(time.time()),
            'source': 'fastapi-celery-app'
        })
        
        # Validate task arguments
        if args:
            self._validate_task_args(args)
        if kwargs:
            self._validate_task_kwargs(kwargs)
            
        return super().apply_async(args, kwargs, **options)
    
    def _validate_task_args(self, args: tuple):
        """Validate task arguments for security."""
        # Check for overly large arguments
        args_size = sum(len(str(arg)) for arg in args)
        if args_size > 1024 * 1024:  # 1MB limit
            raise SecurityError("Task arguments exceed size limit")
        
        # Check for dangerous patterns
        for arg in args:
            if isinstance(arg, str):
                if any(dangerous in arg.lower() for dangerous in ['eval(', 'exec(', '__import__']):
                    raise SecurityError("Dangerous pattern detected in task arguments")
    
    def _validate_task_kwargs(self, kwargs: dict):
        """Validate task keyword arguments for security."""
        # Check for overly large kwargs
        kwargs_size = sum(len(str(k)) + len(str(v)) for k, v in kwargs.items())
        if kwargs_size > 1024 * 1024:  # 1MB limit
            raise SecurityError("Task kwargs exceed size limit")
        
        # Check for dangerous keys
        dangerous_keys = ['__class__', '__globals__', '__builtins__']
        if any(key in kwargs for key in dangerous_keys):
            raise SecurityError("Dangerous key detected in task kwargs")


class TaskSignatureValidator:
    """Validates task signatures for authenticity."""
    
    def __init__(self):
        self.secret_key = os.environ.get('CELERY_SECURITY_KEY', '')
        if not self.secret_key:
            logger.warning("CELERY_SECURITY_KEY not set - task signature validation disabled")
    
    def sign_task(self, task_name: str, args: tuple, kwargs: dict) -> str:
        """Generate HMAC signature for task."""
        if not self.secret_key:
            return ''
        
        # Create canonical representation
        canonical = json.dumps({
            'task': task_name,
            'args': args,
            'kwargs': kwargs
        }, sort_keys=True, separators=(',', ':'))
        
        # Generate HMAC signature
        signature = hmac.new(
            self.secret_key.encode(),
            canonical.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return signature
    
    def verify_task_signature(self, task_name: str, args: tuple, kwargs: dict, signature: str) -> bool:
        """Verify task signature."""
        if not self.secret_key or not signature:
            return True  # Skip validation if not configured
        
        expected_signature = self.sign_task(task_name, args, kwargs)
        return hmac.compare_digest(signature, expected_signature)


class WorkerSecurityManager:
    """Manages Celery worker security configuration."""
    
    def __init__(self):
        self.signature_validator = TaskSignatureValidator()
        self.resource_limits = {
            'max_memory_mb': int(os.environ.get('CELERY_MAX_MEMORY_MB', '512')),
            'max_execution_time': int(os.environ.get('CELERY_MAX_EXECUTION_TIME', '300')),
            'max_tasks_per_child': int(os.environ.get('CELERY_MAX_TASKS_PER_CHILD', '50'))
        }
        
    def configure_worker_security(self, app):
        """Configure security settings for Celery worker."""
        # Set resource limits
        app.conf.update(
            # Worker process limits
            worker_max_memory_per_child=self.resource_limits['max_memory_mb'] * 1024,  # Convert to KB
            task_time_limit=self.resource_limits['max_execution_time'],
            task_soft_time_limit=self.resource_limits['max_execution_time'] - 30,
            worker_max_tasks_per_child=self.resource_limits['max_tasks_per_child'],
            
            # Security settings
            task_reject_on_worker_lost=True,
            task_acks_late=True,
            worker_prefetch_multiplier=1,
            
            # Result backend security
            result_expires=3600,  # 1 hour
            result_persistent=False,
            
            # Task routing security
            task_routes=self._get_secure_task_routes(),
            
            # Serialization security
            accept_content=['json'],  # Only JSON, no pickle
            task_serializer='json',
            result_serializer='json',
            
            # Redis security (if using Redis backend)
            redis_max_connections=20,
            redis_socket_timeout=30.0,
            redis_socket_connect_timeout=30.0,
        )
        
        # Register signal handlers
        self._register_security_signals()
        
        logger.info("Configured Celery worker security",
                   extra={
                       "max_memory_mb": self.resource_limits['max_memory_mb'],
                       "max_execution_time": self.resource_limits['max_execution_time'],
                       "max_tasks_per_child": self.resource_limits['max_tasks_per_child']
                   })
    
    def _get_secure_task_routes(self) -> Dict[str, Dict[str, str]]:
        """Define secure task routing configuration."""
        return {
            # Route sensitive tasks to dedicated queues
            'app.tasks.words.*': {'queue': 'processing'},
            'app.workers.resume_parser.*': {'queue': 'file_processing'},
            'app.tasks.debug.*': {'queue': 'debug'},
            
            # Default queue for other tasks
            '*': {'queue': 'default'}
        }
    
    def _register_security_signals(self):
        """Register Celery signal handlers for security monitoring."""
        
        @task_prerun.connect
        def task_prerun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, **kwds):
            """Log task execution start and validate security."""
            security_logger.info("Task execution started",
                               extra={
                                   "event": "task_start",
                                   "task_id": task_id,
                                   "task_name": sender,
                                   "args_count": len(args) if args else 0,
                                   "kwargs_count": len(kwargs) if kwargs else 0
                               })
            
            # Validate task signature if configured
            if hasattr(task, 'request') and task.request.headers:
                signature = task.request.headers.get('task_signature')
                if signature:
                    if not self.signature_validator.verify_task_signature(sender, args, kwargs, signature):
                        security_logger.error("Invalid task signature detected",
                                            extra={
                                                "event": "security_violation",
                                                "task_id": task_id,
                                                "task_name": sender,
                                                "violation_type": "invalid_signature"
                                            })
                        raise SecurityError("Invalid task signature")
        
        @task_postrun.connect
        def task_postrun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, retval=None, state=None, **kwds):
            """Log task completion."""
            security_logger.info("Task execution completed",
                               extra={
                                   "event": "task_complete",
                                   "task_id": task_id,
                                   "task_name": sender,
                                   "state": state,
                                   "execution_time": getattr(task, 'execution_time', None)
                               })
        
        @task_failure.connect
        def task_failure_handler(sender=None, task_id=None, exception=None, einfo=None, **kwds):
            """Log task failures for security analysis."""
            security_logger.error("Task execution failed",
                                extra={
                                    "event": "task_failure",
                                    "task_id": task_id,
                                    "task_name": sender,
                                    "exception": str(exception),
                                    "exception_type": type(exception).__name__
                                })
            
            # Check for security-related failures
            if isinstance(exception, (SecurityError, WorkerLostError)):
                security_logger.critical("Security-related task failure",
                                       extra={
                                           "event": "security_incident",
                                           "task_id": task_id,
                                           "task_name": sender,
                                           "security_exception": str(exception)
                                       })
        
        @task_retry.connect
        def task_retry_handler(sender=None, task_id=None, reason=None, einfo=None, **kwds):
            """Log task retries for monitoring."""
            security_logger.warning("Task retry triggered",
                                  extra={
                                      "event": "task_retry",
                                      "task_id": task_id,
                                      "task_name": sender,
                                      "retry_reason": str(reason)
                                  })
        
        @worker_ready.connect
        def worker_ready_handler(sender=None, **kwds):
            """Log worker startup."""
            security_logger.info("Celery worker started",
                               extra={
                                   "event": "worker_start",
                                   "worker_id": sender.hostname if sender else "unknown",
                                   "resource_limits": self.resource_limits
                               })
        
        @worker_shutdown.connect
        def worker_shutdown_handler(sender=None, **kwds):
            """Log worker shutdown."""
            security_logger.info("Celery worker shutting down",
                               extra={
                                   "event": "worker_shutdown",
                                   "worker_id": sender.hostname if sender else "unknown"
                               })


class RedisSecurityManager:
    """Manages Redis backend security for Celery."""
    
    def __init__(self):
        self.redis_password = os.environ.get('REDIS_PASSWORD')
        self.redis_ssl_enabled = os.environ.get('REDIS_SSL_ENABLED', 'false').lower() == 'true'
    
    def get_secure_redis_config(self) -> Dict[str, Any]:
        """Get secure Redis configuration for Celery."""
        config = {
            'host': os.environ.get('REDIS_HOST', 'redis'),
            'port': int(os.environ.get('REDIS_PORT', '6379')),
            'db': int(os.environ.get('REDIS_DB', '0')),
            'socket_timeout': 30.0,
            'socket_connect_timeout': 30.0,
            'socket_keepalive': True,
            'socket_keepalive_options': {},
            'connection_pool_kwargs': {
                'max_connections': 50,
                'retry_on_timeout': True
            },
            'health_check_interval': 30
        }
        
        # Add authentication if configured
        if self.redis_password:
            config['password'] = self.redis_password
        
        # Add SSL configuration if enabled
        if self.redis_ssl_enabled:
            config.update({
                'ssl': True,
                'ssl_check_hostname': False,
                'ssl_cert_reqs': None,
                'ssl_ca_certs': os.environ.get('REDIS_SSL_CA_CERTS'),
                'ssl_certfile': os.environ.get('REDIS_SSL_CERT_FILE'),
                'ssl_keyfile': os.environ.get('REDIS_SSL_KEY_FILE')
            })
        
        return config
    
    def validate_redis_security(self, redis_client) -> Dict[str, Any]:
        """Validate Redis security configuration."""
        results = {
            "authentication_enabled": False,
            "ssl_enabled": False,
            "acl_enabled": False,
            "dangerous_commands": [],
            "security_issues": []
        }
        
        try:
            # Check authentication
            info = redis_client.info()
            results["authentication_enabled"] = info.get('auth', False)
            
            # Check SSL
            if hasattr(redis_client.connection_pool, 'connection_kwargs'):
                conn_kwargs = redis_client.connection_pool.connection_kwargs
                results["ssl_enabled"] = conn_kwargs.get('ssl', False)
            
            # Check for dangerous commands
            try:
                config = redis_client.config_get()
                
                # Check if dangerous commands are enabled
                dangerous_commands = ['FLUSHDB', 'FLUSHALL', 'EVAL', 'DEBUG', 'CONFIG']
                for cmd in dangerous_commands:
                    try:
                        redis_client.execute_command('COMMAND', 'INFO', cmd)
                        results["dangerous_commands"].append(cmd)
                    except:
                        pass  # Command disabled or not available
                
                # Check ACL support (Redis 6+)
                try:
                    acl_users = redis_client.execute_command('ACL', 'LIST')
                    results["acl_enabled"] = len(acl_users) > 1  # More than default user
                except:
                    results["acl_enabled"] = False
                    
            except Exception as e:
                results["security_issues"].append(f"Config check failed: {str(e)}")
            
            # Security recommendations
            if not results["authentication_enabled"]:
                results["security_issues"].append("Redis authentication not enabled")
            
            if not results["ssl_enabled"]:
                results["security_issues"].append("Redis SSL/TLS not enabled")
            
            if len(results["dangerous_commands"]) > 2:
                results["security_issues"].append("Multiple dangerous Redis commands available")
                
        except Exception as e:
            logger.error("Failed to validate Redis security",
                        extra={"error": str(e)})
            results["security_issues"].append(f"Redis security validation failed: {str(e)}")
        
        return results


# Global security manager instances
worker_security = WorkerSecurityManager()
redis_security = RedisSecurityManager()


def secure_task(*args, **kwargs):
    """Decorator to create secure Celery tasks."""
    def decorator(func):
        # Create task with secure base class
        task = SecureTask.bind(func)
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                
                # Log successful execution
                security_logger.info("Secure task completed successfully",
                                   extra={
                                       "event": "secure_task_success",
                                       "task_name": func.__name__,
                                       "execution_time": execution_time
                                   })
                return result
            except Exception as e:
                execution_time = time.time() - start_time
                
                # Log task failure
                security_logger.error("Secure task failed",
                                    extra={
                                        "event": "secure_task_failure", 
                                        "task_name": func.__name__,
                                        "execution_time": execution_time,
                                        "error": str(e)
                                    })
                raise
        
        return task(wrapper)
    
    return decorator
"""
Celery worker main and celery_app for tasks sender with security hardening.

Register all tasks from app/tasks with security configurations.
"""

import os.path
from typing import List

import app.config as app_config  # to not shadow global app var with FastAPI app
from celery import Celery
from fastapi.logger import logger
from kombu.exceptions import OperationalError
from app.tasks.security import worker_security, redis_security

mq_uri = app_config.get_config().mq_uri
logger.info(f"amqp_uri: {mq_uri}")


class CeleryConfig:
    """
    Celery configuration with security hardening.
    https://docs.celeryproject.org/en/latest/userguide/configuration.html#configuration-and-defaults
    """

    # Task execution security
    task_acks_late = True  # guarantee task completion but the task may be executed twice
    # if the worker crashes mid execution
    result_expires = 3600  # Results expire after 1 hour for security
    task_compression = "gzip"
    result_compression = "gzip"
    broker_connection_retry = True
    broker_connection_retry_on_startup = True
    
    # Security hardening
    task_reject_on_worker_lost = True
    worker_prefetch_multiplier = 1
    task_time_limit = 300  # 5 minutes max per task
    task_soft_time_limit = 270  # Soft limit at 4.5 minutes
    worker_max_tasks_per_child = 50  # Restart worker after 50 tasks
    worker_max_memory_per_child = 512000  # 512MB memory limit
    
    # Serialization security - only JSON, no pickle
    accept_content = ['json']
    task_serializer = 'json'
    result_serializer = 'json'
    
    # Result backend security
    result_persistent = False
    
    # Redis connection security
    redis_max_connections = 20
    redis_socket_timeout = 30.0
    redis_socket_connect_timeout = 30.0


def get_task_packages(path: str) -> List[str]:
    """Discover Celery task modules from directory structure.
    
    Args:
        path: Directory path to scan for Python task modules.
        
    Returns:
        List[str]: List of module paths for Celery task auto-discovery.
    """
    result = []
    for dirpath, dirnames, filenames in os.walk(path):
        for name in filenames:
            if "__" not in dirpath:  # exclude __pycache__
                result.append(
                    os.path.join(dirpath, name.split(".")[0]).replace("/", ".").replace("\\", "."),
                )
    return result


# Initialize Celery app but don't test connection immediately
task_modules = (
    get_task_packages(os.path.join("app", "tasks")) +
    get_task_packages(os.path.join("app", "workers"))
)
celery_app = Celery(
    "celery",
    backend=app_config.get_config().celery_backend_uri,
    broker=app_config.get_config().celery_broker_uri,
    include=task_modules,
)
celery_app.config_from_object(CeleryConfig)

# Apply security hardening
worker_security.configure_worker_security(celery_app)

print(
    f">>> celery_app: {app_config.get_config().celery_backend_uri}, {app_config.get_config().celery_broker_uri}",
)


# Test connection only when needed, with better error handling
def ensure_celery_connection():
    """Ensure celery connection is available."""
    try:
        celery_app.connection().ensure_connection(max_retries=3, timeout=15)
        logger.info(f"Connection to {mq_uri} established.")
        return True
    except OperationalError as e:
        logger.error(
            f"Connection to {app_config.get_config().celery_broker_uri} broker refused: {e}"
        )
        return False


celery_app.conf.task_default_queue = "main-queue"


if __name__ == "__main__":
    celery_app.worker_main()

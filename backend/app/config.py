"""Application configuration management using Pydantic Settings.

This module provides centralized configuration management for the FastAPI Celery
application, handling environment variables, database connections, Redis settings,
and other application parameters with validation and type safety.
"""

import logging
from functools import lru_cache
from typing import List, Tuple

import redis
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

API_V1_STR = "/api"


@lru_cache
def get_config() -> "Config":
    """Get cached application configuration instance.
    
    Returns:
        Config: Singleton configuration instance with environment variables loaded.
    """
    return Config()


log = logging.getLogger()


DB_HOST_DEFAUL = "postgres"
DB_POOL_SIZE_DEFAUL = "10"
DB_DATABASE_DEFAULT = "postgres"
DB_USER_DEFAULT = "postgres"
DB_PASSWORD_DEFAULT = "postgres"


class Config(BaseSettings):
    """Configuration with secure environment variable handling."""

    # Authentication settings
    admin_login: str = Field(default="admin", alias="ADMIN_LOGIN", description="Admin login username")
    admin_password: str = Field(default="admin", alias="ADMIN_PASSWORD", description="Admin password")
    jwt_secret_key: str = Field(
        default="default_secret_key_change_in_production",
        alias="JWT_SECRET_KEY",
        description="JWT signing secret",
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")

    # Database settings
    db_database: str = Field(default=DB_DATABASE_DEFAULT, alias="POSTGRES_DB")
    db_user: str = Field(default=DB_USER_DEFAULT, alias="POSTGRES_USER")
    db_password: str = Field(default=DB_PASSWORD_DEFAULT, alias="POSTGRES_PASSWORD")
    db_host: str = Field(default=DB_HOST_DEFAUL, alias="POSTGRES_HOST")
    db_pool_size: int = Field(default=int(DB_POOL_SIZE_DEFAUL), alias="DB_POOL_SIZE")

    # Message queue settings
    mq_user: str = Field(default="guest", alias="AMQP_USERNAME", description="Message queue username")
    mq_password: str = Field(
        default="guest",
        alias="AMQP_PASSWORD",
        description="Message queue password",
    )
    mq_host: str = Field(default="localhost", alias="AMQP_HOST", description="Message queue host")
    mq_port: str = Field(default="6379", alias="AMQP_PORT", description="Message queue port")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }

    def __init__(self, **kwargs) -> None:
        """Initialize configuration with environment variables and validation.
        
        Args:
            **kwargs: Additional configuration parameters.
        """
        super().__init__(**kwargs)
        log.info(
            f"Backend started with MQ '{self.mq_uri}' and DB '{self.db_uri}', celery '{self.celery_backend_uri}', '{self.celery_broker_uri}'",
        )
        
        # Validate security configuration on startup
        self._validate_security_config()
    
    @field_validator('jwt_secret_key')
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        """Validate JWT secret strength."""
        if v == "default_secret_key_change_in_production":
            log.warning("⚠️  SECURITY WARNING: Using default JWT secret in production is dangerous!")
        elif len(v) < 32:
            log.warning(f"⚠️  SECURITY WARNING: JWT secret is only {len(v)} characters. Recommended minimum: 32 characters")
        return v
    
    def _validate_security_config(self) -> None:
        """Validate overall security configuration."""
        security_issues = []
        
        # Check JWT secret
        if self.jwt_secret_key == "default_secret_key_change_in_production":
            security_issues.append("🔴 CRITICAL: Default JWT secret must be changed!")
        elif len(self.jwt_secret_key) < 32:
            security_issues.append(f"🟡 WARNING: JWT secret ({len(self.jwt_secret_key)} chars) should be at least 32 characters")
        
        # Check admin password
        if self.admin_password == "admin":
            security_issues.append("🔴 CRITICAL: Default admin password must be changed!")
        elif not self.admin_password.startswith("$2b$"):
            security_issues.append("🟡 WARNING: Admin password should be bcrypt hashed for security")
        
        # Check for other weak passwords
        weak_passwords = ["password", "123456", "admin123", "root", "default"]
        if self.admin_password in weak_passwords:
            security_issues.append("🔴 CRITICAL: Admin password is too weak!")
        
        # Log security issues
        if security_issues:
            log.warning("🛡️  SECURITY CONFIGURATION ISSUES DETECTED:")
            for issue in security_issues:
                log.warning(f"  {issue}")
            log.warning("🛡️  Please review and fix these security issues before deploying to production!")
        else:
            log.info("✅ Security configuration validation passed")
    
    def get_security_status(self) -> Tuple[bool, List[str]]:
        """Get current security status."""
        issues = []
        
        # JWT Secret validation
        if self.jwt_secret_key == "default_secret_key_change_in_production":
            issues.append("Default JWT secret in use")
        elif len(self.jwt_secret_key) < 32:
            issues.append(f"JWT secret too short ({len(self.jwt_secret_key)} chars)")
        
        # Password validation  
        if self.admin_password == "admin":
            issues.append("Default admin password in use")
        elif not self.admin_password.startswith("$2b$"):
            issues.append("Admin password not hashed")
        
        return len(issues) == 0, issues

    @property
    def db_uri(self) -> str:
        """Construct PostgreSQL database connection URI.
        
        Returns:
            str: Complete PostgreSQL connection string with credentials.
        """
        return (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}@"
            f"{self.db_host}/{self.db_database}"
        )

    @property
    def mq_uri(self) -> str:
        """Construct message queue connection URI for AMQP broker.
        
        Returns:
            str: PyAMQP connection string for message broker.
        """
        return f"pyamqp://{self.mq_user}:{self.mq_password}@{self.mq_host}:{self.mq_port}/"

    @property
    def redis_host(self) -> str:
        """Get Redis host from message queue configuration.
        
        Returns:
            str: Redis server hostname.
        """
        return self.mq_host

    @property
    def redis_port(self) -> int:
        """Get Redis port from message queue configuration.
        
        Returns:
            int: Redis server port number.
        """
        return int(self.mq_port)

    @property
    def redis_db(self) -> int:
        """Get Redis database number for application use.
        
        Returns:
            int: Redis database index (1 for application data).
        """
        return 1

    @property
    def redis(self) -> redis.Redis:  # type: ignore
        """Create Redis client instance with authentication.
        
        Returns:
            redis.Redis: Configured Redis client for application use.
        """
        return redis.Redis(
            host=self.redis_host,
            port=self.redis_port,
            password=self.redis_password,
            db=self.redis_db,
        )

    @property
    def redis_password(self) -> str:
        """Get Redis password from message queue configuration.
        
        Returns:
            str: Redis authentication password.
        """
        return self.mq_password

    @property
    def celery_broker_uri(self) -> str:
        """Construct Celery broker URI using Redis.
        
        Returns:
            str: Redis URI for Celery message broker.
        """
        return f"redis://:{self.mq_password}@{self.mq_host}:{self.mq_port}/0"

    @property
    def celery_backend_uri(self) -> str:
        """Construct Celery result backend URI using Redis.
        
        Returns:
            str: Redis URI for Celery result storage.
        """
        return self.celery_broker_uri

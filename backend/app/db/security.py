"""
Database security hardening for PostgreSQL connections.

Implements connection encryption, query logging, and privilege restrictions.
"""

import os
import ssl
import logging
from typing import Optional, Dict, Any
from urllib.parse import urlparse, parse_qs
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool
from sqlalchemy.sql import text

from app.logging_config import get_logger

logger = get_logger(__name__)


class DatabaseSecurityManager:
    """Manages database security configuration and monitoring."""
    
    def __init__(self):
        self.query_logger = get_logger("database.queries")
        self.security_logger = get_logger("database.security")
        
    def create_secure_engine(self, database_url: str, **kwargs) -> Engine:
        """
        Create a secure database engine with SSL and security configurations.
        
        Args:
            database_url: Database connection URL
            **kwargs: Additional engine configuration
            
        Returns:
            Configured SQLAlchemy engine with security hardening
        """
        # Parse URL for security validation
        parsed = urlparse(database_url)
        
        # Security validations
        if parsed.scheme not in ['postgresql', 'postgresql+psycopg2']:
            raise ValueError(f"Unsupported database scheme: {parsed.scheme}")
        
        if not parsed.hostname:
            raise ValueError("Database hostname is required")
            
        # Default secure engine configuration
        secure_config = {
            'poolclass': QueuePool,
            'pool_size': 5,
            'max_overflow': 10,
            'pool_timeout': 30,
            'pool_recycle': 3600,  # Recycle connections every hour
            'pool_pre_ping': True,  # Validate connections before use
            'echo': False,  # Disable SQL echoing in production
            'echo_pool': False,
            'connect_args': self._get_secure_connect_args(database_url)
        }
        
        # Override with provided kwargs
        secure_config.update(kwargs)
        
        # Create engine
        engine = create_engine(database_url, **secure_config)
        
        # Register security event listeners
        self._register_security_listeners(engine)
        
        logger.info("Created secure database engine",
                   extra={
                       "database_host": parsed.hostname,
                       "database_port": parsed.port or 5432,
                       "ssl_enabled": self._is_ssl_enabled(database_url),
                       "pool_size": secure_config["pool_size"]
                   })
        
        return engine
    
    def _get_secure_connect_args(self, database_url: str) -> Dict[str, Any]:
        """Get secure connection arguments for PostgreSQL."""
        connect_args = {}
        
        # SSL configuration
        if self._is_ssl_enabled(database_url):
            connect_args.update({
                'sslmode': 'require',
                'sslcert': os.environ.get('DB_SSL_CERT'),
                'sslkey': os.environ.get('DB_SSL_KEY'),
                'sslrootcert': os.environ.get('DB_SSL_ROOT_CERT'),
            })
            
            # Remove None values
            connect_args = {k: v for k, v in connect_args.items() if v is not None}
        
        # Connection security settings
        connect_args.update({
            'application_name': 'fastapi-celery-app',
            'connect_timeout': 10,
            'options': '-c default_transaction_isolation=read_committed'
        })
        
        return connect_args
    
    def _is_ssl_enabled(self, database_url: str) -> bool:
        """Check if SSL is enabled in database URL."""
        parsed = urlparse(database_url)
        query_params = parse_qs(parsed.query)
        
        # Check for SSL parameters
        ssl_params = ['sslmode', 'ssl', 'sslcert', 'sslkey']
        return any(param in query_params for param in ssl_params)
    
    def _register_security_listeners(self, engine: Engine):
        """Register security event listeners for monitoring."""
        
        @event.listens_for(engine, "connect")
        def receive_connect(dbapi_connection, connection_record):
            """Log successful database connections."""
            self.security_logger.info("Database connection established",
                                    extra={
                                        "event": "db_connect",
                                        "connection_id": id(dbapi_connection)
                                    })
        
        @event.listens_for(engine, "checkout")
        def receive_checkout(dbapi_connection, connection_record, connection_proxy):
            """Log connection checkout from pool."""
            self.security_logger.debug("Connection checked out from pool",
                                     extra={
                                         "event": "db_checkout", 
                                         "connection_id": id(dbapi_connection)
                                     })
        
        @event.listens_for(engine, "checkin")
        def receive_checkin(dbapi_connection, connection_record):
            """Log connection checkin to pool."""
            self.security_logger.debug("Connection checked into pool",
                                     extra={
                                         "event": "db_checkin",
                                         "connection_id": id(dbapi_connection)
                                     })
        
        @event.listens_for(engine, "before_cursor_execute")
        def receive_before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            """Log SQL queries for security monitoring."""
            # Only log in debug mode or for security-sensitive operations
            if logger.level <= logging.DEBUG or self._is_security_sensitive_query(statement):
                self.query_logger.info("Executing SQL query",
                                     extra={
                                         "event": "sql_execute",
                                         "query": statement[:500],  # Truncate long queries
                                         "parameters_count": len(parameters) if parameters else 0,
                                         "executemany": executemany
                                     })
    
    def _is_security_sensitive_query(self, statement: str) -> bool:
        """Check if query is security-sensitive and should be logged."""
        sensitive_patterns = [
            'CREATE USER', 'DROP USER', 'ALTER USER',
            'GRANT', 'REVOKE',
            'CREATE ROLE', 'DROP ROLE', 'ALTER ROLE',
            'SET ROLE', 'SET SESSION_USER',
            'DELETE FROM', 'TRUNCATE',
            'ALTER TABLE', 'DROP TABLE'
        ]
        
        upper_statement = statement.upper()
        return any(pattern in upper_statement for pattern in sensitive_patterns)
    
    def validate_database_security(self, engine: Engine) -> Dict[str, Any]:
        """
        Validate database security configuration.
        
        Returns:
            Dictionary with security validation results
        """
        results = {
            "ssl_enabled": False,
            "connection_encrypted": False,
            "user_privileges": {},
            "database_version": None,
            "security_issues": []
        }
        
        try:
            with engine.connect() as conn:
                # Check SSL status
                ssl_result = conn.execute(text("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()")).fetchone()
                if ssl_result:
                    results["ssl_enabled"] = ssl_result[0]
                    results["connection_encrypted"] = ssl_result[0]
                
                # Get database version
                version_result = conn.execute(text("SELECT version()")).fetchone()
                if version_result:
                    results["database_version"] = version_result[0]
                
                # Check current user privileges
                user_result = conn.execute(text("SELECT current_user, session_user")).fetchone()
                if user_result:
                    current_user, session_user = user_result
                    results["user_privileges"]["current_user"] = current_user
                    results["user_privileges"]["session_user"] = session_user
                
                # Check for superuser privileges (should be False in production)
                superuser_result = conn.execute(text("SELECT usesuper FROM pg_user WHERE usename = current_user")).fetchone()
                if superuser_result:
                    is_superuser = superuser_result[0]
                    results["user_privileges"]["is_superuser"] = is_superuser
                    
                    if is_superuser:
                        results["security_issues"].append("Database user has superuser privileges")
                
                # Check for dangerous permissions
                dangerous_perms = conn.execute(text("""
                    SELECT rolname FROM pg_roles 
                    WHERE (rolsuper OR rolcreaterole OR rolcreatedb) 
                    AND rolname = current_user
                """)).fetchall()
                
                if dangerous_perms:
                    results["security_issues"].append("Database user has elevated privileges")
                
        except Exception as e:
            logger.error("Failed to validate database security", 
                        extra={"error": str(e)})
            results["security_issues"].append(f"Security validation failed: {str(e)}")
        
        # Log security validation results
        self.security_logger.info("Database security validation completed",
                                 extra={
                                     "event": "security_validation",
                                     "results": results
                                 })
        
        return results
    
    def setup_connection_encryption(self, database_url: str) -> str:
        """
        Setup connection encryption for database URL.
        
        Args:
            database_url: Original database URL
            
        Returns:
            Updated database URL with SSL parameters
        """
        parsed = urlparse(database_url)
        
        # If SSL already configured, return as-is
        if self._is_ssl_enabled(database_url):
            return database_url
        
        # Add SSL parameters for encrypted connections
        ssl_params = "sslmode=require"
        
        # Add SSL certificate paths if available
        if os.environ.get('DB_SSL_CERT'):
            ssl_params += f"&sslcert={os.environ.get('DB_SSL_CERT')}"
        if os.environ.get('DB_SSL_KEY'):
            ssl_params += f"&sslkey={os.environ.get('DB_SSL_KEY')}"
        if os.environ.get('DB_SSL_ROOT_CERT'):
            ssl_params += f"&sslrootcert={os.environ.get('DB_SSL_ROOT_CERT')}"
        
        # Reconstruct URL with SSL parameters
        if parsed.query:
            new_query = f"{parsed.query}&{ssl_params}"
        else:
            new_query = ssl_params
        
        encrypted_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{new_query}"
        
        logger.info("Added SSL encryption to database URL",
                   extra={"ssl_mode": "require"})
        
        return encrypted_url


# Global security manager instance
db_security = DatabaseSecurityManager()
"""
Test suite for database security hardening.

Tests connection encryption, query logging, and privilege restrictions.
"""

import pytest
import os
from unittest.mock import Mock, patch, MagicMock
from urllib.parse import urlparse
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.db.security import DatabaseSecurityManager, db_security


class TestDatabaseSecurityManager:
    """Test database security management."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.db_security = DatabaseSecurityManager()
    
    def test_database_security_manager_initialization(self):
        """Test database security manager initializes correctly."""
        assert hasattr(self.db_security, 'query_logger')
        assert hasattr(self.db_security, 'security_logger')
        assert self.db_security.query_logger is not None
        assert self.db_security.security_logger is not None
    
    def test_create_secure_engine_basic(self):
        """Test secure engine creation with basic configuration."""
        database_url = "postgresql://user:pass@localhost:5432/testdb"
        
        with patch('app.db.security.create_engine') as mock_create_engine:
            mock_engine = Mock()
            mock_create_engine.return_value = mock_engine
            
            engine = self.db_security.create_secure_engine(database_url)
            
            # Verify create_engine was called with secure configuration
            mock_create_engine.assert_called_once()
            call_args = mock_create_engine.call_args
            
            # Check URL
            assert call_args[0][0] == database_url
            
            # Check secure configuration
            config = call_args[1]
            assert config['pool_pre_ping'] is True
            assert config['pool_size'] == 5
            assert config['max_overflow'] == 10
            assert config['pool_timeout'] == 30
            assert config['pool_recycle'] == 3600
            assert config['echo'] is False
            assert config['echo_pool'] is False
    
    def test_create_secure_engine_invalid_scheme(self):
        """Test engine creation fails with invalid database scheme."""
        invalid_url = "mysql://user:pass@localhost:5432/testdb"
        
        with pytest.raises(ValueError, match="Unsupported database scheme"):
            self.db_security.create_secure_engine(invalid_url)
    
    def test_create_secure_engine_missing_hostname(self):
        """Test engine creation fails with missing hostname."""
        invalid_url = "postgresql://user:pass@:5432/testdb"
        
        with pytest.raises(ValueError, match="Database hostname is required"):
            self.db_security.create_secure_engine(invalid_url)
    
    def test_get_secure_connect_args_basic(self):
        """Test secure connection arguments generation."""
        database_url = "postgresql://user:pass@localhost:5432/testdb"
        
        connect_args = self.db_security._get_secure_connect_args(database_url)
        
        assert 'application_name' in connect_args
        assert 'connect_timeout' in connect_args
        assert 'options' in connect_args
        
        assert connect_args['application_name'] == 'fastapi-celery-app'
        assert connect_args['connect_timeout'] == 10
        assert 'default_transaction_isolation=read_committed' in connect_args['options']
    
    @patch.dict(os.environ, {
        'DB_SSL_CERT': '/path/to/cert.crt',
        'DB_SSL_KEY': '/path/to/key.key',
        'DB_SSL_ROOT_CERT': '/path/to/ca.crt'
    })
    def test_get_secure_connect_args_with_ssl(self):
        """Test secure connection arguments with SSL certificates."""
        database_url = "postgresql://user:pass@localhost:5432/testdb?sslmode=require"
        
        connect_args = self.db_security._get_secure_connect_args(database_url)
        
        assert 'sslmode' in connect_args
        assert 'sslcert' in connect_args
        assert 'sslkey' in connect_args
        assert 'sslrootcert' in connect_args
        
        assert connect_args['sslmode'] == 'require'
        assert connect_args['sslcert'] == '/path/to/cert.crt'
        assert connect_args['sslkey'] == '/path/to/key.key'
        assert connect_args['sslrootcert'] == '/path/to/ca.crt'
    
    def test_is_ssl_enabled_detection(self):
        """Test SSL detection in database URLs."""
        ssl_urls = [
            "postgresql://user:pass@host:5432/db?sslmode=require",
            "postgresql://user:pass@host:5432/db?ssl=true",
            "postgresql://user:pass@host:5432/db?sslcert=/path/to/cert"
        ]
        
        non_ssl_urls = [
            "postgresql://user:pass@host:5432/db",
            "postgresql://user:pass@host:5432/db?timeout=30"
        ]
        
        for url in ssl_urls:
            assert self.db_security._is_ssl_enabled(url) is True
        
        for url in non_ssl_urls:
            assert self.db_security._is_ssl_enabled(url) is False
    
    def test_is_security_sensitive_query(self):
        """Test detection of security-sensitive SQL queries."""
        sensitive_queries = [
            "CREATE USER testuser",
            "DROP USER testuser",
            "ALTER USER testuser",
            "GRANT SELECT ON table TO user",
            "REVOKE SELECT ON table FROM user",
            "CREATE ROLE admin",
            "DROP ROLE admin",
            "SET ROLE admin",
            "DELETE FROM users",
            "TRUNCATE TABLE sessions",
            "ALTER TABLE users ADD COLUMN",
            "DROP TABLE sensitive_data"
        ]
        
        non_sensitive_queries = [
            "SELECT * FROM users",
            "INSERT INTO logs VALUES",
            "UPDATE users SET name",
            "SELECT COUNT(*) FROM table"
        ]
        
        for query in sensitive_queries:
            assert self.db_security._is_security_sensitive_query(query) is True
        
        for query in non_sensitive_queries:
            assert self.db_security._is_security_sensitive_query(query) is False
    
    def test_setup_connection_encryption(self):
        """Test connection encryption setup."""
        plain_url = "postgresql://user:pass@host:5432/db"
        encrypted_url = self.db_security.setup_connection_encryption(plain_url)
        
        # Should add SSL parameters
        assert "sslmode=require" in encrypted_url
        assert encrypted_url != plain_url
        
        # Already encrypted URL should remain unchanged
        ssl_url = "postgresql://user:pass@host:5432/db?sslmode=require"
        unchanged_url = self.db_security.setup_connection_encryption(ssl_url)
        
        assert unchanged_url == ssl_url
    
    @patch.dict(os.environ, {
        'DB_SSL_CERT': '/path/to/cert.crt',
        'DB_SSL_KEY': '/path/to/key.key',
        'DB_SSL_ROOT_CERT': '/path/to/ca.crt'
    })
    def test_setup_connection_encryption_with_certificates(self):
        """Test connection encryption with SSL certificates."""
        plain_url = "postgresql://user:pass@host:5432/db"
        encrypted_url = self.db_security.setup_connection_encryption(plain_url)
        
        assert "sslmode=require" in encrypted_url
        assert "sslcert=/path/to/cert.crt" in encrypted_url
        assert "sslkey=/path/to/key.key" in encrypted_url
        assert "sslrootcert=/path/to/ca.crt" in encrypted_url


class TestDatabaseSecurityValidation:
    """Test database security validation."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.db_security = DatabaseSecurityManager()
    
    def test_validate_database_security_success(self):
        """Test successful database security validation."""
        mock_engine = Mock()
        mock_connection = Mock()
        mock_engine.connect.return_value.__enter__.return_value = mock_connection
        
        # Mock SQL query results
        mock_connection.execute.side_effect = [
            Mock(fetchone=lambda: (True,)),  # SSL enabled
            Mock(fetchone=lambda: ("PostgreSQL 13.0",)),  # Version
            Mock(fetchone=lambda: ("app_user", "app_user")),  # Current user
            Mock(fetchone=lambda: (False,)),  # Not superuser
            Mock(fetchall=lambda: [])  # No dangerous permissions
        ]
        
        results = self.db_security.validate_database_security(mock_engine)
        
        assert results['ssl_enabled'] is True
        assert results['connection_encrypted'] is True
        assert results['database_version'] == "PostgreSQL 13.0"
        assert results['user_privileges']['current_user'] == "app_user"
        assert results['user_privileges']['is_superuser'] is False
        assert len(results['security_issues']) == 0
    
    def test_validate_database_security_superuser_warning(self):
        """Test database validation detects superuser privileges."""
        mock_engine = Mock()
        mock_connection = Mock()
        mock_engine.connect.return_value.__enter__.return_value = mock_connection
        
        # Mock SQL query results with superuser
        mock_connection.execute.side_effect = [
            Mock(fetchone=lambda: (False,)),  # SSL disabled
            Mock(fetchone=lambda: ("PostgreSQL 13.0",)),  # Version
            Mock(fetchone=lambda: ("postgres", "postgres")),  # Current user
            Mock(fetchone=lambda: (True,)),  # Is superuser
            Mock(fetchall=lambda: [("postgres",)])  # Has dangerous permissions
        ]
        
        results = self.db_security.validate_database_security(mock_engine)
        
        assert results['ssl_enabled'] is False
        assert results['user_privileges']['is_superuser'] is True
        assert "Database user has superuser privileges" in results['security_issues']
        assert "Database user has elevated privileges" in results['security_issues']
    
    def test_validate_database_security_connection_error(self):
        """Test database validation handles connection errors."""
        mock_engine = Mock()
        mock_engine.connect.side_effect = Exception("Connection failed")
        
        results = self.db_security.validate_database_security(mock_engine)
        
        assert len(results['security_issues']) > 0
        assert any("Security validation failed" in issue for issue in results['security_issues'])


class TestDatabaseEventListeners:
    """Test database event listeners for security monitoring."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.db_security = DatabaseSecurityManager()
    
    def test_register_security_listeners(self):
        """Test that security event listeners are registered."""
        mock_engine = Mock()
        
        with patch('app.db.security.event') as mock_event:
            self.db_security._register_security_listeners(mock_engine)
            
            # Verify that event listeners were registered
            assert mock_event.listens_for.call_count >= 4
            
            # Check for expected events
            calls = [call[0] for call in mock_event.listens_for.call_args_list]
            events = [call[1] for call in calls]
            
            assert "connect" in events
            assert "checkout" in events
            assert "checkin" in events
            assert "before_cursor_execute" in events
    
    def test_connection_event_logging(self):
        """Test connection event logging."""
        mock_engine = Mock()
        
        with patch.object(self.db_security.security_logger, 'info') as mock_log:
            self.db_security._register_security_listeners(mock_engine)
            
            # Simulate connection event
            connect_handler = None
            for call in mock_event.listens_for.call_args_list:
                if call[0][1] == "connect":
                    connect_handler = call[1]["func"]
                    break
            
            if connect_handler:
                mock_connection = Mock()
                mock_record = Mock()
                connect_handler(mock_connection, mock_record)
                
                mock_log.assert_called()
                call_args = mock_log.call_args
                assert "Database connection established" in call_args[0][0]


class TestGlobalSecurityInstance:
    """Test global database security instance."""
    
    def test_global_db_security_instance(self):
        """Test that global db_security instance is available."""
        from app.db.security import db_security
        
        assert db_security is not None
        assert isinstance(db_security, DatabaseSecurityManager)
        assert hasattr(db_security, 'create_secure_engine')
        assert hasattr(db_security, 'validate_database_security')


class TestSSLConfiguration:
    """Test SSL/TLS configuration for database connections."""
    
    def test_ssl_parameter_injection(self):
        """Test SSL parameter injection into database URLs."""
        db_security = DatabaseSecurityManager()
        
        test_cases = [
            {
                'input': "postgresql://user:pass@host:5432/db",
                'expected_params': ['sslmode=require']
            },
            {
                'input': "postgresql://user:pass@host:5432/db?timeout=30",
                'expected_params': ['sslmode=require']
            }
        ]
        
        for case in test_cases:
            result = db_security.setup_connection_encryption(case['input'])
            for param in case['expected_params']:
                assert param in result
    
    @patch.dict(os.environ, {
        'DB_SSL_CERT': '/etc/ssl/client-cert.pem',
        'DB_SSL_KEY': '/etc/ssl/client-key.pem',
        'DB_SSL_ROOT_CERT': '/etc/ssl/ca-cert.pem'
    })
    def test_ssl_certificate_configuration(self):
        """Test SSL certificate configuration."""
        db_security = DatabaseSecurityManager()
        
        url = "postgresql://user:pass@host:5432/db"
        result = db_security.setup_connection_encryption(url)
        
        assert "sslcert=/etc/ssl/client-cert.pem" in result
        assert "sslkey=/etc/ssl/client-key.pem" in result
        assert "sslrootcert=/etc/ssl/ca-cert.pem" in result


@pytest.mark.integration
class TestDatabaseSecurityIntegration:
    """Integration tests for database security hardening."""
    
    def test_secure_engine_creation_integration(self):
        """Test secure engine creation with real configuration."""
        # Use test database URL
        test_url = "postgresql://test_user:test_pass@localhost:5432/test_db"
        
        with patch('app.db.security.create_engine') as mock_create:
            mock_engine = Mock()
            mock_create.return_value = mock_engine
            
            db_security = DatabaseSecurityManager()
            engine = db_security.create_secure_engine(test_url)
            
            # Verify secure configuration was applied
            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args[1]
            
            assert call_kwargs['pool_pre_ping'] is True
            assert call_kwargs['pool_size'] == 5
            assert call_kwargs['pool_recycle'] == 3600
            assert 'connect_args' in call_kwargs
    
    def test_database_session_security_integration(self):
        """Test database session security integration."""
        from app.db.session import engine
        from app.config import get_config
        
        config = get_config()
        
        with patch('app.db.security.db_security.create_secure_engine') as mock_create:
            mock_engine = Mock()
            mock_create.return_value = mock_engine
            
            # Should use secure engine creation
            result_engine = engine(config)
            
            mock_create.assert_called_once_with(
                config.db_uri,
                pool_pre_ping=True,
                pool_size=config.db_pool_size
            )


class TestConnectionPoolSecurity:
    """Test connection pool security configuration."""
    
    def test_connection_pool_limits(self):
        """Test connection pool limits are properly configured."""
        db_security = DatabaseSecurityManager()
        
        with patch('app.db.security.create_engine') as mock_create:
            mock_create.return_value = Mock()
            
            db_security.create_secure_engine("postgresql://user:pass@host:5432/db")
            
            call_kwargs = mock_create.call_args[1]
            
            assert call_kwargs['pool_size'] == 5
            assert call_kwargs['max_overflow'] == 10
            assert call_kwargs['pool_timeout'] == 30
            assert call_kwargs['pool_recycle'] == 3600
    
    def test_connection_validation(self):
        """Test connection validation configuration."""
        db_security = DatabaseSecurityManager()
        
        with patch('app.db.security.create_engine') as mock_create:
            mock_create.return_value = Mock()
            
            db_security.create_secure_engine("postgresql://user:pass@host:5432/db")
            
            call_kwargs = mock_create.call_args[1]
            
            assert call_kwargs['pool_pre_ping'] is True


class TestQueryLoggingSecurity:
    """Test query logging for security monitoring."""
    
    def test_sensitive_query_detection(self):
        """Test detection of security-sensitive queries."""
        db_security = DatabaseSecurityManager()
        
        sensitive_queries = [
            "CREATE USER malicious_user",
            "GRANT ALL PRIVILEGES ON *.* TO user",
            "DROP TABLE important_data",
            "TRUNCATE users",
            "SET ROLE admin"
        ]
        
        for query in sensitive_queries:
            assert db_security._is_security_sensitive_query(query) is True
    
    def test_normal_query_not_flagged(self):
        """Test that normal queries are not flagged as sensitive."""
        db_security = DatabaseSecurityManager()
        
        normal_queries = [
            "SELECT id, name FROM users WHERE active = true",
            "INSERT INTO logs (message, timestamp) VALUES (?, ?)",
            "UPDATE user_profiles SET last_login = NOW() WHERE user_id = ?",
            "SELECT COUNT(*) FROM orders WHERE date > '2025-01-01'"
        ]
        
        for query in normal_queries:
            assert db_security._is_security_sensitive_query(query) is False
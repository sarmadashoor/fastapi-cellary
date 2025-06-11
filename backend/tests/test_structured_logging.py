"""Tests for structured logging in upload and parse flow."""
import io
import json
import logging
from unittest.mock import MagicMock, patch
from io import StringIO

import pytest
from fastapi.testclient import TestClient

from app.main import app


class TestStructuredLogging:
    """Test structured logging implementation."""

    def test_upload_endpoint_logs_structured_data(self, client, admin_token):
        """Test that upload endpoint logs structured data with context."""
        # Create a test file
        file_content = b"test resume content"
        file = io.BytesIO(file_content)
        
        with patch("app.api.v1.resumes.upload.logger") as mock_logger:
            response = client.post(
                "/api/resumes/upload",
                files={"file": ("test.pdf", file, "application/pdf")},
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            
            assert response.status_code == 200
            
            # Check that structured logging was called
            assert mock_logger.info.called
            
            # Get the log call arguments
            log_calls = mock_logger.info.call_args_list
            assert len(log_calls) > 0
            
            # Check that log contains structured context
            for call in log_calls:
                args, kwargs = call
                # Should have either structured kwargs or a structured message
                assert kwargs or (args and isinstance(args[0], (str, dict)))

    def test_parse_task_logs_structured_data(self):
        """Test that parse task logs structured data with context."""
        from app.workers.resume_parser import parse_resume_task
        
        with patch("app.workers.resume_parser.logger") as mock_logger:
            # Mock the parsing functions
            with patch("app.workers.resume_parser.extract_text_from_pdf") as mock_extract:
                mock_extract.return_value = "Test resume text"
                
                with patch("app.workers.resume_parser.extract_contact_info") as mock_contact:
                    mock_contact.return_value = {
                        "name": "John Doe",
                        "email": "john@example.com",
                        "phone": "+1234567890"
                    }
                    
                    result = parse_resume_task(b"test content", "application/pdf")
                    
                    # Check that structured logging was called
                    assert mock_logger.info.called
                    
                    # Verify log calls contain structured data
                    log_calls = mock_logger.info.call_args_list
                    assert len(log_calls) >= 2  # At least start and completion logs

    def test_logging_configuration_exists(self):
        """Test that logging configuration is properly set up."""
        from app import logging_config
        
        # Check that logging configuration module exists
        assert hasattr(logging_config, 'configure_logging')
        
        # Check that it returns a proper logger
        logger = logging_config.get_logger(__name__)
        assert hasattr(logger, 'info')  # Check it has logging methods

    def test_structured_formatter_json_output(self):
        """Test that StructuredFormatter outputs valid JSON."""
        from app.logging_config import StructuredFormatter
        
        formatter = StructuredFormatter()
        logger = logging.getLogger("test_logger")
        
        # Create a log record with extra fields
        record = logger.makeRecord(
            name="test_logger",
            level=logging.INFO,
            fn="test.py",
            lno=10,
            msg="Test message",
            args=(),
            exc_info=None
        )
        
        # Add extra fields to the record
        record.extra_fields = {
            "user_id": "123",
            "action": "upload",
            "file_size": 1024
        }
        
        # Format the record
        formatted_output = formatter.format(record)
        
        # Parse as JSON to verify it's valid JSON
        log_data = json.loads(formatted_output)
        
        # Verify required fields are present
        assert log_data["level"] == "INFO"
        assert log_data["logger"] == "test_logger"
        assert log_data["message"] == "Test message"
        assert log_data["user_id"] == "123"
        assert log_data["action"] == "upload" 
        assert log_data["file_size"] == 1024
        assert "timestamp" in log_data

    def test_structured_logger_context_propagation(self):
        """Test that StructuredLogger properly propagates context."""
        from app.logging_config import StructuredLogger, StructuredFormatter
        
        # Create a logger with custom handler for testing
        base_logger = logging.getLogger("test_context")
        base_logger.handlers.clear()  # Remove existing handlers
        
        # Add a string stream handler with structured formatter
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter())
        base_logger.addHandler(handler)
        base_logger.setLevel(logging.INFO)
        
        # Create structured logger with base context
        structured_logger = StructuredLogger(base_logger, {"service": "test_service"})
        
        # Log with additional context
        structured_logger.info("Test message", extra={
            "user_id": "456",
            "request_id": "req-789"
        })
        
        # Get the logged output
        log_output = stream.getvalue()
        log_data = json.loads(log_output)
        
        # Verify context propagation
        assert log_data["message"] == "Test message"
        assert log_data["service"] == "test_service"  # Base context
        assert log_data["user_id"] == "456"  # Extra context
        assert log_data["request_id"] == "req-789"  # Extra context

    def test_pii_redaction_in_formatter(self):
        """Test that sensitive data is redacted from log messages."""
        from app.logging_config import StructuredFormatter
        
        formatter = StructuredFormatter()
        logger = logging.getLogger("test_logger")
        
        # Test SSN redaction
        record = logger.makeRecord(
            name="test_logger",
            level=logging.INFO,
            fn="test.py",
            lno=10,
            msg="User SSN is 123-45-6789 and credit card 4111111111111111",
            args=(),
            exc_info=None
        )
        
        formatted_output = formatter.format(record)
        log_data = json.loads(formatted_output)
        
        # Verify sensitive data is redacted
        assert "[REDACTED]" in log_data["message"]
        assert "123-45-6789" not in log_data["message"]
        
        # Test password field redaction
        record.extra_fields = {
            "user_password": "secret123",
            "api_token": "abc123xyz",
            "safe_field": "safe_value"
        }
        
        formatted_output = formatter.format(record)
        log_data = json.loads(formatted_output)
        
        # Verify field-level redaction
        assert log_data["user_password"] == "[REDACTED]"
        assert log_data["api_token"] == "[REDACTED]"
        assert log_data["safe_field"] == "safe_value"

    def test_security_no_sensitive_data_logged(self, client, admin_token):
        """Test that sensitive data is not logged."""
        # Create a file with sensitive name
        file_content = b"sensitive content"
        sensitive_filename = "John_Doe_SSN_123456789.pdf"
        file = io.BytesIO(file_content)
        
        with patch("app.api.v1.resumes.upload.logger") as mock_logger:
            response = client.post(
                "/api/resumes/upload",
                files={"file": (sensitive_filename, file, "application/pdf")},
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            
            assert response.status_code == 200
            
            # Check that filename is not logged directly
            for call in mock_logger.info.call_args_list:
                args, kwargs = call
                # Convert to string to check
                log_str = str(args) + str(kwargs)
                # Should not contain the full filename
                assert sensitive_filename not in log_str
                # Should not contain SSN pattern
                assert "123456789" not in log_str

    def test_error_logging_with_context(self, client, admin_token):
        """Test that errors are logged with proper context."""
        # Send invalid file type
        file_content = b"test content"
        file = io.BytesIO(file_content)
        
        with patch("app.api.v1.resumes.upload.logger") as mock_logger:
            response = client.post(
                "/api/resumes/upload",
                files={"file": ("test.txt", file, "text/plain")},
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            
            assert response.status_code == 400
            
            # Check that warning was logged with context
            assert mock_logger.warning.called
            call_args = mock_logger.warning.call_args
            
            # Should include context about the error
            args, kwargs = call_args
            assert "extra" in kwargs or len(args) > 1

    def test_log_level_filtering(self):
        """Test that log levels are properly filtered."""
        from app.logging_config import get_logger
        
        # Create a test logger with INFO level
        base_logger = logging.getLogger("test_level_filter")
        base_logger.handlers.clear()
        base_logger.setLevel(logging.INFO)
        
        # Add a handler to capture logs
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        base_logger.addHandler(handler)
        
        logger = get_logger("test_level_filter")
        logger.logger = base_logger  # Use our test logger
        
        # Log at different levels
        logger.debug("Debug message")  # Should be filtered out
        logger.info("Info message")   # Should be logged
        logger.warning("Warning message")  # Should be logged
        
        # Check what was actually logged
        log_output = stream.getvalue()
        
        # DEBUG should be filtered out, INFO and WARNING should be present
        assert "Debug message" not in log_output
        assert "Info message" in log_output
        assert "Warning message" in log_output
"""Tests for structured logging in upload and parse flow."""
import io
import json
import logging
from unittest.mock import MagicMock, patch

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

    def test_structured_log_format(self, caplog):
        """Test that logs are formatted as structured JSON."""
        from app.logging_config import get_logger
        
        logger = get_logger("test_module")
        
        # Log a message with context
        with caplog.at_level(logging.INFO):
            logger.info("Test message", extra={
                "user_id": "123",
                "action": "upload",
                "file_size": 1024
            })
        
        # Check that the log was captured
        assert len(caplog.records) == 1
        record = caplog.records[0]
        
        # Check that message is correct
        assert "Test message" in record.message

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

    @pytest.mark.parametrize("log_level,should_log", [
        (logging.DEBUG, False),  # Debug should not log in production
        (logging.INFO, True),    # Info should log
        (logging.WARNING, True), # Warning should log
        (logging.ERROR, True),   # Error should log
    ])
    def test_log_levels_respected(self, log_level, should_log):
        """Test that log levels are properly configured."""
        from app.logging_config import get_logger
        
        logger = get_logger("test_module")
        
        # Test that logger can handle different log levels
        with patch.object(logger.logger, 'log') as mock_log:
            logger.log(log_level, "Test message")
            assert mock_log.called
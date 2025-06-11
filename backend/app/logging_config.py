"""Structured logging configuration for the application."""
import logging
import sys
from typing import Any, Dict, Optional
import json
from datetime import datetime, timezone
import re


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    
    SENSITIVE_PATTERNS = [
        r'\b\d{3}-\d{2}-\d{4}\b',  # SSN pattern
        r'\b\d{9}\b',  # SSN without dashes
        r'password["\']?\s*[:=]\s*["\']?[^"\'}\s]+',  # Password patterns
        r'token["\']?\s*[:=]\s*["\']?[^"\'}\s]+',  # Token patterns
    ]
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON with security filtering."""
        log_data: Dict[str, Any] = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': self._sanitize_message(record.getMessage()),
        }
        
        # Add any extra fields from the record
        if hasattr(record, 'extra_fields'):
            for key, value in record.extra_fields.items():
                log_data[key] = self._sanitize_value(key, value)
        
        # Add standard fields if present
        if hasattr(record, 'pathname'):
            log_data['pathname'] = record.pathname
        if hasattr(record, 'lineno'):
            log_data['lineno'] = record.lineno
        if hasattr(record, 'funcName'):
            log_data['function'] = record.funcName
            
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
            
        return json.dumps(log_data)
    
    def _sanitize_message(self, message: str) -> str:
        """Remove sensitive data from log messages."""
        for pattern in self.SENSITIVE_PATTERNS:
            message = re.sub(pattern, '[REDACTED]', message, flags=re.IGNORECASE)
        return message
    
    def _sanitize_value(self, key: str, value: Any) -> Any:
        """Sanitize individual log values based on key names."""
        # Don't log sensitive field values
        sensitive_keys = ['password', 'token', 'secret', 'ssn', 'credit_card']
        if any(sensitive in key.lower() for sensitive in sensitive_keys):
            return '[REDACTED]'
            
        # Sanitize string values
        if isinstance(value, str):
            return self._sanitize_message(value)
            
        return value


class StructuredLogger(logging.LoggerAdapter):
    """Logger adapter that adds structured context to logs."""
    
    def __init__(self, logger: logging.Logger, extra: Optional[Dict[str, Any]] = None):
        super().__init__(logger, extra or {})
        
    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        """Process log message to add structured context."""
        # Get extra fields from kwargs
        extra_fields = kwargs.pop('extra', {})
        
        # Merge with adapter's extra fields
        if self.extra:
            extra_fields.update(self.extra)
            
        # Create new log record with extra_fields attribute
        if extra_fields:
            kwargs['extra'] = {'extra_fields': extra_fields}
            
        return msg, kwargs


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structured logging for the application.
    
    Args:
        log_level: The logging level to use (default: INFO)
    """
    # Remove existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler with structured formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(StructuredFormatter())
    
    # Configure root logger
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    root_logger.addHandler(console_handler)
    
    # Suppress noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("watchfiles").setLevel(logging.WARNING)


def get_logger(name: str) -> StructuredLogger:
    """Get a structured logger instance.
    
    Args:
        name: The name of the logger (usually __name__)
        
    Returns:
        StructuredLogger instance with structured logging capabilities
    """
    base_logger = logging.getLogger(name)
    return StructuredLogger(base_logger)
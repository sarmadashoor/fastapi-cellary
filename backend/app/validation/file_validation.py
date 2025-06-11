"""
Comprehensive file validation and security scanning module.

This module provides security-hardened file validation including:
- ClamAV virus scanning integration
- Magic bytes content validation
- Strict file type and size enforcement
- Security logging with reason codes
"""

import logging
import subprocess
from typing import Optional, Dict, Any
from pathlib import Path

try:
    import pyclamd
    CLAMD_AVAILABLE = True
except ImportError:
    CLAMD_AVAILABLE = False

from app.logging_config import get_logger

logger = get_logger(__name__)


class SecurityValidationError(Exception):
    """Exception raised when file fails security validation."""
    
    def __init__(self, message: str, reason_code: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.reason_code = reason_code
        self.details = details or {}


# File type magic bytes signatures
MAGIC_BYTES_SIGNATURES = {
    "application/pdf": [
        b"%PDF-1.",  # PDF version 1.x
        b"%PDF-2.",  # PDF version 2.x
    ],
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [
        b"PK\x03\x04",  # ZIP signature (DOCX is a ZIP archive)
    ]
}

# Suspicious content patterns that should be rejected
SUSPICIOUS_PATTERNS = [
    b"<script",
    b"javascript:",
    b"/JavaScript",
    b"eval(",
    b"document.write",
    b"window.open",
    b"ActiveXObject",
    b"Shell.Application",
    b"WScript.Shell",
    b"cmd.exe",
    b"powershell",
]

# Executable file signatures to detect disguised executables
EXECUTABLE_SIGNATURES = [
    b"MZ",      # Windows PE executable
    b"\x7fELF", # Linux ELF executable
    b"\xca\xfe\xba\xbe",  # Mach-O executable (macOS)
    b"\xfe\xed\xfa",      # Mach-O executable variants
]


def scan_file_for_viruses(file_content: bytes, filename: str) -> bool:
    """
    Scan file content for viruses using ClamAV.
    
    Args:
        file_content: The file content to scan as bytes
        filename: Original filename for logging purposes
        
    Returns:
        True if file is clean or scanning unavailable
        
    Raises:
        SecurityValidationError: If virus is detected
    """
    if not CLAMD_AVAILABLE:
        logger.warning(
            "ClamAV not available, skipping virus scan",
            extra={
                "filename": filename,
                "reason_code": "CLAMD_UNAVAILABLE",
                "event": "virus_scan_skipped"
            }
        )
        return True
    
    try:
        # Try to connect to ClamAV daemon
        cd = pyclamd.ClamdUnixSocket()
        
        # Test connection
        if not cd.ping():
            logger.warning(
                "ClamAV daemon not responding",
                extra={
                    "filename": filename,
                    "reason_code": "CLAMD_NOT_RESPONDING",
                    "event": "virus_scan_fallback"
                }
            )
            return True
        
        # Scan the file content
        scan_result = cd.scan_stream(file_content)
        
        if scan_result is None:
            # File is clean
            logger.debug(
                "File passed virus scan",
                extra={
                    "filename": filename,
                    "file_size": len(file_content),
                    "event": "virus_scan_clean"
                }
            )
            return True
        else:
            # Virus detected
            virus_name = scan_result[1] if len(scan_result) > 1 else "Unknown"
            
            logger.error(
                "Virus detected in uploaded file",
                extra={
                    "filename": filename,
                    "virus_name": virus_name,
                    "reason_code": "SECURITY_VIRUS_DETECTED",
                    "event": "virus_scan_infected",
                    "file_size": len(file_content)
                }
            )
            
            raise SecurityValidationError(
                f"Virus detected: {virus_name}",
                reason_code="SECURITY_VIRUS_DETECTED",
                details={"virus_name": virus_name, "filename": filename}
            )
            
    except (ConnectionError, TimeoutError, OSError) as e:
        # ClamAV daemon unavailable or timeout
        logger.warning(
            "Virus scanning unavailable, allowing file through",
            extra={
                "filename": filename,
                "error": str(e),
                "reason_code": "CLAMD_CONNECTION_ERROR",
                "event": "virus_scan_fallback"
            }
        )
        return True
        
    except Exception as e:
        # Unexpected error during scanning
        logger.error(
            "Unexpected error during virus scanning",
            extra={
                "filename": filename,
                "error": str(e),
                "reason_code": "CLAMD_SCAN_ERROR",
                "event": "virus_scan_error"
            }
        )
        # Fail-open for availability, but log the error
        return True


def validate_file_content_by_magic_bytes(file_content: bytes, expected_content_type: str) -> bool:
    """
    Validate file content using magic bytes signature verification.
    
    Args:
        file_content: The file content to validate
        expected_content_type: The expected MIME type
        
    Returns:
        True if validation passes
        
    Raises:
        SecurityValidationError: If validation fails
    """
    if len(file_content) == 0:
        logger.warning(
            "Empty file content detected",
            extra={
                "reason_code": "SECURITY_EMPTY_FILE",
                "event": "magic_bytes_validation_failed"
            }
        )
        raise SecurityValidationError(
            "Empty file not allowed",
            reason_code="SECURITY_EMPTY_FILE"
        )
    
    # Check for executable file signatures first
    for exe_sig in EXECUTABLE_SIGNATURES:
        if file_content.startswith(exe_sig):
            logger.error(
                "Executable file detected disguised as document",
                extra={
                    "content_type": expected_content_type,
                    "detected_signature": exe_sig.hex(),
                    "reason_code": "SECURITY_EXECUTABLE_DETECTED",
                    "event": "magic_bytes_validation_failed"
                }
            )
            raise SecurityValidationError(
                "Executable files are not allowed",
                reason_code="SECURITY_EXECUTABLE_DETECTED"
            )
    
    # Check for suspicious content patterns
    content_lower = file_content.lower()
    for pattern in SUSPICIOUS_PATTERNS:
        if pattern in content_lower:
            logger.warning(
                "Suspicious content pattern detected",
                extra={
                    "content_type": expected_content_type,
                    "pattern": pattern.decode('utf-8', errors='ignore'),
                    "reason_code": "SECURITY_SUSPICIOUS_CONTENT",
                    "event": "magic_bytes_validation_failed"
                }
            )
            raise SecurityValidationError(
                "Suspicious content detected in file",
                reason_code="SECURITY_SUSPICIOUS_CONTENT"
            )
    
    # Validate magic bytes for expected content type
    if expected_content_type not in MAGIC_BYTES_SIGNATURES:
        logger.error(
            "Unsupported content type for magic bytes validation",
            extra={
                "content_type": expected_content_type,
                "reason_code": "SECURITY_UNSUPPORTED_TYPE",
                "event": "magic_bytes_validation_failed"
            }
        )
        raise SecurityValidationError(
            f"Content type {expected_content_type} not supported for validation",
            reason_code="SECURITY_UNSUPPORTED_TYPE"
        )
    
    # Check if file starts with any valid magic bytes for the content type
    valid_signatures = MAGIC_BYTES_SIGNATURES[expected_content_type]
    for signature in valid_signatures:
        if file_content.startswith(signature):
            logger.debug(
                "Magic bytes validation passed",
                extra={
                    "content_type": expected_content_type,
                    "signature": signature.hex(),
                    "event": "magic_bytes_validation_success"
                }
            )
            return True
    
    # No valid signature found
    logger.warning(
        "Magic bytes validation failed",
        extra={
            "content_type": expected_content_type,
            "file_start": file_content[:16].hex(),
            "expected_signatures": [sig.hex() for sig in valid_signatures],
            "reason_code": "SECURITY_MAGIC_BYTES_VIOLATION",
            "event": "magic_bytes_validation_failed"
        }
    )
    
    raise SecurityValidationError(
        f"Magic bytes validation failed for {expected_content_type}",
        reason_code="SECURITY_MAGIC_BYTES_VIOLATION",
        details={
            "expected_type": expected_content_type,
            "file_start": file_content[:16].hex()
        }
    )


def validate_file_size_strict(file_content: bytes, max_size_bytes: int = 5 * 1024 * 1024) -> bool:
    """
    Strictly validate file size before any disk operations.
    
    Args:
        file_content: The file content to validate
        max_size_bytes: Maximum allowed file size in bytes (default: 5MB)
        
    Returns:
        True if validation passes
        
    Raises:
        SecurityValidationError: If file exceeds size limit
    """
    file_size = len(file_content)
    
    if file_size == 0:
        logger.warning(
            "Empty file size detected",
            extra={
                "file_size": file_size,
                "reason_code": "SECURITY_EMPTY_FILE",
                "event": "file_size_validation_failed"
            }
        )
        raise SecurityValidationError(
            "Empty file not allowed",
            reason_code="SECURITY_EMPTY_FILE"
        )
    
    if file_size > max_size_bytes:
        max_size_mb = max_size_bytes / (1024 * 1024)
        actual_size_mb = file_size / (1024 * 1024)
        
        logger.warning(
            "File size limit exceeded",
            extra={
                "file_size_bytes": file_size,
                "file_size_mb": round(actual_size_mb, 2),
                "max_size_bytes": max_size_bytes,
                "max_size_mb": max_size_mb,
                "reason_code": "SECURITY_FILE_SIZE_VIOLATION",
                "event": "file_size_validation_failed"
            }
        )
        
        raise SecurityValidationError(
            f"File size exceeds maximum limit of {max_size_mb}MB",
            reason_code="SECURITY_FILE_SIZE_VIOLATION",
            details={
                "file_size_mb": actual_size_mb,
                "max_size_mb": max_size_mb
            }
        )
    
    logger.debug(
        "File size validation passed",
        extra={
            "file_size_bytes": file_size,
            "file_size_mb": round(file_size / (1024 * 1024), 2),
            "event": "file_size_validation_success"
        }
    )
    
    return True


def validate_file_type_enhanced(file, allowed_content_types: Optional[set] = None) -> bool:
    """
    Enhanced file type validation with extension spoofing detection.
    
    Args:
        file: FastAPI UploadFile object
        allowed_content_types: Set of allowed MIME types
        
    Returns:
        True if validation passes
        
    Raises:
        SecurityValidationError: If file type validation fails
    """
    if allowed_content_types is None:
        allowed_content_types = {
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        }
    
    # Check if content type is provided
    if not file.content_type:
        logger.warning(
            "Missing content type in uploaded file",
            extra={
                "filename": file.filename,
                "reason_code": "SECURITY_MISSING_CONTENT_TYPE",
                "event": "file_type_validation_failed"
            }
        )
        raise SecurityValidationError(
            "Missing content type in uploaded file",
            reason_code="SECURITY_MISSING_CONTENT_TYPE"
        )
    
    # Check if content type is allowed
    if file.content_type not in allowed_content_types:
        logger.warning(
            "Unsupported file type attempted upload",
            extra={
                "filename": file.filename,
                "content_type": file.content_type,
                "allowed_types": list(allowed_content_types),
                "reason_code": "SECURITY_FILE_TYPE_VIOLATION",
                "event": "file_type_validation_failed"
            }
        )
        raise SecurityValidationError(
            f"Unsupported file type: {file.content_type}",
            reason_code="SECURITY_FILE_TYPE_VIOLATION",
            details={
                "content_type": file.content_type,
                "allowed_types": list(allowed_content_types)
            }
        )
    
    # Enhanced filename validation
    if file.filename:
        filename_lower = file.filename.lower()
        
        # Check for double extensions (e.g., file.pdf.exe)
        if filename_lower.count('.') > 1:
            extensions = filename_lower.split('.')
            # Check if any non-final extension is suspicious
            for ext in extensions[1:-1]:  # Skip the base name and final extension
                if ext in ['exe', 'bat', 'cmd', 'com', 'scr', 'vbs', 'js', 'jar', 'app']:
                    logger.warning(
                        "Suspicious file extension detected",
                        extra={
                            "filename": file.filename,
                            "suspicious_extension": ext,
                            "reason_code": "SECURITY_SUSPICIOUS_EXTENSION",
                            "event": "file_type_validation_failed"
                        }
                    )
                    raise SecurityValidationError(
                        "Suspicious file extension detected",
                        reason_code="SECURITY_SUSPICIOUS_EXTENSION",
                        details={"filename": file.filename}
                    )
        
        # Validate final extension matches content type
        final_extension = filename_lower.split('.')[-1] if '.' in filename_lower else ''
        
        expected_extensions = {
            "application/pdf": "pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx"
        }
        
        expected_ext = expected_extensions.get(file.content_type)
        if expected_ext and final_extension != expected_ext:
            logger.warning(
                "File extension does not match content type",
                extra={
                    "filename": file.filename,
                    "content_type": file.content_type,
                    "actual_extension": final_extension,
                    "expected_extension": expected_ext,
                    "reason_code": "SECURITY_EXTENSION_MISMATCH",
                    "event": "file_type_validation_failed"
                }
            )
            raise SecurityValidationError(
                f"File extension '{final_extension}' does not match content type '{file.content_type}'",
                reason_code="SECURITY_EXTENSION_MISMATCH",
                details={
                    "actual_extension": final_extension,
                    "expected_extension": expected_ext
                }
            )
    
    logger.debug(
        "File type validation passed",
        extra={
            "filename": file.filename,
            "content_type": file.content_type,
            "event": "file_type_validation_success"
        }
    )
    
    return True


def comprehensive_file_validation(file, file_content: bytes) -> bool:
    """
    Run comprehensive file validation pipeline.
    
    Args:
        file: FastAPI UploadFile object
        file_content: File content as bytes
        
    Returns:
        True if all validations pass
        
    Raises:
        SecurityValidationError: If any validation fails
    """
    logger.info(
        "Starting comprehensive file validation",
        extra={
            "filename": file.filename,
            "content_type": file.content_type,
            "file_size": len(file_content),
            "event": "file_validation_started"
        }
    )
    
    try:
        # 1. File type validation (fastest, fail early)
        validate_file_type_enhanced(file)
        
        # 2. File size validation (before expensive operations)
        validate_file_size_strict(file_content)
        
        # 3. Magic bytes validation
        validate_file_content_by_magic_bytes(file_content, file.content_type)
        
        # 4. Virus scanning (most expensive, run last)
        scan_file_for_viruses(file_content, file.filename or "unknown")
        
        logger.info(
            "File validation completed successfully",
            extra={
                "filename": file.filename,
                "content_type": file.content_type,
                "file_size": len(file_content),
                "event": "file_validation_success"
            }
        )
        
        return True
        
    except SecurityValidationError as e:
        logger.error(
            "File validation failed",
            extra={
                "filename": file.filename,
                "content_type": file.content_type,
                "file_size": len(file_content),
                "reason_code": e.reason_code,
                "error_message": str(e),
                "event": "file_validation_failed"
            }
        )
        raise
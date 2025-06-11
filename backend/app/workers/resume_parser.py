"""
Celery workers for resume parsing tasks.

This module contains background tasks for processing uploaded resume files,
extracting text content, and generating metadata for further processing.
"""

import io
import re
import time
from typing import Dict, Any, Optional

from celery import current_task

from app.celery_app import celery_app
from app.logging_config import get_logger

# Configure structured logger
logger = get_logger(__name__)

# Import PDF and DOCX libraries with graceful fallback for testing
try:
    import PyPDF2
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False
    PyPDF2 = None

try:
    from docx import Document
    PYTHON_DOCX_AVAILABLE = True
except ImportError:
    PYTHON_DOCX_AVAILABLE = False
    Document = None


def extract_text_from_pdf(file_content: bytes) -> str:
    """
    Extract text content from PDF file bytes.
    
    Args:
        file_content: PDF file content as bytes
        
    Returns:
        Extracted text content as string
        
    Raises:
        Exception: If PDF parsing fails or PyPDF2 not available
    """
    if not PYPDF2_AVAILABLE:
        raise Exception("PyPDF2 library not available")
    
    try:
        pdf_file = io.BytesIO(file_content)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        
        text_content = []
        for page in pdf_reader.pages:
            text_content.append(page.extract_text())
        
        return "\n".join(text_content)
    except Exception as e:
        logger.error(
            "Failed to extract text from PDF",
            extra={
                "error_type": type(e).__name__,
                "error_message": str(e),
                "event": "pdf_extraction_failed",
                "file_size_bytes": len(file_content)
            }
        )
        raise


def extract_text_from_docx(file_content: bytes) -> str:
    """
    Extract text content from DOCX file bytes.
    
    Args:
        file_content: DOCX file content as bytes
        
    Returns:
        Extracted text content as string
        
    Raises:
        Exception: If DOCX parsing fails or python-docx not available
    """
    if not PYTHON_DOCX_AVAILABLE:
        raise Exception("python-docx library not available")
    
    try:
        docx_file = io.BytesIO(file_content)
        document = Document(docx_file)
        
        text_content = []
        for paragraph in document.paragraphs:
            text_content.append(paragraph.text)
        
        return "\n".join(text_content)
    except Exception as e:
        logger.error(
            "Failed to extract text from DOCX",
            extra={
                "error_type": type(e).__name__,
                "error_message": str(e),
                "event": "docx_extraction_failed",
                "file_size_bytes": len(file_content)
            }
        )
        raise


def extract_name_from_text(text: str) -> Optional[str]:
    """
    Extract the first name from resume text.
    
    Args:
        text: Resume text content
        
    Returns:
        Extracted name or None if not found
    """
    lines = text.strip().split('\n')
    
    # Look for name patterns in the first few lines
    for line in lines[:5]:
        line = line.strip()
        
        # Skip empty lines or lines with common resume keywords
        if not line or any(keyword in line.lower() for keyword in [
            'email', 'phone', 'address', 'objective', 'summary', 'experience',
            'education', 'skills', 'software', 'engineer', 'developer', 'manager'
        ]):
            continue
            
        # Simple heuristic: if line contains 2-3 words and looks like a name
        words = line.split()
        if 2 <= len(words) <= 3 and all(word.replace('-', '').replace("'", '').isalpha() for word in words):
            return line
    
    return None


def extract_email_from_text(text: str) -> Optional[str]:
    """
    Extract email address from resume text.
    
    Args:
        text: Resume text content
        
    Returns:
        First email address found or None if not found
    """
    # Email regex pattern
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    
    emails = re.findall(email_pattern, text)
    
    # Return the first email found
    return emails[0] if emails else None


def extract_phone_from_text(text: str) -> Optional[str]:
    """
    Extract phone number from resume text.
    
    Args:
        text: Resume text content
        
    Returns:
        First phone number found or None if not found
    """
    # Phone number patterns
    phone_patterns = [
        r'\(\d{3}\)\s*\d{3}[-.\s]*\d{4}',  # (555) 123-4567
        r'\d{3}[-.\s]*\d{3}[-.\s]*\d{4}',  # 555-123-4567 or 555.123.4567
        r'\d{3}\s*\d{3}\s*\d{4}',          # 555 123 4567
        r'\+\d{1,3}\s*\d{3}\s*\d{3}\s*\d{4}',  # +1 555 123 4567
    ]
    
    for pattern in phone_patterns:
        phones = re.findall(pattern, text)
        if phones:
            return phones[0]
    
    return None


def extract_contact_info(text: str) -> Dict[str, Optional[str]]:
    """
    Extract contact information from resume text.
    
    Args:
        text: Resume text content
        
    Returns:
        Dictionary with name, email, and phone fields
    """
    return {
        "name": extract_name_from_text(text),
        "email": extract_email_from_text(text),
        "phone": extract_phone_from_text(text)
    }


@celery_app.task(bind=True, name="app.workers.resume_parser.parse_resume_task")
def parse_resume_task(self, file_content: bytes, file_type: str) -> Dict[str, Any]:
    """
    Parse uploaded resume file and extract text content.
    
    This task processes resume files asynchronously, extracts text content,
    and returns metadata about the parsing results.
    
    Args:
        file_content: Resume file content as bytes
        file_type: MIME type of the file
        
    Returns:
        Dictionary containing parsing results with keys:
        - status: "success" or "error"
        - file_type: Original MIME type
        - character_count: Number of characters extracted
        - extracted_text: Full text content (if successful)
        - error: Error message (if failed)
    """
    task_id = current_task.request.id if current_task else "unknown"
    start_time = time.time()
    
    logger.info(
        "Resume parsing task started",
        extra={
            "task_id": task_id,
            "file_type": file_type,
            "file_size_bytes": len(file_content),
            "file_size_mb": round(len(file_content) / (1024 * 1024), 2),
            "event": "task_started",
            "task_type": "resume_parsing"
        }
    )
    
    # Validate input
    if not file_content:
        error_msg = "Empty file content provided"
        processing_time_ms = round((time.time() - start_time) * 1000, 2)
        
        logger.error(
            "Resume parsing failed - empty file content",
            extra={
                "task_id": task_id,
                "error_message": error_msg,
                "processing_time_ms": processing_time_ms,
                "event": "task_failed",
                "error_category": "validation_error"
            }
        )
        return {
            "status": "error",
            "error": error_msg,
            "file_type": file_type,
            "character_count": 0
        }
    
    try:
        # Extract text based on file type
        if file_type == "application/pdf":
            extracted_text = extract_text_from_pdf(file_content)
        elif file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            extracted_text = extract_text_from_docx(file_content)
        else:
            error_msg = f"Unsupported file format: {file_type}"
            processing_time_ms = round((time.time() - start_time) * 1000, 2)
            
            logger.error(
                "Resume parsing failed - unsupported file format",
                extra={
                    "task_id": task_id,
                    "file_type": file_type,
                    "error_message": error_msg,
                    "processing_time_ms": processing_time_ms,
                    "event": "task_failed",
                    "error_category": "unsupported_format"
                }
            )
            return {
                "status": "error",
                "error": error_msg,
                "file_type": file_type,
                "character_count": 0
            }
        
        # Calculate metadata
        character_count = len(extracted_text)
        processing_time_ms = round((time.time() - start_time) * 1000, 2)
        
        # Extract contact information
        contact_info = extract_contact_info(extracted_text)
        contact_fields_found = [field for field, value in contact_info.items() if value]
        
        logger.info(
            "Resume parsing completed successfully",
            extra={
                "task_id": task_id,
                "file_type": file_type,
                "character_count": character_count,
                "processing_time_ms": processing_time_ms,
                "contact_fields_found": contact_fields_found,
                "contact_info_extracted": len(contact_fields_found) > 0,
                "text_preview_length": min(100, len(extracted_text)),
                "event": "task_completed",
                "task_status": "success"
            }
        )
        
        return {
            "status": "success",
            "file_type": file_type,
            "character_count": character_count,
            "extracted_text": extracted_text,
            "contact_info": contact_info
        }
        
    except Exception as e:
        error_msg = f"Failed to parse resume: {str(e)}"
        processing_time_ms = round((time.time() - start_time) * 1000, 2)
        
        logger.error(
            "Resume parsing failed with unexpected error",
            extra={
                "task_id": task_id,
                "file_type": file_type,
                "error_type": type(e).__name__,
                "error_message": error_msg,
                "processing_time_ms": processing_time_ms,
                "event": "task_failed",
                "error_category": "processing_error"
            }
        )
        return {
            "status": "error",
            "error": error_msg,
            "file_type": file_type,
            "character_count": 0
        }
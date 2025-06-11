"""
Tests for resume parser Celery worker.
"""

import io
from unittest.mock import patch, MagicMock

import pytest
from celery.exceptions import Retry

from app.workers.resume_parser import parse_resume_task


class TestParseResumeTask:
    """Test cases for parse_resume_task Celery task."""

    def test_parse_pdf_resume_success(self):
        """Test successful parsing of PDF resume."""
        # Mock PDF content
        pdf_content = b"%PDF-1.4 fake pdf content with some text"
        
        with patch('app.workers.resume_parser.extract_text_from_pdf') as mock_pdf_extract:
            extracted_text = "John Doe\nSoftware Engineer\nExperience with Python and FastAPI"
            mock_pdf_extract.return_value = extracted_text
            
            result = parse_resume_task.apply(args=[pdf_content, "application/pdf"]).get()
            
            assert result["status"] == "success"
            assert result["file_type"] == "application/pdf"
            assert result["character_count"] == len(extracted_text)
            assert "John Doe" in result["extracted_text"]
            mock_pdf_extract.assert_called_once()

    def test_parse_docx_resume_success(self):
        """Test successful parsing of DOCX resume."""
        # Mock DOCX content
        docx_content = b"PK\x03\x04 fake docx content"
        
        with patch('app.workers.resume_parser.extract_text_from_docx') as mock_docx_extract:
            extracted_text = "Jane Smith\nData Scientist\nSkills: Python, Machine Learning"
            mock_docx_extract.return_value = extracted_text
            
            result = parse_resume_task.apply(args=[docx_content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]).get()
            
            assert result["status"] == "success"
            assert result["file_type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            assert result["character_count"] == len(extracted_text)
            assert "Jane Smith" in result["extracted_text"]
            mock_docx_extract.assert_called_once()

    def test_parse_resume_unsupported_format(self):
        """Test parsing with unsupported file format."""
        result = parse_resume_task.apply(args=[b"content", "text/plain"]).get()
        
        assert result["status"] == "error"
        assert result["error"] == "Unsupported file format: text/plain"
        assert result["file_type"] == "text/plain"
        assert result["character_count"] == 0

    def test_parse_resume_pdf_extraction_error(self):
        """Test handling of PDF extraction errors."""
        pdf_content = b"%PDF-1.4 corrupted pdf"
        
        with patch('app.workers.resume_parser.extract_text_from_pdf') as mock_pdf_extract:
            mock_pdf_extract.side_effect = Exception("PDF parsing failed")
            
            result = parse_resume_task.apply(args=[pdf_content, "application/pdf"]).get()
            
            assert result["status"] == "error"
            assert "PDF parsing failed" in result["error"]
            assert result["file_type"] == "application/pdf"

    def test_parse_resume_docx_extraction_error(self):
        """Test handling of DOCX extraction errors."""
        docx_content = b"PK\x03\x04 corrupted docx"
        
        with patch('app.workers.resume_parser.extract_text_from_docx') as mock_docx_extract:
            mock_docx_extract.side_effect = Exception("DOCX parsing failed")
            
            result = parse_resume_task.apply(args=[docx_content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]).get()
            
            assert result["status"] == "error"
            assert "DOCX parsing failed" in result["error"]
            assert result["file_type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    def test_parse_resume_empty_content(self):
        """Test parsing with empty file content."""
        result = parse_resume_task.apply(args=[b"", "application/pdf"]).get()
        
        assert result["status"] == "error"
        assert "Empty file content" in result["error"]
        assert result["file_type"] == "application/pdf"

    def test_parse_resume_logs_metadata(self, caplog):
        """Test that parsing logs appropriate metadata."""
        pdf_content = b"%PDF-1.4 test content"
        
        with patch('app.workers.resume_parser.extract_text_from_pdf') as mock_pdf_extract:
            extracted_text = "Test resume content"
            mock_pdf_extract.return_value = extracted_text
            
            parse_resume_task.apply(args=[pdf_content, "application/pdf"]).get()
            
            # Check that logging occurred
            assert "Starting resume parsing" in caplog.text
            assert "Resume parsing completed successfully" in caplog.text
            assert "File type: application/pdf" in caplog.text
            assert f"Character count: {len(extracted_text)}" in caplog.text

    def test_parse_resume_task_is_celery_task(self):
        """Test that parse_resume_task is properly configured as Celery task."""
        assert hasattr(parse_resume_task, 'apply')
        assert hasattr(parse_resume_task, 'delay')
        assert parse_resume_task.name == 'app.workers.resume_parser.parse_resume_task'

    def test_parse_resume_extracts_structured_data(self):
        """Test that resume parsing extracts structured data like name, email, phone."""
        pdf_content = b"%PDF-1.4 fake pdf content"
        
        with patch('app.workers.resume_parser.extract_text_from_pdf') as mock_pdf_extract:
            # Mock resume text with typical contact information
            resume_text = """
            John Doe
            Software Engineer
            Email: john.doe@example.com
            Phone: (555) 123-4567
            Experience with Python and FastAPI
            """
            mock_pdf_extract.return_value = resume_text
            
            result = parse_resume_task.apply(args=[pdf_content, "application/pdf"]).get()
            
            assert result["status"] == "success"
            assert "contact_info" in result
            
            contact_info = result["contact_info"]
            assert contact_info["name"] == "John Doe"
            assert contact_info["email"] == "john.doe@example.com"
            assert contact_info["phone"] == "(555) 123-4567"

    def test_parse_resume_handles_missing_contact_info(self):
        """Test resume parsing when contact information is not found."""
        pdf_content = b"%PDF-1.4 fake pdf content"
        
        with patch('app.workers.resume_parser.extract_text_from_pdf') as mock_pdf_extract:
            # Resume text without clear contact information
            resume_text = "Some random text without contact information"
            mock_pdf_extract.return_value = resume_text
            
            result = parse_resume_task.apply(args=[pdf_content, "application/pdf"]).get()
            
            assert result["status"] == "success"
            assert "contact_info" in result
            
            contact_info = result["contact_info"]
            assert contact_info["name"] is None
            assert contact_info["email"] is None
            assert contact_info["phone"] is None

    def test_parse_resume_extracts_multiple_phones_and_emails(self):
        """Test resume parsing with multiple phone numbers and emails."""
        pdf_content = b"%PDF-1.4 fake pdf content"
        
        with patch('app.workers.resume_parser.extract_text_from_pdf') as mock_pdf_extract:
            resume_text = """
            Jane Smith
            jane@work.com
            Personal: jane.smith@gmail.com
            Work: (555) 987-6543
            Mobile: 555.123.4567
            """
            mock_pdf_extract.return_value = resume_text
            
            result = parse_resume_task.apply(args=[pdf_content, "application/pdf"]).get()
            
            assert result["status"] == "success"
            contact_info = result["contact_info"]
            
            # Should extract the first email and phone found
            assert contact_info["name"] == "Jane Smith"
            assert contact_info["email"] in ["jane@work.com", "jane.smith@gmail.com"]
            assert contact_info["phone"] in ["(555) 987-6543", "555.123.4567"]
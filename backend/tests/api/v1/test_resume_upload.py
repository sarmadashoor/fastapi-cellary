"""
Tests for resume upload endpoint at /api/v1/resumes/upload

This module tests the resume upload functionality with focus on:
- File type validation (PDF, DOCX supported)
- File size limits (5MB maximum)
- Proper error handling and status codes
- Response schema validation
- Celery task queueing
"""

import io
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import status


class TestResumeUpload:
    """Test cases for resume upload endpoint."""

    @pytest.mark.resume
    @pytest.mark.does_not_change_db
    @patch('app.workers.resume_parser.parse_resume_task.delay')
    def test_upload_valid_pdf_file(self, mock_celery_task, client, admin_token):
        """Test uploading a valid PDF file under 5MB returns 200 OK with task_id and queues Celery task."""
        # Mock Celery task delay to return a task object with id
        mock_task = type('MockTask', (), {'id': 'test-task-id-12345'})()
        mock_celery_task.return_value = mock_task
        
        # Create a small PDF-like file (simulated)
        pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n"
        pdf_content += b"x" * (1024 * 1024)  # 1MB file
        
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_file:
            temp_file.write(pdf_content)
            temp_file.flush()
            
            with open(temp_file.name, "rb") as f:
                response = client.post(
                    "/api/resumes/upload",
                    files={"file": ("resume.pdf", f, "application/pdf")},
                    headers={"Authorization": f"Bearer {admin_token}"}
                )
        
        # Clean up
        Path(temp_file.name).unlink()
        
        assert response.status_code == status.HTTP_200_OK, (
            f"Expected 200 OK for valid PDF upload, got {response.status_code}: {response.text}"
        )
        
        response_data = response.json()
        assert "task_id" in response_data, "Response should contain task_id field"
        assert isinstance(response_data["task_id"], str), "task_id should be a string"
        assert response_data["task_id"] == "test-task-id-12345", "task_id should match mocked task id"
        
        # Verify Celery task was called with correct arguments
        mock_celery_task.assert_called_once()
        call_args = mock_celery_task.call_args[0]
        assert len(call_args) == 2, "Celery task should be called with file content and mime type"
        assert call_args[0] == pdf_content, "First argument should be file content"
        assert call_args[1] == "application/pdf", "Second argument should be MIME type"

    @pytest.mark.resume
    @pytest.mark.does_not_change_db
    @patch('app.workers.resume_parser.parse_resume_task.delay')
    def test_upload_valid_docx_file(self, mock_celery_task, client, admin_token):
        """Test uploading a valid DOCX file under 5MB returns 200 OK with task_id and queues Celery task."""
        # Mock Celery task delay to return a task object with id
        mock_task = type('MockTask', (), {'id': 'test-docx-task-67890'})()
        mock_celery_task.return_value = mock_task
        
        # Create a minimal DOCX-like file (simulated)
        docx_content = b"PK\x03\x04\x14\x00\x00\x00\x08\x00"  # ZIP signature for DOCX
        docx_content += b"x" * (2 * 1024 * 1024)  # 2MB file
        
        files = {"file": ("resume.docx", io.BytesIO(docx_content), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        
        response = client.post("/api/resumes/upload", files=files, headers={"Authorization": f"Bearer {admin_token}"})
        
        assert response.status_code == status.HTTP_200_OK, (
            f"Expected 200 OK for valid DOCX upload, got {response.status_code}: {response.text}"
        )
        
        response_data = response.json()
        assert "task_id" in response_data, "Response should contain task_id field"
        assert isinstance(response_data["task_id"], str), "task_id should be a string"
        assert response_data["task_id"] == "test-docx-task-67890", "task_id should match mocked task id"
        
        # Verify Celery task was called with correct arguments
        mock_celery_task.assert_called_once()
        call_args = mock_celery_task.call_args[0]
        assert len(call_args) == 2, "Celery task should be called with file content and mime type"
        assert call_args[0] == docx_content, "First argument should be file content"
        assert call_args[1] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "Second argument should be MIME type"

    @pytest.mark.resume
    @pytest.mark.does_not_change_db
    def test_upload_unsupported_file_type(self, client, admin_token):
        """Test uploading an unsupported file type returns 400 Bad Request."""
        txt_content = b"This is a plain text resume file content."
        
        files = {"file": ("resume.txt", io.BytesIO(txt_content), "text/plain")}
        
        response = client.post("/api/resumes/upload", files=files, headers={"Authorization": f"Bearer {admin_token}"})
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST, (
            f"Expected 400 Bad Request for unsupported file type, got {response.status_code}: {response.text}"
        )
        
        response_data = response.json()
        assert "detail" in response_data, "Error response should contain detail field"
        assert "unsupported" in response_data["detail"].lower() or "invalid" in response_data["detail"].lower(), (
            "Error message should indicate unsupported file type"
        )

    @pytest.mark.resume
    @pytest.mark.does_not_change_db
    def test_upload_file_exceeds_size_limit(self, client, admin_token):
        """Test uploading a file over 5MB returns 413 Payload Too Large."""
        # Create a file larger than 5MB
        large_pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n"
        large_pdf_content += b"x" * (6 * 1024 * 1024)  # 6MB file
        
        files = {"file": ("large_resume.pdf", io.BytesIO(large_pdf_content), "application/pdf")}
        
        response = client.post("/api/resumes/upload", files=files, headers={"Authorization": f"Bearer {admin_token}"})
        
        assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, (
            f"Expected 413 Payload Too Large for oversized file, got {response.status_code}: {response.text}"
        )
        
        response_data = response.json()
        assert "detail" in response_data, "Error response should contain detail field"
        assert "size" in response_data["detail"].lower() or "large" in response_data["detail"].lower(), (
            "Error message should indicate file size issue"
        )

    @pytest.mark.resume
    @pytest.mark.does_not_change_db
    def test_upload_no_file_provided(self, client, admin_token):
        """Test uploading with no file returns 422 Unprocessable Entity."""
        response = client.post("/api/resumes/upload", headers={"Authorization": f"Bearer {admin_token}"})
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, (
            f"Expected 422 Unprocessable Entity for missing file, got {response.status_code}: {response.text}"
        )
        
        response_data = response.json()
        assert "message" in response_data, "Error response should contain message field"

    @pytest.mark.resume
    @pytest.mark.does_not_change_db
    def test_upload_empty_file(self, client, admin_token):
        """Test uploading an empty file returns 400 Bad Request."""
        files = {"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")}
        
        response = client.post("/api/resumes/upload", files=files, headers={"Authorization": f"Bearer {admin_token}"})
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST, (
            f"Expected 400 Bad Request for empty file, got {response.status_code}: {response.text}"
        )
        
        response_data = response.json()
        assert "detail" in response_data, "Error response should contain detail field"
        assert "empty" in response_data["detail"].lower() or "size" in response_data["detail"].lower(), (
            "Error message should indicate empty file issue"
        )

    @pytest.mark.resume
    @pytest.mark.does_not_change_db
    def test_upload_response_schema_validation(self, client, admin_token):
        """Test that successful upload response matches ResumeUploadResponse schema."""
        pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n"
        pdf_content += b"x" * (500 * 1024)  # 500KB file
        
        files = {"file": ("test_resume.pdf", io.BytesIO(pdf_content), "application/pdf")}
        
        response = client.post("/api/resumes/upload", files=files, headers={"Authorization": f"Bearer {admin_token}"})
        
        assert response.status_code == status.HTTP_200_OK, (
            f"Expected 200 OK for valid upload, got {response.status_code}: {response.text}"
        )
        
        response_data = response.json()
        
        # Validate ResumeUploadResponse schema
        expected_fields = {"task_id"}
        actual_fields = set(response_data.keys())
        
        assert expected_fields.issubset(actual_fields), (
            f"Response missing required fields. Expected: {expected_fields}, Got: {actual_fields}"
        )
        
        # Validate field types and constraints
        assert isinstance(response_data["task_id"], str), "task_id must be a string"
        assert response_data["task_id"].strip(), "task_id must not be empty or whitespace"
        
        # Task ID should be UUID-like or similar format
        task_id = response_data["task_id"]
        assert len(task_id) >= 8, "task_id should be at least 8 characters long"
        assert not task_id.isspace(), "task_id should not be only whitespace"

    @pytest.mark.resume  
    @pytest.mark.does_not_change_db
    def test_upload_file_with_special_characters_in_name(self, client, admin_token):
        """Test uploading a file with special characters in filename."""
        pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n"
        pdf_content += b"x" * (100 * 1024)  # 100KB file
        
        # Test filename with spaces, special characters
        special_filename = "John Doe's Resume (2024) - Software Engineer.pdf"
        
        files = {"file": (special_filename, io.BytesIO(pdf_content), "application/pdf")}
        
        response = client.post("/api/resumes/upload", files=files, headers={"Authorization": f"Bearer {admin_token}"})
        
        assert response.status_code == status.HTTP_200_OK, (
            f"Expected 200 OK for file with special characters in name, got {response.status_code}: {response.text}"
        )
        
        response_data = response.json()
        assert "task_id" in response_data, "Response should contain task_id field"

    @pytest.mark.resume
    @pytest.mark.does_not_change_db  
    def test_upload_file_boundary_size_just_under_limit(self, client, admin_token):
        """Test uploading a file just under the 5MB limit succeeds."""
        # Create file just under 5MB (5MB - 1KB)
        size_just_under_limit = (5 * 1024 * 1024) - 1024
        pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n"
        pdf_content += b"x" * (size_just_under_limit - len(pdf_content))
        
        files = {"file": ("boundary_resume.pdf", io.BytesIO(pdf_content), "application/pdf")}
        
        response = client.post("/api/resumes/upload", files=files, headers={"Authorization": f"Bearer {admin_token}"})
        
        assert response.status_code == status.HTTP_200_OK, (
            f"Expected 200 OK for file just under size limit, got {response.status_code}: {response.text}"
        )
        
        response_data = response.json()
        assert "task_id" in response_data, "Response should contain task_id field"

    @pytest.mark.resume
    @pytest.mark.does_not_change_db
    def test_upload_file_boundary_size_just_over_limit(self, client, admin_token):
        """Test uploading a file just over the 5MB limit fails."""
        # Create file just over 5MB (5MB + 1KB)
        size_just_over_limit = (5 * 1024 * 1024) + 1024
        pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n"
        pdf_content += b"x" * (size_just_over_limit - len(pdf_content))
        
        files = {"file": ("boundary_resume.pdf", io.BytesIO(pdf_content), "application/pdf")}
        
        response = client.post("/api/resumes/upload", files=files, headers={"Authorization": f"Bearer {admin_token}"})
        
        assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, (
            f"Expected 413 Payload Too Large for file just over size limit, got {response.status_code}: {response.text}"
        )
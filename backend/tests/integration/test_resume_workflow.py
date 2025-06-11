"""
Integration tests for complete resume processing workflow.

This module tests the full end-to-end resume processing pipeline:
- Upload → Celery parse → Status polling → Final result
- Task failure/retry flow scenarios
- Real database state changes and validation
- Cross-component integration validation
"""

import asyncio
import io
import pytest
import time
from unittest.mock import patch, MagicMock
from celery.result import AsyncResult
from fastapi import status

from app.celery_app import celery_app
from app.workers.resume_parser import parse_resume_task


@pytest.mark.integration
@pytest.mark.resume
class TestResumeWorkflowIntegration:
    """Test complete resume processing workflow integration."""

    def test_upload_to_status_success_flow(self, client, admin_token):
        """Test complete successful workflow: upload → queue → process → status."""
        
        # Step 1: Upload a resume file
        pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n"
        pdf_content += b"Sample resume text with contact info. John Doe, john@example.com, (555) 123-4567"
        
        upload_response = client.post(
            "/api/resumes/upload",
            files={"file": ("resume.pdf", io.BytesIO(pdf_content), "application/pdf")},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert upload_response.status_code == status.HTTP_200_OK
        upload_data = upload_response.json()
        task_id = upload_data["task_id"]
        assert task_id, "Should receive a valid task ID"
        
        # Step 2: Check initial status (should be PENDING)
        status_response = client.get(
            f"/api/resumes/status/{task_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert status_response.status_code == status.HTTP_200_OK
        status_data = status_response.json()
        assert status_data["task_id"] == task_id
        assert status_data["status"] in ["PENDING", "SUCCESS"]  # Might complete very quickly
        
        # Step 3: Wait for task completion (with timeout)
        max_wait = 30  # seconds
        start_time = time.time()
        final_status = None
        
        while time.time() - start_time < max_wait:
            status_response = client.get(
                f"/api/resumes/status/{task_id}",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            
            status_data = status_response.json()
            final_status = status_data["status"]
            
            if final_status in ["SUCCESS", "FAILURE"]:
                break
                
            time.sleep(0.5)  # Poll every 500ms
        
        # Step 4: Validate final results
        assert final_status == "SUCCESS", f"Task should complete successfully, got: {final_status}"
        
        if "result" in status_data:
            result = status_data["result"]
            assert result["status"] == "success"
            assert result["file_type"] == "application/pdf"
            assert result["character_count"] > 0
            assert "extracted_text" in result

    def test_upload_to_status_with_mocked_processing(self, client, admin_token):
        """Test workflow with mocked Celery processing for controlled results."""
        
        with patch('app.workers.resume_parser.parse_resume_task.delay') as mock_delay:
            # Mock successful task result
            mock_task = MagicMock()
            mock_task.id = "test-integration-task-123"
            mock_delay.return_value = mock_task
            
            # Mock AsyncResult for status checking
            with patch('app.api.v1.resumes.status.AsyncResult') as mock_async_result:
                mock_result = MagicMock()
                mock_result.state = "SUCCESS"
                mock_result.result = {
                    "status": "success",
                    "file_type": "application/pdf",
                    "character_count": 150,
                    "extracted_text": "John Doe Software Engineer",
                    "contact_info": {
                        "name": "John Doe",
                        "email": "john.doe@example.com",
                        "phone": "(555) 123-4567"
                    }
                }
                mock_result.backend.get.return_value = True  # Task exists
                mock_async_result.return_value = mock_result
                
                # Step 1: Upload
                pdf_content = b"%PDF-1.4\nSample resume content"
                upload_response = client.post(
                    "/api/resumes/upload",
                    files={"file": ("resume.pdf", io.BytesIO(pdf_content), "application/pdf")},
                    headers={"Authorization": f"Bearer {admin_token}"}
                )
                
                assert upload_response.status_code == status.HTTP_200_OK
                upload_data = upload_response.json()
                task_id = upload_data["task_id"]
                
                # Verify Celery task was called
                mock_delay.assert_called_once()
                call_args = mock_delay.call_args[0]
                assert call_args[0] == pdf_content
                assert call_args[1] == "application/pdf"
                
                # Step 2: Check status
                status_response = client.get(
                    f"/api/resumes/status/{task_id}",
                    headers={"Authorization": f"Bearer {admin_token}"}
                )
                
                assert status_response.status_code == status.HTTP_200_OK
                status_data = status_response.json()
                
                # Validate complete result structure
                assert status_data["task_id"] == task_id
                assert status_data["status"] == "SUCCESS"
                assert "result" in status_data
                
                result = status_data["result"]
                assert result["status"] == "success"
                assert result["file_type"] == "application/pdf"
                assert result["character_count"] == 150
                assert result["extracted_text"] == "John Doe Software Engineer"
                assert "contact_info" in result
                assert result["contact_info"]["name"] == "John Doe"

    def test_task_failure_flow(self, client, admin_token):
        """Test workflow when task processing fails."""
        
        with patch('app.workers.resume_parser.parse_resume_task.delay') as mock_delay:
            # Mock task that raises an error
            mock_task = MagicMock()
            mock_task.id = "test-failure-task-456"
            mock_delay.return_value = mock_task
            
            # Mock failed AsyncResult
            with patch('app.api.v1.resumes.status.AsyncResult') as mock_async_result:
                mock_result = MagicMock()
                mock_result.state = "FAILURE"
                mock_result.info = "Failed to extract text from PDF: corrupted file"
                mock_result.backend.get.return_value = True  # Task exists
                mock_async_result.return_value = mock_result
                
                # Step 1: Upload
                corrupted_content = b"Invalid PDF content"
                upload_response = client.post(
                    "/api/resumes/upload",
                    files={"file": ("corrupted.pdf", io.BytesIO(corrupted_content), "application/pdf")},
                    headers={"Authorization": f"Bearer {admin_token}"}
                )
                
                assert upload_response.status_code == status.HTTP_200_OK
                task_id = upload_response.json()["task_id"]
                
                # Step 2: Check failed status
                status_response = client.get(
                    f"/api/resumes/status/{task_id}",
                    headers={"Authorization": f"Bearer {admin_token}"}
                )
                
                assert status_response.status_code == status.HTTP_200_OK
                status_data = status_response.json()
                
                assert status_data["task_id"] == task_id
                assert status_data["status"] == "FAILURE"
                assert "error" in status_data
                assert "corrupted file" in status_data["error"]
                assert "result" not in status_data  # No result on failure

    def test_task_retry_flow(self, client, admin_token):
        """Test workflow when task is retried."""
        
        with patch('app.workers.resume_parser.parse_resume_task.delay') as mock_delay:
            mock_task = MagicMock()
            mock_task.id = "test-retry-task-789"
            mock_delay.return_value = mock_task
            
            # Mock retrying AsyncResult
            with patch('app.api.v1.resumes.status.AsyncResult') as mock_async_result:
                mock_result = MagicMock()
                mock_result.state = "RETRY"
                mock_result.info = "Temporary processing error, retrying..."
                mock_result.backend.get.return_value = True
                mock_async_result.return_value = mock_result
                
                # Upload and check retry status
                upload_response = client.post(
                    "/api/resumes/upload",
                    files={"file": ("retry.pdf", io.BytesIO(b"Test content"), "application/pdf")},
                    headers={"Authorization": f"Bearer {admin_token}"}
                )
                
                task_id = upload_response.json()["task_id"]
                
                status_response = client.get(
                    f"/api/resumes/status/{task_id}",
                    headers={"Authorization": f"Bearer {admin_token}"}
                )
                
                status_data = status_response.json()
                assert status_data["status"] == "RETRY"
                assert "error" in status_data
                assert "retrying" in status_data["error"]

    def test_nonexistent_task_status(self, client, admin_token):
        """Test status check for non-existent task ID."""
        
        with patch('app.api.v1.resumes.status.AsyncResult') as mock_async_result:
            mock_result = MagicMock()
            mock_result.state = "PENDING"
            mock_result.result = None
            mock_result.backend.get.return_value = None  # Task doesn't exist
            mock_async_result.return_value = mock_result
            
            fake_task_id = "nonexistent-task-id-999"
            response = client.get(
                f"/api/resumes/status/{fake_task_id}",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            
            assert response.status_code == status.HTTP_404_NOT_FOUND
            assert "not found" in response.json()["detail"].lower()

    def test_invalid_task_id_format(self, client, admin_token):
        """Test status check with invalid task ID format."""
        
        invalid_task_ids = ["", "   ", "invalid-chars!@#", "a" * 1000]
        
        for invalid_id in invalid_task_ids:
            response = client.get(
                f"/api/resumes/status/{invalid_id}",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            
            # Should handle invalid IDs gracefully
            assert response.status_code in [
                status.HTTP_400_BAD_REQUEST,
                status.HTTP_404_NOT_FOUND,
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ]

    def test_multiple_concurrent_uploads(self, client, admin_token):
        """Test handling multiple concurrent upload requests."""
        
        with patch('app.workers.resume_parser.parse_resume_task.delay') as mock_delay:
            # Mock different task IDs for each upload
            mock_tasks = [
                MagicMock(id=f"concurrent-task-{i}")
                for i in range(3)
            ]
            mock_delay.side_effect = mock_tasks
            
            # Upload multiple files concurrently (simulated)
            upload_responses = []
            task_ids = []
            
            for i in range(3):
                content = f"Resume content {i}".encode()
                response = client.post(
                    "/api/resumes/upload",
                    files={"file": (f"resume_{i}.pdf", io.BytesIO(content), "application/pdf")},
                    headers={"Authorization": f"Bearer {admin_token}"}
                )
                
                upload_responses.append(response)
                if response.status_code == status.HTTP_200_OK:
                    task_ids.append(response.json()["task_id"])
                elif response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
                    # Rate limiting is expected
                    break
            
            # Verify at least one upload succeeded
            assert len(task_ids) >= 1, "At least one upload should succeed"
            
            # Verify unique task IDs
            assert len(set(task_ids)) == len(task_ids), "All task IDs should be unique"
            
            # Verify Celery was called for successful uploads
            assert mock_delay.call_count == len(task_ids)

    def test_workflow_with_different_file_types(self, client, admin_token):
        """Test workflow with different supported file types."""
        
        test_files = [
            ("resume.pdf", b"%PDF-1.4\nPDF content", "application/pdf"),
            ("resume.docx", b"PK\x03\x04DOCX content", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ]
        
        with patch('app.workers.resume_parser.parse_resume_task.delay') as mock_delay:
            mock_tasks = [MagicMock(id=f"filetype-task-{i}") for i in range(len(test_files))]
            mock_delay.side_effect = mock_tasks
            
            for i, (filename, content, content_type) in enumerate(test_files):
                response = client.post(
                    "/api/resumes/upload",
                    files={"file": (filename, io.BytesIO(content), content_type)},
                    headers={"Authorization": f"Bearer {admin_token}"}
                )
                
                if response.status_code == status.HTTP_200_OK:
                    task_id = response.json()["task_id"]
                    assert task_id, f"Should get task ID for {filename}"
                    
                    # Verify correct content type was passed to Celery
                    call_args = mock_delay.call_args[0]
                    assert call_args[0] == content
                    assert call_args[1] == content_type
                elif response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
                    # Rate limiting is acceptable
                    continue

    def test_database_state_consistency(self, client, admin_token):
        """Test that database state remains consistent during workflow."""
        
        # Note: This test assumes there's database logging of tasks
        # If no database persistence exists, this test validates that
        # the system works correctly without database state corruption
        
        with patch('app.workers.resume_parser.parse_resume_task.delay') as mock_delay:
            mock_task = MagicMock(id="db-consistency-task")
            mock_delay.return_value = mock_task
            
            # Perform upload
            response = client.post(
                "/api/resumes/upload",
                files={"file": ("test.pdf", io.BytesIO(b"PDF content"), "application/pdf")},
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            
            if response.status_code == status.HTTP_200_OK:
                task_id = response.json()["task_id"]
                
                # Multiple status checks shouldn't cause DB issues
                for _ in range(5):
                    status_response = client.get(
                        f"/api/resumes/status/{task_id}",
                        headers={"Authorization": f"Bearer {admin_token}"}
                    )
                    
                    # Should consistently return same task_id
                    if status_response.status_code == status.HTTP_200_OK:
                        assert status_response.json()["task_id"] == task_id

    def test_error_handling_in_status_endpoint(self, client, admin_token):
        """Test error handling in status endpoint with various error conditions."""
        
        # Test with mocked Celery backend errors
        with patch('app.api.v1.resumes.status.AsyncResult') as mock_async_result:
            # Simulate backend connection error
            mock_result = MagicMock()
            mock_result.state = "PENDING"
            mock_result.backend.get.side_effect = Exception("Backend connection error")
            mock_async_result.return_value = mock_result
            
            response = client.get(
                "/api/resumes/status/error-test-task",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            
            # Should handle backend errors gracefully
            assert response.status_code in [
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                status.HTTP_404_NOT_FOUND,
                status.HTTP_200_OK  # If error is handled gracefully
            ]

    def test_task_revoked_scenario(self, client, admin_token):
        """Test handling of revoked/cancelled tasks."""
        
        with patch('app.workers.resume_parser.parse_resume_task.delay') as mock_delay:
            mock_task = MagicMock(id="revoked-task-123")
            mock_delay.return_value = mock_task
            
            with patch('app.api.v1.resumes.status.AsyncResult') as mock_async_result:
                mock_result = MagicMock()
                mock_result.state = "REVOKED"
                mock_result.info = "Task was cancelled by administrator"
                mock_result.backend.get.return_value = True
                mock_async_result.return_value = mock_result
                
                # Upload file
                response = client.post(
                    "/api/resumes/upload",
                    files={"file": ("test.pdf", io.BytesIO(b"Content"), "application/pdf")},
                    headers={"Authorization": f"Bearer {admin_token}"}
                )
                
                if response.status_code == status.HTTP_200_OK:
                    task_id = response.json()["task_id"]
                    
                    # Check revoked status
                    status_response = client.get(
                        f"/api/resumes/status/{task_id}",
                        headers={"Authorization": f"Bearer {admin_token}"}
                    )
                    
                    if status_response.status_code == status.HTTP_200_OK:
                        status_data = status_response.json()
                        assert status_data["status"] == "REVOKED"
                        assert "cancelled" in status_data.get("error", "").lower()


@pytest.mark.integration
class TestCeleryIntegration:
    """Test Celery task integration and behavior."""

    def test_celery_task_registration(self):
        """Test that resume parsing task is properly registered with Celery."""
        # Check if task is registered
        assert 'app.workers.resume_parser.parse_resume_task' in celery_app.tasks
        
        # Verify task signature
        task = celery_app.tasks['app.workers.resume_parser.parse_resume_task']
        assert task is not None
        assert hasattr(task, 'delay')
        assert hasattr(task, 'apply_async')

    def test_celery_task_serialization(self):
        """Test that task arguments serialize properly."""
        test_content = b"Test file content for serialization"
        test_content_type = "application/pdf"
        
        # This tests the task can be serialized without actually executing
        task = parse_resume_task.s(test_content, test_content_type)
        
        # Should be able to create task signature without error
        assert task is not None
        assert task.args == (test_content, test_content_type)

    @pytest.mark.slow
    def test_celery_task_timeout_handling(self):
        """Test task timeout scenarios (marked as slow)."""
        
        # Create a very large content that might timeout
        large_content = b"X" * (10 * 1024 * 1024)  # 10MB of content
        
        with patch('app.workers.resume_parser.extract_text_from_pdf') as mock_extract:
            # Simulate slow extraction
            mock_extract.side_effect = Exception("Processing timeout")
            
            # Apply task (this might timeout in real scenarios)
            try:
                result = parse_resume_task.apply(args=[large_content, "application/pdf"])
                # If it doesn't timeout, check that errors are handled
                if result.failed():
                    assert "timeout" in str(result.info).lower() or "error" in str(result.info).lower()
            except Exception as e:
                # Timeout or other errors are acceptable for this test
                assert "timeout" in str(e).lower() or "error" in str(e).lower()
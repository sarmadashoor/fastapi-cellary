"""
Tests for resume status API endpoint.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app


class TestResumeStatusEndpoint:
    """Test cases for GET /api/v1/resumes/status/{task_id} endpoint."""
    
    def setup_method(self):
        """Set up test client."""
        self.client = TestClient(app)
        self.base_url = "/api/resumes"
    
    def test_get_status_success_with_result(self):
        """Test successful status retrieval for completed task."""
        task_id = "test-task-123"
        mock_result = {
            "status": "success",
            "file_type": "application/pdf",
            "character_count": 1500,
            "extracted_text": "John Doe\nSoftware Engineer...",
            "contact_info": {
                "name": "John Doe",
                "email": "john@example.com",
                "phone": "(555) 123-4567"
            }
        }
        
        with patch('app.api.v1.resumes.status.AsyncResult') as mock_async_result:
            mock_task = MagicMock()
            mock_task.state = "SUCCESS"
            mock_task.result = mock_result
            mock_async_result.return_value = mock_task
            
            response = self.client.get(f"{self.base_url}/status/{task_id}")
            
            assert response.status_code == 200
            response_data = response.json()
            assert response_data["task_id"] == task_id
            assert response_data["status"] == "SUCCESS"
            assert response_data["result"] == mock_result
            assert response_data["error"] is None
    
    def test_get_status_pending(self):
        """Test status retrieval for pending task."""
        task_id = "pending-task-456"
        
        with patch('app.api.v1.resumes.status.AsyncResult') as mock_async_result:
            mock_task = MagicMock()
            mock_task.state = "PENDING"
            mock_task.result = None
            mock_task.backend.get.return_value = "some_value"  # Task exists
            mock_task.key = f"celery-task-meta-{task_id}"
            mock_async_result.return_value = mock_task
            
            response = self.client.get(f"{self.base_url}/status/{task_id}")
            
            assert response.status_code == 200
            response_data = response.json()
            assert response_data["task_id"] == task_id
            assert response_data["status"] == "PENDING"
            assert response_data["result"] is None
            assert response_data["error"] is None
    
    def test_get_status_failure_with_error(self):
        """Test status retrieval for failed task."""
        task_id = "failed-task-789"
        error_message = "PDF parsing failed: corrupted file"
        
        with patch('app.api.v1.resumes.status.AsyncResult') as mock_async_result:
            mock_task = MagicMock()
            mock_task.state = "FAILURE"
            mock_task.info = error_message
            mock_async_result.return_value = mock_task
            
            response = self.client.get(f"{self.base_url}/status/{task_id}")
            
            assert response.status_code == 200
            response_data = response.json()
            assert response_data["task_id"] == task_id
            assert response_data["status"] == "FAILURE"
            assert response_data["result"] is None
            assert response_data["error"] == error_message
    
    def test_get_status_retry_state(self):
        """Test status retrieval for task in retry state."""
        task_id = "retry-task-101"
        retry_info = "Retrying after temporary failure"
        
        with patch('app.api.v1.resumes.status.AsyncResult') as mock_async_result:
            mock_task = MagicMock()
            mock_task.state = "RETRY"
            mock_task.info = retry_info
            mock_async_result.return_value = mock_task
            
            response = self.client.get(f"{self.base_url}/status/{task_id}")
            
            assert response.status_code == 200
            response_data = response.json()
            assert response_data["task_id"] == task_id
            assert response_data["status"] == "RETRY"
            assert response_data["result"] is None
            assert response_data["error"] == retry_info
    
    def test_get_status_revoked_state(self):
        """Test status retrieval for revoked/cancelled task."""
        task_id = "revoked-task-202"
        
        with patch('app.api.v1.resumes.status.AsyncResult') as mock_async_result:
            mock_task = MagicMock()
            mock_task.state = "REVOKED"
            mock_task.info = None
            mock_async_result.return_value = mock_task
            
            response = self.client.get(f"{self.base_url}/status/{task_id}")
            
            assert response.status_code == 200
            response_data = response.json()
            assert response_data["task_id"] == task_id
            assert response_data["status"] == "REVOKED"
            assert response_data["result"] is None
            assert response_data["error"] is None
    
    def test_get_status_empty_task_id(self):
        """Test status endpoint with empty task ID."""
        response = self.client.get(f"{self.base_url}/status/")
        
        # Should return 404 for missing path parameter
        assert response.status_code == 404
    
    def test_get_status_whitespace_task_id(self):
        """Test status endpoint with whitespace-only task ID."""
        response = self.client.get(f"{self.base_url}/status/   ")
        
        assert response.status_code == 400
        response_data = response.json()
        assert "Task ID is required" in response_data["detail"]
    
    def test_get_status_task_not_found(self):
        """Test status retrieval for non-existent task."""
        task_id = "nonexistent-task-999"
        
        with patch('app.api.v1.resumes.status.AsyncResult') as mock_async_result:
            mock_task = MagicMock()
            mock_task.state = "PENDING"
            mock_task.result = None
            mock_task.backend.get.return_value = None  # Task doesn't exist
            mock_task.key = f"celery-task-meta-{task_id}"
            mock_async_result.return_value = mock_task
            
            response = self.client.get(f"{self.base_url}/status/{task_id}")
            
            assert response.status_code == 404
            response_data = response.json()
            assert "Task not found" in response_data["detail"]
    
    def test_get_status_celery_exception(self):
        """Test handling of Celery-related exceptions."""
        task_id = "exception-task-555"
        
        with patch('app.api.v1.resumes.status.AsyncResult') as mock_async_result:
            mock_async_result.side_effect = Exception("Celery connection error")
            
            response = self.client.get(f"{self.base_url}/status/{task_id}")
            
            assert response.status_code == 500
            response_data = response.json()
            assert "An error occurred while retrieving task status" in response_data["detail"]
    
    def test_get_status_validates_task_id_format(self):
        """Test that endpoint accepts various valid task ID formats."""
        valid_task_ids = [
            "uuid-123-456-789",
            "simple-task-id",
            "task_with_underscores",
            "UPPERCASE-TASK",
            "123456789",
            "a1b2c3d4-e5f6-7890-abcd-ef1234567890"  # UUID format
        ]
        
        for task_id in valid_task_ids:
            with patch('app.api.v1.resumes.status.AsyncResult') as mock_async_result:
                mock_task = MagicMock()
                mock_task.state = "PENDING"
                mock_task.result = None
                mock_task.backend.get.return_value = "exists"
                mock_task.key = f"celery-task-meta-{task_id}"
                mock_async_result.return_value = mock_task
                
                response = self.client.get(f"{self.base_url}/status/{task_id}")
                assert response.status_code == 200
                assert response.json()["task_id"] == task_id
    
    def test_get_status_logs_appropriately(self, caplog):
        """Test that status endpoint logs appropriately."""
        task_id = "logging-test-task"
        
        with patch('app.api.v1.resumes.status.AsyncResult') as mock_async_result:
            mock_task = MagicMock()
            mock_task.state = "SUCCESS"
            mock_task.result = {"status": "success"}
            mock_async_result.return_value = mock_task
            
            response = self.client.get(f"{self.base_url}/status/{task_id}")
            
            assert response.status_code == 200
            assert f"Retrieved status for task {task_id}: SUCCESS" in caplog.text
    
    def test_get_status_response_model_validation(self):
        """Test that response matches the ResumeStatusResponse model."""
        task_id = "model-validation-task"
        
        with patch('app.api.v1.resumes.status.AsyncResult') as mock_async_result:
            mock_task = MagicMock()
            mock_task.state = "SUCCESS"
            mock_task.result = {
                "status": "success",
                "file_type": "application/pdf",
                "character_count": 100,
                "extracted_text": "Test content",
                "contact_info": {"name": "Test User", "email": "test@example.com", "phone": None}
            }
            mock_async_result.return_value = mock_task
            
            response = self.client.get(f"{self.base_url}/status/{task_id}")
            
            assert response.status_code == 200
            response_data = response.json()
            
            # Validate required fields
            assert "task_id" in response_data
            assert "status" in response_data
            assert "result" in response_data
            assert "error" in response_data
            
            # Validate types
            assert isinstance(response_data["task_id"], str)
            assert isinstance(response_data["status"], str)
            assert isinstance(response_data["result"], dict) or response_data["result"] is None
            assert isinstance(response_data["error"], str) or response_data["error"] is None
"""
Resume status endpoint for checking task processing status.

This module provides endpoints to check the status of resume parsing tasks,
returning current state and results when available.
"""

import logging
from celery.result import AsyncResult
from fastapi import APIRouter, HTTPException, status

from app.api.v1.models.resumes import ResumeStatusResponse
from app.celery_app import celery_app

# Configure logger
log = logging.getLogger(__name__)

router = APIRouter()


@router.get("/status/{task_id}", response_model=ResumeStatusResponse, status_code=status.HTTP_200_OK)
async def get_resume_status(task_id: str) -> ResumeStatusResponse:
    """
    Get the status of a resume parsing task.
    
    Returns the current status of the background task processing a resume.
    Possible statuses include:
    - PENDING: Task is waiting to be processed
    - SUCCESS: Task completed successfully with results
    - FAILURE: Task failed with error information
    - RETRY: Task is being retried after failure
    - REVOKED: Task was cancelled
    
    Args:
        task_id: The unique identifier for the resume parsing task
        
    Returns:
        ResumeStatusResponse containing the current task status and results/error
        
    Raises:
        HTTPException:
            - 400 Bad Request: Invalid task ID format
            - 404 Not Found: Task ID not found
    """
    if not task_id or not task_id.strip():
        log.warning("Empty task ID provided to status endpoint")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Task ID is required"
        )
    
    try:
        # Get task result from Celery
        task_result = AsyncResult(task_id, app=celery_app)
        
        # Check if task exists
        if task_result.state == 'PENDING' and task_result.result is None:
            # This could mean the task doesn't exist or is actually pending
            # Try to get more info from the backend
            if not task_result.backend.get(task_result.key):
                log.warning(f"Task ID not found: {task_id}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Task not found"
                )
        
        log.info(f"Retrieved status for task {task_id}: {task_result.state}")
        
        # Prepare response based on task state
        response_data = {
            "task_id": task_id,
            "status": task_result.state,
        }
        
        if task_result.state == "SUCCESS":
            response_data["result"] = task_result.result
        elif task_result.state == "FAILURE":
            # Handle task failure
            error_info = str(task_result.info) if task_result.info else "Unknown error occurred"
            response_data["error"] = error_info
        elif task_result.state in ["RETRY", "REVOKED"]:
            # Handle retry or revoked states
            if task_result.info:
                response_data["error"] = str(task_result.info)
        
        return ResumeStatusResponse(**response_data)
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        log.error(f"Unexpected error retrieving task status for {task_id}: {type(e).__name__}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving task status"
        )
from typing import Dict, Optional, Any, Literal
from pydantic import BaseModel, Field


class ResumeUploadResponse(BaseModel):
    """Response model for resume upload endpoint.
    
    Returns a task ID that can be used to check the processing status
    of the uploaded resume file.
    """

    task_id: str = Field(
        ...,
        description="Unique identifier for the resume parsing task",
        example="a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
            }
        }


class ContactInfo(BaseModel):
    """Contact information extracted from resume."""
    
    name: Optional[str] = Field(
        None,
        description="Full name extracted from the resume",
        example="John Doe"
    )
    email: Optional[str] = Field(
        None,
        description="Email address found in the resume",
        example="john.doe@example.com"
    )
    phone: Optional[str] = Field(
        None,
        description="Phone number found in the resume",
        example="(555) 123-4567"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "name": "John Doe",
                "email": "john.doe@example.com",
                "phone": "(555) 123-4567"
            }
        }


class ResumeParsingResult(BaseModel):
    """Detailed results from resume parsing."""
    
    status: Literal["success", "error"] = Field(
        ...,
        description="Processing status of the resume parsing"
    )
    file_type: str = Field(
        ...,
        description="MIME type of the processed file",
        example="application/pdf"
    )
    character_count: int = Field(
        ...,
        description="Number of characters extracted from the resume",
        example=2543
    )
    extracted_text: Optional[str] = Field(
        None,
        description="Full text content extracted from the resume",
        example="John Doe\nSoftware Engineer\nExperience:\n- Python development..."
    )
    contact_info: Optional[ContactInfo] = Field(
        None,
        description="Contact information parsed from the resume"
    )
    error: Optional[str] = Field(
        None,
        description="Error message if parsing failed",
        example="Failed to extract text from PDF: file corrupted"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "file_type": "application/pdf",
                "character_count": 2543,
                "extracted_text": "John Doe\nSoftware Engineer\nEmail: john.doe@example.com\nPhone: (555) 123-4567\n\nExperience:\n- 5 years of Python development\n- FastAPI and Django expertise\n- Database design and optimization",
                "contact_info": {
                    "name": "John Doe",
                    "email": "john.doe@example.com",
                    "phone": "(555) 123-4567"
                }
            }
        }


class ResumeStatusResponse(BaseModel):
    """Response model for resume status endpoint.
    
    Provides the current status of a resume parsing task and results
    when processing is complete.
    """
    
    task_id: str = Field(
        ...,
        description="Unique identifier for the resume parsing task",
        example="a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    )
    status: Literal["PENDING", "SUCCESS", "FAILURE", "RETRY", "REVOKED"] = Field(
        ...,
        description="Current status of the task processing",
        example="SUCCESS"
    )
    result: Optional[ResumeParsingResult] = Field(
        None,
        description="Parsing results when status is SUCCESS"
    )
    error: Optional[str] = Field(
        None,
        description="Error message when status is FAILURE",
        example="Task failed due to corrupted file"
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "description": "Task completed successfully",
                    "value": {
                        "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "status": "SUCCESS",
                        "result": {
                            "status": "success",
                            "file_type": "application/pdf",
                            "character_count": 2543,
                            "contact_info": {
                                "name": "John Doe",
                                "email": "john.doe@example.com",
                                "phone": "(555) 123-4567"
                            }
                        }
                    }
                },
                {
                    "description": "Task still processing",
                    "value": {
                        "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "status": "PENDING"
                    }
                },
                {
                    "description": "Task failed",
                    "value": {
                        "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "status": "FAILURE",
                        "error": "Failed to parse resume: unsupported file format"
                    }
                }
            ]
        }

"""Pydantic models for word processing API responses."""

from pydantic import BaseModel


class Words(BaseModel):
    """Word count response model for text processing operations.
    
    Attributes:
        count: The number of words found in the processed text.
    """
    
    count: int

"""Custom Celery task state definitions.

This module defines custom task states used throughout the application
for enhanced task monitoring and status reporting.
"""


class TaskStates:
    """Custom Celery task state constants.
    
    Attributes:
        PROGRESS: Task is currently in progress and running.
    """
    
    PROGRESS = "PROGRESS"

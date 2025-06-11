from fastapi import APIRouter
from app.api.v1.resumes.upload import router as upload_router
from app.api.v1.resumes.status import router as status_router

# Combine routers for resumes API
router = APIRouter()
router.include_router(upload_router)
router.include_router(status_router)

__all__ = ["router"]

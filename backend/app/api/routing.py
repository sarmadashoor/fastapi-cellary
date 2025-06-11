from app.api.v1.auth import router as auth_router
from app.api.v1.resumes import router as resumes_router
from app.api.v1.root import router as root_router
from app.api.v1.words import router as words_router
from app.api.v1.observability import router as observability_router
from fastapi import APIRouter

TAGS = [
    {
        "name": "tests",
        "description": "Service health and status endpoints for monitoring and testing.",
    },
    {
        "name": "security",
        "description": "Authentication and authorization endpoints using JWT tokens.",
        "externalDocs": {
            "description": "JWT Authentication Guide",
            "url": "https://jwt.io/introduction/",
        },
    },
    {
        "name": "resumes",
        "description": "Resume processing endpoints for file upload, text extraction, and status tracking.",
    },
    {
        "name": "Resume Processing",
        "description": "Complete resume processing workflow including upload, parsing, and result retrieval.",
    },
    {
        "name": "words",
        "description": "Word processing and text analysis endpoints for map-reduce operations.",
    },
    {
        "name": "observability",
        "description": "Application monitoring, health checks, metrics, and observability endpoints.",
    },
]

ROUTE_TABLE = [
    {"router": root_router, "tag": "tests"},
    {"prefix": "/auth", "router": auth_router, "tag": "security"},
    {"prefix": "/words", "router": words_router, "tag": "words"},
    {"prefix": "/resumes", "router": resumes_router, "tag": "resumes"},
    {"prefix": "/observability", "router": observability_router, "tag": "observability"},
]


router = APIRouter()
for route in ROUTE_TABLE:
    if "prefix" in route:
        router.include_router(
            route["router"],
            tags=[route["tag"]],
            prefix=route["prefix"],
        )
    else:
        router.include_router(route["router"], tags=[route["tag"]])

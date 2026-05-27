from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.http.router import router as agents_router
from app.runtime import crewai_available, crewai_version
from app.settings import settings

app = FastAPI(title="yuno", version="0.0.0-batch0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agents_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/system")
def system_info() -> dict[str, object]:
    return {
        "app_env": settings.app_env,
        "crewai": {
            "available": crewai_available(),
            "version": crewai_version(),
        },
        "providers_configured": {
            "gemini": bool(settings.gemini_api_key),
            "anthropic": bool(settings.anthropic_api_key),
            "openai": bool(settings.openai_api_key),
        },
    }

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.http.router import router as agents_router
from app.event_bus import bus
from app.runs.event_bus.subscriber import RunsEventSubscriber
from app.runs.http.router import router as runs_router
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
app.include_router(runs_router)

_runs_subscriber = RunsEventSubscriber()


@app.on_event("startup")
def _wire_runs_subscriber() -> None:
    _runs_subscriber.register(bus)


@app.on_event("shutdown")
def _unwire_runs_subscriber() -> None:
    _runs_subscriber.unregister(bus)


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

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from placebo_api import db
from placebo_api.config import settings
from placebo_api.routes import checkins, experiments, metrics


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_pool(settings.database_url)
    yield
    await db.close_pool()


app = FastAPI(title="Placebo API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(metrics.router)
app.include_router(experiments.router)
app.include_router(checkins.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

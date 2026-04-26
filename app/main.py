from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.session import create_tables
from app.core.redis_manager import manager
from app.routers import auth, channels, messages, websocket, presence, ai, eval


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    await manager.connect_redis()
    yield
    await manager.disconnect_redis()


app = FastAPI(
    title="CollabMind Chat API",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(channels.router)
app.include_router(messages.router)
app.include_router(websocket.router)
app.include_router(presence.router)
app.include_router(ai.router)
app.include_router(eval.router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.2.0"}
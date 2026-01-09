from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.api import auth, confluence, indexes, mcp
from app.database import init_db
from app.config import config
from app.services.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()


app = FastAPI(
    title="MCP Confluence Sync",
    description="API for syncing Confluence pages to LlamaIndex Cloud",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers for different functionalities
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(confluence.router, prefix="/api/confluence", tags=["confluence"])
app.include_router(indexes.router, prefix="/api/indexes", tags=["indexes"])
app.include_router(mcp.router, prefix="/mcp", tags=["mcp"])


@app.get("/")
async def root():
    return {"message": "MCP Confluence Sync API", "status": "running"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.API_HOST, port=config.API_PORT)
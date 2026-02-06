"""FastAPI application factory for h-mem Web UI."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from strawberry.fastapi import GraphQLRouter

from hmem.api.graphql.schema import schema


def create_app(dev: bool = False) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        dev: Enable development mode (CORS + GraphiQL)

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="h-mem Web UI",
        description="Cognitive Agent Memory System - Web Interface",
        version="0.1.0",
    )

    # Configure CORS for development
    if dev:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Mount GraphQL endpoint
    graphql_app = GraphQLRouter(
        schema,
        graphql_ide="graphiql" if dev else None,
    )
    app.include_router(graphql_app, prefix="/graphql")

    # Try to serve static files from built frontend
    # First check for bundled static files in api/static (for pip install)
    # Then check for dev build in web/dist
    static_dir = Path(__file__).parent / "static"
    if not static_dir.exists():
        # Fall back to web/dist for development
        static_dir = Path(__file__).parent.parent / "web" / "dist"

    if static_dir.exists():
        # Serve static assets
        app.mount(
            "/assets", StaticFiles(directory=static_dir / "assets"), name="assets"
        )

        # Serve index.html for SPA routing
        @app.get("/")
        async def serve_root() -> FileResponse:
            return FileResponse(static_dir / "index.html")

        @app.get("/{path:path}")
        async def serve_spa(path: str) -> FileResponse:
            # Check if it's a static file
            file_path = static_dir / path
            if file_path.exists() and file_path.is_file():
                return FileResponse(file_path)
            # Otherwise serve index.html for SPA routing
            return FileResponse(static_dir / "index.html")

    @app.get("/health")
    async def health() -> dict:
        """Health check endpoint."""
        return {"status": "ok", "service": "h-mem"}

    return app

"""FastAPI application for reading stored opportunities."""
from contextlib import asynccontextmanager
from pathlib import Path
import sqlite3
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .store import OpportunityStore


class OpportunityResponse(BaseModel):
    id: int
    title: str
    organization: str
    category: str
    location: str
    description: str
    eligibility: str
    deadline: str
    application_url: str
    source_name: str


class HealthResponse(BaseModel):
    status: str
    database: str


def _response(row: sqlite3.Row) -> OpportunityResponse:
    return OpportunityResponse(**dict(row))


def create_app(db_path: Path | str = Path("data/opportunities.sqlite3")) -> FastAPI:
    """Create the API app using the CLI's default database path unless overridden."""
    database_path = Path(db_path)
    static_path = Path(__file__).resolve().parent / "static"

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        store = OpportunityStore(database_path)
        app.state.opportunity_store = store
        try:
            yield
        finally:
            store.close()

    app = FastAPI(title="Opportunity Radar API", version="0.1.0", lifespan=lifespan)

    @app.get("/", include_in_schema=False)
    async def homepage() -> FileResponse:
        return FileResponse(static_path / "index.html")

    @app.get("/health", response_model=HealthResponse)
    async def health(request: Request) -> HealthResponse:
        store: OpportunityStore = request.app.state.opportunity_store
        if not store.check_health():
            raise HTTPException(status_code=503, detail="Database unavailable")
        return HealthResponse(status="ok", database="ok")

    @app.get("/api/opportunities", response_model=list[OpportunityResponse])
    async def list_opportunities(
        request: Request,
        q: str = Query(default="", description="Search title, organization, description, and eligibility"),
        category: str = Query(default=""),
        location: str = Query(default=""),
        company: str = Query(default=""),
    ) -> list[OpportunityResponse]:
        store: OpportunityStore = request.app.state.opportunity_store
        rows = store.search(query=q, category=category, location=location, company=company)
        return [_response(row) for row in rows]

    @app.get("/api/opportunities/{opportunity_id}", response_model=OpportunityResponse)
    async def get_opportunity(
        opportunity_id: int, request: Request
    ) -> OpportunityResponse:
        store: OpportunityStore = request.app.state.opportunity_store
        row = store.get_by_id(opportunity_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Opportunity not found")
        return _response(row)

    app.mount("/static", StaticFiles(directory=static_path), name="static")
    return app


app = create_app()

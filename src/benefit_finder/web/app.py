"""FastAPI application for benefit-finder.

Endpoints
  GET  /                read the intake wizard / dashboard single-page app
  GET  /api/meta        enums, labels, and disclaimers for the frontend
  POST /api/screen      profile JSON in, structured results JSON out
  POST /api/report      profile JSON in, markdown report out
  GET  /api/report      same, profile passed as a JSON query parameter

Privacy. The server holds the posted profile only for the duration of
the request to compute a result. It is never written to disk, logged,
or stored. There is no database and no logging of request bodies.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from ..core import screen_household
from ..models import ProfileError
from ..report import generate_report
from .schemas import (
    MetaResponse,
    ProfileIn,
    ScreenResponse,
    build_meta,
    build_screen_response,
)

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="benefit-finder",
    description=(
        "Screen a US household for public benefits, assistance programs, and "
        "tax credits. Static rules engine, no database, no server-side "
        "storage of household data."
    ),
    version="0.1.0",
)


@app.exception_handler(ProfileError)
async def _profile_error_handler(request: Request, exc: ProfileError) -> JSONResponse:
    # A bad-but-well-formed profile (unknown flag, invalid enum, non-finite
    # AGI) is a client error, not a server crash.
    return JSONResponse(status_code=422, content={"detail": str(exc)})


def _household_from(payload: ProfileIn):
    return payload.to_household()


@app.get("/api/meta", response_model=MetaResponse)
def get_meta() -> MetaResponse:
    return build_meta()


@app.post("/api/screen", response_model=ScreenResponse)
def post_screen(payload: ProfileIn) -> ScreenResponse:
    household = _household_from(payload)
    evaluations = screen_household(household)
    return build_screen_response(evaluations, household)


def _report_markdown(payload: ProfileIn) -> str:
    household = _household_from(payload)
    evaluations = screen_household(household)
    return generate_report(evaluations, household)


@app.post("/api/report", response_class=PlainTextResponse)
def post_report(payload: ProfileIn) -> PlainTextResponse:
    return PlainTextResponse(_report_markdown(payload), media_type="text/markdown")


@app.get("/api/report", response_class=PlainTextResponse)
def get_report(
    profile: str = Query(..., description="URL-encoded profile JSON")
) -> PlainTextResponse:
    try:
        data = json.loads(profile)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"profile is not valid JSON ({exc})")
    try:
        payload = ProfileIn.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=json.loads(exc.json()))
    return PlainTextResponse(_report_markdown(payload), media_type="text/markdown")


# ---- static single-page app (mounted last so /api/* wins) ----

@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

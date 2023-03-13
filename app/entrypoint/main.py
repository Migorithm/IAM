from uuid import uuid4
from fastapi import FastAPI, Request
from app.entrypoint.middleware import request as ctx_request, db

app = FastAPI(
    title="iam_service Server",
    description="",
    version="2.0",
    docs_url=None,
    redoc_url=None,
)


@app.middleware("http")
async def add_middleware(request: Request, call_next):
    token = ctx_request.set(request)
    session_id = uuid4()
    db_token = db.set(session_id)
    response = await call_next(request)
    db.reset(db_token)

    ctx_request.reset(token)
    return response

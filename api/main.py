"""Search over the alert queue, and a socket carrying alerts as they are raised."""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from typing import Annotated

import pandas as pd
from fastapi import Depends, FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from redis import Redis
from sqlalchemy.orm import Session

from api.broadcast import Broadcaster
from api.config import (
    ALLOWED_ORIGINS,
    MAX_PAGE_LIMIT,
    PAGE_LIMIT,
    REPLAY_DAYS,
    REPLAY_START,
    RUN_CONSUMER,
    RUN_REPLAY,
)
from api.deps import get_session
from api.schemas import AlertOut, AlertPage, Summary
from db.alerts import recent, summary
from stream.config import REDIS_URL

log = logging.getLogger(__name__)

broadcaster = Broadcaster()

Queue = Annotated[Session, Depends(get_session)]


def _run_consumer() -> None:
    from stream.consumer import consume, load_scorer
    from stream.sinks import DatabaseAlertSink, RedisAlertSink

    client = Redis.from_url(REDIS_URL)
    consume(client, load_scorer(client), "api", [RedisAlertSink(client), DatabaseAlertSink()])


def _run_replay() -> None:
    from ingest.prepare import load_table
    from stream.producer import replay, timeline
    from stream.warmup import warm

    client = Redis.from_url(REDIS_URL)
    table = load_table()
    start = pd.Timestamp(REPLAY_START)

    warm(client, table, start)
    window = table[
        (table.tx_datetime >= start) & (table.tx_datetime < start + pd.Timedelta(days=REPLAY_DAYS))
    ]
    replay(client, timeline(window))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await broadcaster.start()
    workers = []
    if RUN_CONSUMER:
        workers.append(threading.Thread(target=_run_consumer, daemon=True))
    if RUN_REPLAY:
        workers.append(threading.Thread(target=_run_replay, daemon=True))
    for worker in workers:
        worker.start()
    try:
        yield
    finally:
        await broadcaster.stop()


app = FastAPI(title="Fraud Stream Detection", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "HEAD", "OPTIONS"],
    allow_headers=["*"],
)


@app.api_route("/", methods=["GET", "HEAD"])
def root() -> dict:
    return {"service": "fraud-stream-detection", "watchers": len(broadcaster.clients)}


@app.get("/alerts", response_model=AlertPage)
def alerts(
    session: Queue,
    limit: int = Query(PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    before: int | None = Query(None, ge=1),
) -> AlertPage:
    rows = recent(session, limit, before)
    page = [AlertOut.model_validate(row) for row in rows]
    # The cursor is the last id of the page, so a new alert cannot shift the next one.
    return AlertPage(alerts=page, next_before=page[-1].id if len(page) == limit else None)


@app.get("/stats", response_model=Summary)
def stats(session: Queue) -> Summary:
    return Summary(**summary(session))


@app.websocket("/live")
async def live(socket: WebSocket) -> None:
    await socket.accept()
    broadcaster.register(socket)
    try:
        while True:
            # The client sends nothing; the receive is what notices it left.
            await socket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        broadcaster.unregister(socket)

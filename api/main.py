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
    LOG_LEVEL,
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


def configure_logging() -> None:
    """Uvicorn configures its own loggers and leaves the root one without a handler,
    so every startup line a module writes would otherwise go nowhere."""
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
        root.addHandler(handler)
    root.setLevel(LOG_LEVEL)
    # These log a line per request at INFO, which buries the lines that carry
    # information about this service.
    for noisy in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


configure_logging()

broadcaster = Broadcaster()

Queue = Annotated[Session, Depends(get_session)]


def _run_consumer() -> None:
    from stream.consumer import consume, load_scorer
    from stream.sinks import DatabaseAlertSink, RedisAlertSink

    client = Redis.from_url(REDIS_URL)
    consume(client, load_scorer(client), "api", [RedisAlertSink(client), DatabaseAlertSink()])


def _run_replay() -> None:
    from ingest.source import replay_slice
    from stream.consumer import ensure_group
    from stream.producer import replay, timeline
    from stream.warmup import warm

    client = Redis.from_url(REDIS_URL)
    # Created before the first event, so the producer can measure how far behind
    # the consumer is from the start rather than racing it.
    ensure_group(client)
    start = pd.Timestamp(REPLAY_START)
    table = replay_slice(start, REPLAY_DAYS)

    warm(client, table, start)
    replay(client, timeline(table[table.tx_datetime >= start]))


def _supervised(work) -> None:
    """A worker thread that dies silently leaves the API serving a queue that has
    stopped filling, so its failure is reported rather than swallowed."""
    try:
        work()
    except Exception:
        log.exception("%s stopped", work.__name__)
    else:
        log.info("%s finished", work.__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await broadcaster.start()
    workers = []
    if RUN_CONSUMER:
        workers.append(threading.Thread(target=_supervised, args=(_run_consumer,), daemon=True))
    if RUN_REPLAY:
        workers.append(threading.Thread(target=_supervised, args=(_run_replay,), daemon=True))
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

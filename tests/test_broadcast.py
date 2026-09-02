from __future__ import annotations

import pytest

from api.broadcast import Broadcaster


class FakeSocket:
    def __init__(self, fails: bool = False) -> None:
        self.fails = fails
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        if self.fails:
            raise RuntimeError("socket closed")
        self.sent.append(payload)


@pytest.mark.anyio
async def test_an_alert_reaches_every_watcher():
    broadcaster = Broadcaster()
    first, second = FakeSocket(), FakeSocket()
    broadcaster.register(first)
    broadcaster.register(second)

    await broadcaster.publish({"transaction_id": "1"})

    assert first.sent == second.sent == [{"transaction_id": "1"}]


@pytest.mark.anyio
async def test_a_closed_socket_is_dropped_rather_than_retried():
    broadcaster = Broadcaster()
    healthy, broken = FakeSocket(), FakeSocket(fails=True)
    broadcaster.register(healthy)
    broadcaster.register(broken)

    await broadcaster.publish({"transaction_id": "1"})

    assert broken not in broadcaster.clients
    assert healthy in broadcaster.clients


@pytest.mark.anyio
async def test_stopping_a_broadcaster_that_never_started_is_harmless():
    await Broadcaster().stop()


def test_unregistering_an_unknown_socket_is_harmless():
    Broadcaster().unregister(FakeSocket())

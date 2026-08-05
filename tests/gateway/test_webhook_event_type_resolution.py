"""Event-type resolution tests for the generic webhook adapter.

The adapter derives ``event_type`` from a fixed precedence chain of headers and
payload keys, then uses it to apply a route's ``events:`` allow-list. Providers
that send no event header and use a non-standard payload key (notably Jira
Cloud, which sends ``webhookEvent``) previously resolved to ``"unknown"`` and
were silently dropped by any route filter.

These tests pin the *contract* of that chain — the relative precedence and the
accepted keys — rather than a snapshot of any single payload shape.
"""

import asyncio
import hashlib
import hmac
import json

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import MessageEvent
from gateway.platforms.webhook import WebhookAdapter


def _make_adapter(routes) -> WebhookAdapter:
    config = PlatformConfig(
        enabled=True,
        extra={"host": "0.0.0.0", "port": 0, "routes": routes},
    )
    return WebhookAdapter(config)


def _create_app(adapter: WebhookAdapter) -> web.Application:
    app = web.Application()
    app.router.add_post("/webhooks/{route_name}", adapter._handle_webhook)
    return app


SECRET = "event-type-test-secret"


def _signature(body: bytes) -> str:
    """Compute the generic X-Webhook-Signature for *body*."""
    return hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


async def _post(payload, *, allowed_events, headers=None, raw_body=None):
    """POST *payload* to a signed route and return (status, json, events).

    ``allowed_events`` becomes the route's ``events:`` filter, so the returned
    JSON tells us which ``event_type`` the adapter resolved: an accepted
    delivery echoes it back under ``"event"``, an ignored one does the same
    with ``status == "ignored"``.
    """
    routes = {
        "r": {
            "secret": SECRET,
            "events": allowed_events,
            "prompt": "handled {x}",
            "deliver": "log",
        }
    }
    adapter = _make_adapter(routes)
    captured: list[MessageEvent] = []

    async def _capture(event: MessageEvent):
        captured.append(event)

    adapter.handle_message = _capture
    app = _create_app(adapter)
    body = raw_body if raw_body is not None else json.dumps(payload).encode()

    async with TestClient(TestServer(app)) as cli:
        resp = await cli.post(
            "/webhooks/r",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": _signature(body),
                **(headers or {}),
            },
        )
        data = await resp.json()
        status = resp.status
    await asyncio.sleep(0.05)
    return status, data, captured


@pytest.mark.asyncio
async def test_explicit_event_type_key_is_used():
    """``payload.event_type`` resolves the event when no header is present."""
    status, data, captured = await _post(
        {"event_type": "message.received", "x": 1},
        allowed_events=["message.received"],
    )
    assert status == 202
    assert data["event"] == "message.received"
    assert len(captured) == 1


@pytest.mark.asyncio
async def test_payload_type_key_is_used():
    """``payload.type`` resolves the event when ``event_type`` is absent."""
    status, data, captured = await _post(
        {"type": "ticket.created", "x": 1},
        allowed_events=["ticket.created"],
    )
    assert status == 202
    assert data["event"] == "ticket.created"
    assert len(captured) == 1


@pytest.mark.asyncio
async def test_payload_event_key_is_used():
    """A bare ``payload.event`` key resolves the event type."""
    status, data, captured = await _post(
        {"event": "push", "x": 1},
        allowed_events=["push"],
    )
    assert status == 202
    assert data["event"] == "push"
    assert len(captured) == 1


@pytest.mark.asyncio
async def test_jira_webhook_event_key_is_used():
    """Jira Cloud's ``webhookEvent`` resolves the event type.

    Jira sends no event header and neither ``event_type``, ``type`` nor
    ``event`` — without this the route filter drops every Jira delivery.
    """
    status, data, captured = await _post(
        {"webhookEvent": "jira:issue_updated", "issue": {"key": "PPE-5"}, "x": 1},
        allowed_events=["jira:issue_updated"],
    )
    assert status == 202
    assert data["event"] == "jira:issue_updated"
    assert len(captured) == 1


@pytest.mark.asyncio
async def test_header_wins_over_all_payload_keys():
    """An event header outranks every payload key (precedence unchanged)."""
    payload = {
        "event_type": "from_event_type",
        "type": "from_type",
        "event": "from_event",
        "webhookEvent": "from_webhook_event",
        "x": 1,
    }
    status, data, _ = await _post(
        payload,
        allowed_events=["pull_request"],
        headers={"X-GitHub-Event": "pull_request"},
    )
    assert status == 202
    assert data["event"] == "pull_request"


@pytest.mark.asyncio
async def test_event_type_outranks_type_event_and_webhook_event():
    """``event_type`` outranks ``type``, ``event`` and ``webhookEvent``."""
    payload = {
        "event_type": "from_event_type",
        "type": "from_type",
        "event": "from_event",
        "webhookEvent": "from_webhook_event",
        "x": 1,
    }
    status, data, _ = await _post(payload, allowed_events=["from_event_type"])
    assert status == 202
    assert data["event"] == "from_event_type"


@pytest.mark.asyncio
async def test_type_outranks_event_and_webhook_event():
    """``type`` outranks the two newly accepted keys."""
    payload = {
        "type": "from_type",
        "event": "from_event",
        "webhookEvent": "from_webhook_event",
        "x": 1,
    }
    status, data, _ = await _post(payload, allowed_events=["from_type"])
    assert status == 202
    assert data["event"] == "from_type"


@pytest.mark.asyncio
async def test_event_outranks_webhook_event():
    """``event`` is checked before ``webhookEvent``."""
    payload = {"event": "from_event", "webhookEvent": "from_webhook_event", "x": 1}
    status, data, _ = await _post(payload, allowed_events=["from_event"])
    assert status == 202
    assert data["event"] == "from_event"


@pytest.mark.asyncio
async def test_non_matching_event_is_still_filtered():
    """Resolution does not weaken the allow-list: a mismatch is ignored."""
    status, data, captured = await _post(
        {"webhookEvent": "jira:issue_deleted", "x": 1},
        allowed_events=["jira:issue_updated"],
    )
    assert status == 200
    assert data["status"] == "ignored"
    assert data["event"] == "jira:issue_deleted"
    assert captured == []


@pytest.mark.asyncio
async def test_payload_without_any_event_key_resolves_unknown():
    """With no header and no recognised key the event stays ``unknown``."""
    status, data, captured = await _post(
        {"issue": {"key": "PPE-5"}, "x": 1},
        allowed_events=["jira:issue_updated"],
    )
    assert status == 200
    assert data["status"] == "ignored"
    assert data["event"] == "unknown"
    assert captured == []


@pytest.mark.asyncio
async def test_non_string_webhook_event_does_not_crash():
    """A malformed (non-string) value must not raise out of the handler."""
    status, data, _ = await _post(
        {"webhookEvent": {"nested": "object"}, "x": 1},
        allowed_events=["jira:issue_updated"],
    )
    assert status in (200, 202, 400)


@pytest.mark.asyncio
async def test_invalid_json_body_does_not_fabricate_an_event():
    """A body that is not JSON must never resolve to a filtered event.

    The adapter tolerates non-JSON bodies (they become a raw text payload),
    so the contract here is not the status code but that no event key can be
    conjured out of an unparseable body: the route filter rejects it and the
    agent is never invoked.
    """
    status, data, captured = await _post(
        None,
        allowed_events=["jira:issue_updated"],
        raw_body=b"{not json",
    )
    assert status != 202
    assert data.get("event") != "jira:issue_updated"
    assert captured == []

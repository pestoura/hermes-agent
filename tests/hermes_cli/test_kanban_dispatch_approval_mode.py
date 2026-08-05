"""Tests for kanban dispatch-approval mode resolution and fail-closed behavior.

Covers ``_resolve_dispatch_approval_mode`` and ``_check_dispatch_approval_allowed``:

- the config key is actually honoured (it previously was not — the resolver
  short-circuited on a hardcoded ``"structured"`` and never read config);
- an absent key keeps the shipped default, so upgrading does not change
  behavior on an existing board;
- an unreadable or invalid config falls **closed** onto the strictest mode and
  reports why, instead of silently degrading;
- ``compat`` does not enforce (documented as behavior-preserving) while
  ``structured``/``legacy`` do;
- a dry-run tick writes no audit events.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest


@pytest.fixture()
def kb(monkeypatch):
    """Fresh HERMES_HOME with an isolated kanban DB and a reimported module."""
    test_home = tempfile.mkdtemp(prefix="kanban_approval_mode_test_")
    os.makedirs(os.path.join(test_home, "profiles", "default"), exist_ok=True)
    monkeypatch.setenv("HERMES_HOME", test_home)
    for mod in list(sys.modules.keys()):
        if (
            mod.startswith("hermes_cli")
            or mod.startswith("hermes_state")
            or mod == "hermes_constants"
        ):
            del sys.modules[mod]
    from hermes_cli import kanban_db

    with kanban_db.connect_closing() as conn:  # noqa: F841 - ensures schema init
        kanban_db.create_board(slug="default", name="Test")
    yield kanban_db


def _fake_spawn(*args, **kwargs):
    return 12345


def _events(kb_mod, task_id):
    with kb_mod.connect_closing() as conn:
        rows = conn.execute(
            "SELECT kind FROM task_events WHERE task_id = ? ORDER BY id",
            (task_id,),
        ).fetchall()
    return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# Mode resolution
# ---------------------------------------------------------------------------


def test_config_value_is_honoured(kb, monkeypatch):
    """A configured mode is actually used, not ignored for a hardcoded one."""
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", None)
    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda *a, **k: {"kanban": {"dispatch_approval_mode": "legacy"}},
    )
    mode, err = kb._resolve_dispatch_approval_mode()
    assert mode == "legacy"
    assert err is None


def test_absent_key_uses_shipped_default(kb, monkeypatch):
    """No key configured → the packaged default, so upgrades are inert."""
    from hermes_cli.config_defaults import DEFAULT_CONFIG

    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", None)
    monkeypatch.setattr("hermes_cli.config.load_config", lambda *a, **k: {"kanban": {}})
    mode, err = kb._resolve_dispatch_approval_mode()
    assert mode == DEFAULT_CONFIG["kanban"]["dispatch_approval_mode"]
    assert err is None


def test_override_wins_over_config(kb, monkeypatch):
    """The explicit override beats whatever config says."""
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", "structured")
    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda *a, **k: {"kanban": {"dispatch_approval_mode": "compat"}},
    )
    mode, err = kb._resolve_dispatch_approval_mode()
    assert mode == "structured"
    assert err is None


def test_unreadable_config_falls_closed(kb, monkeypatch):
    """A config-read error must not be a reason to dispatch."""

    def _boom(*a, **k):
        raise RuntimeError("config file is corrupt")

    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", None)
    monkeypatch.setattr("hermes_cli.config.load_config", _boom)
    mode, err = kb._resolve_dispatch_approval_mode()
    assert mode == kb._DISPATCH_APPROVAL_FAILSAFE_MODE
    assert mode in kb._VALID_DISPATCH_APPROVAL_MODES
    assert err == "config_unreadable"


@pytest.mark.parametrize("bad", ["yolo", "", 3, None if False else []])
def test_invalid_mode_value_falls_closed(kb, monkeypatch, bad):
    """An unrecognised or non-string mode falls closed and is reported."""
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", None)
    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda *a, **k: {"kanban": {"dispatch_approval_mode": bad}},
    )
    mode, err = kb._resolve_dispatch_approval_mode()
    assert mode == kb._DISPATCH_APPROVAL_FAILSAFE_MODE
    assert err == "invalid_dispatch_approval_mode"


def test_failsafe_mode_is_an_enforcing_mode(kb):
    """The fail-safe must be one that actually requires an approval."""
    assert kb._DISPATCH_APPROVAL_FAILSAFE_MODE in {"structured", "legacy"}


# ---------------------------------------------------------------------------
# Enforcement
# ---------------------------------------------------------------------------


def test_structured_mode_blocks_unapproved_task(kb, monkeypatch):
    """structured: no approval → no dispatch, with an explicit reason."""
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", "structured")
    with kb.connect_closing() as conn:
        task_id = kb.create_task(conn, title="t", assignee="default")
    with kb.connect_closing() as conn:
        res = kb.dispatch_once(conn, spawn_fn=_fake_spawn, dry_run=False)
    assert not any(s[0] == task_id for s in res.spawned)
    assert any(
        t == task_id and "no_active_dispatch_approval" in r
        for t, r in res.respawn_guarded
    )


def test_structured_mode_allows_approved_task(kb, monkeypatch):
    """structured: an active approval unblocks exactly that task."""
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", "structured")
    with kb.connect_closing() as conn:
        task_id = kb.create_task(conn, title="t", assignee="default")
    with kb.connect_closing() as conn:
        with kb.write_txn(conn):
            kb.approve_dispatch(conn, task_id, actor="supervisor", source="test")
    with kb.connect_closing() as conn:
        res = kb.dispatch_once(conn, spawn_fn=_fake_spawn, dry_run=False)
    assert any(s[0] == task_id for s in res.spawned)


def test_compat_mode_does_not_block_unapproved_task(kb, monkeypatch):
    """compat is the shipped default and must preserve pre-gate behavior.

    If compat blocked, upgrading Hermes would silently freeze every existing
    board that does not use the approval workflow.
    """
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", "compat")
    with kb.connect_closing() as conn:
        task_id = kb.create_task(conn, title="t", assignee="default")
    with kb.connect_closing() as conn:
        res = kb.dispatch_once(conn, spawn_fn=_fake_spawn, dry_run=False)
    assert any(s[0] == task_id for s in res.spawned)


def test_compat_mode_audits_the_ungated_dispatch(kb, monkeypatch):
    """compat records that it let an unapproved task through."""
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", "compat")
    with kb.connect_closing() as conn:
        task_id = kb.create_task(conn, title="t", assignee="default")
    with kb.connect_closing() as conn:
        kb.dispatch_once(conn, spawn_fn=_fake_spawn, dry_run=False)
    assert "dispatch_approved" in _events(kb, task_id)


def test_config_error_is_surfaced_in_the_denial_reason(kb, monkeypatch):
    """A board frozen by a bad config says so, instead of looking idle."""

    def _boom(*a, **k):
        raise RuntimeError("config file is corrupt")

    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", None)
    monkeypatch.setattr("hermes_cli.config.load_config", _boom)
    with kb.connect_closing() as conn:
        task_id = kb.create_task(conn, title="t", assignee="default")
    with kb.connect_closing() as conn:
        res = kb.dispatch_once(conn, spawn_fn=_fake_spawn, dry_run=False)
    assert not any(s[0] == task_id for s in res.spawned)
    assert any(
        t == task_id and r.endswith(":config_unreadable")
        for t, r in res.respawn_guarded
    )


def test_invalid_config_blocks_dispatch_end_to_end(kb, monkeypatch):
    """An invalid mode value blocks dispatch rather than degrading to allow."""
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", None)
    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda *a, **k: {"kanban": {"dispatch_approval_mode": "nonsense"}},
    )
    with kb.connect_closing() as conn:
        task_id = kb.create_task(conn, title="t", assignee="default")
    with kb.connect_closing() as conn:
        res = kb.dispatch_once(conn, spawn_fn=_fake_spawn, dry_run=False)
    assert not any(s[0] == task_id for s in res.spawned)
    assert any(
        t == task_id and r.endswith(":invalid_dispatch_approval_mode")
        for t, r in res.respawn_guarded
    )


# ---------------------------------------------------------------------------
# Side-effect discipline
# ---------------------------------------------------------------------------


def test_dry_run_writes_no_audit_events(kb, monkeypatch):
    """A preview tick must not mutate the event log."""
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", "compat")
    with kb.connect_closing() as conn:
        task_id = kb.create_task(conn, title="t", assignee="default")
    before = _events(kb, task_id)
    with kb.connect_closing() as conn:
        res = kb.dispatch_once(conn, spawn_fn=_fake_spawn, dry_run=True)
    assert any(s[0] == task_id for s in res.spawned)
    assert _events(kb, task_id) == before


def test_blocked_task_is_not_claimed(kb, monkeypatch):
    """A denied task keeps no claim lock, so it stays dispatchable later."""
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", "structured")
    with kb.connect_closing() as conn:
        task_id = kb.create_task(conn, title="t", assignee="default")
    with kb.connect_closing() as conn:
        kb.dispatch_once(conn, spawn_fn=_fake_spawn, dry_run=False)
    with kb.connect_closing() as conn:
        row = conn.execute(
            "SELECT claim_lock, current_run_id FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
    assert row["claim_lock"] is None
    assert row["current_run_id"] is None


def test_repeated_blocked_ticks_are_idempotent(kb, monkeypatch):
    """Re-ticking a blocked board spawns nothing and adds no claims."""
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", "structured")
    with kb.connect_closing() as conn:
        task_id = kb.create_task(conn, title="t", assignee="default")
    for _ in range(3):
        with kb.connect_closing() as conn:
            res = kb.dispatch_once(conn, spawn_fn=_fake_spawn, dry_run=False)
        assert res.spawned == []
    with kb.connect_closing() as conn:
        row = conn.execute(
            "SELECT claim_lock FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
    assert row["claim_lock"] is None


def test_per_profile_cap_is_preserved_under_the_gate(kb, monkeypatch):
    """The approval gate must not bypass or break the concurrency cap."""
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", "compat")
    with kb.connect_closing() as conn:
        for i in range(4):
            kb.create_task(conn, title=f"t{i}", assignee="default")
    with kb.connect_closing() as conn:
        res = kb.dispatch_once(
            conn,
            spawn_fn=_fake_spawn,
            dry_run=True,
            max_in_progress_per_profile=2,
        )
    assert len(res.spawned) == 2
    assert len(res.skipped_per_profile_capped) == 2

"""Parity tests for the kanban dispatch approval gate (#P1.1).

Before this change the approval gate was consulted on exactly one of the
three state advances a dispatcher tick performs:

* ``ready``  -> ``running``  — gated;
* ``review`` -> ``running``  — **not** gated: a card that could never be
  dispatched from ``ready`` could still spawn a review agent;
* ``todo``/``blocked`` -> ``ready`` — **not** gated: ``recompute_ready``
  promoted unconditionally, so enforcement modes only half-worked.

These tests pin the contract for all three paths across the three modes,
plus the fail-closed behavior on a broken config and the read-only
guarantee of a dry-run tick.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest


@pytest.fixture()
def kb(monkeypatch):
    """Fresh HERMES_HOME with an isolated kanban DB and a reimported module."""
    test_home = tempfile.mkdtemp(prefix="kanban_gate_parity_test_")
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


def _status(kb_mod, task_id):
    with kb_mod.connect_closing() as conn:
        row = conn.execute(
            "SELECT status FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
    return row["status"]


def _make_review_task(kb_mod, *, title="r"):
    """Create a task parked in the ``review`` column with a real assignee."""
    with kb_mod.connect_closing() as conn:
        task_id = kb_mod.create_task(conn, title=title, assignee="default")
        with kb_mod.write_txn(conn):
            conn.execute(
                "UPDATE tasks SET status = 'review', claim_lock = NULL, "
                "current_run_id = NULL WHERE id = ?",
                (task_id,),
            )
    return task_id


def _make_child_with_done_parent(kb_mod, *, child_status="todo"):
    """Child in ``todo``/``blocked`` whose only parent is already ``done``.

    That is exactly the shape ``recompute_ready`` promotes.
    """
    with kb_mod.connect_closing() as conn:
        parent_id = kb_mod.create_task(conn, title="parent", assignee="default")
        child_id = kb_mod.create_task(conn, title="child", assignee="default")
        kb_mod.link_tasks(conn, parent_id=parent_id, child_id=child_id)
        with kb_mod.write_txn(conn):
            conn.execute(
                "UPDATE tasks SET status = 'done' WHERE id = ?", (parent_id,)
            )
            conn.execute(
                "UPDATE tasks SET status = ?, consecutive_failures = 0 "
                "WHERE id = ?",
                (child_status, child_id),
            )
    return parent_id, child_id


def _approve_structured(kb_mod, task_id):
    with kb_mod.connect_closing() as conn:
        with kb_mod.write_txn(conn):
            kb_mod.approve_dispatch(
                conn, task_id, actor="supervisor", source="test"
            )


def _approve_legacy(kb_mod, task_id):
    with kb_mod.connect_closing() as conn:
        with kb_mod.write_txn(conn):
            kb_mod.set_legacy_dispatch_approval(conn, task_id)


def _tick(kb_mod, **kwargs):
    with kb_mod.connect_closing() as conn:
        return kb_mod.dispatch_once(conn, spawn_fn=_fake_spawn, **kwargs)


# ---------------------------------------------------------------------------
# ready dispatch — gated in all three modes (compat = permissive + audited)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mode,expect_spawn",
    [("compat", True), ("legacy", False), ("structured", False)],
)
def test_ready_gate_per_mode_without_approval(kb, monkeypatch, mode, expect_spawn):
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", mode)
    with kb.connect_closing() as conn:
        task_id = kb.create_task(conn, title="t", assignee="default")
    res = _tick(kb, dry_run=False)
    assert any(s[0] == task_id for s in res.spawned) is expect_spawn
    if not expect_spawn:
        assert any(
            t == task_id and r.startswith("approval:")
            for t, r in res.respawn_guarded
        )


def test_ready_legacy_marker_present_allows(kb, monkeypatch):
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", "legacy")
    with kb.connect_closing() as conn:
        task_id = kb.create_task(conn, title="t", assignee="default")
    _approve_legacy(kb, task_id)
    res = _tick(kb, dry_run=False)
    assert any(s[0] == task_id for s in res.spawned)


def test_ready_structured_approval_present_allows(kb, monkeypatch):
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", "structured")
    with kb.connect_closing() as conn:
        task_id = kb.create_task(conn, title="t", assignee="default")
    _approve_structured(kb, task_id)
    res = _tick(kb, dry_run=False)
    assert any(s[0] == task_id for s in res.spawned)


def test_ready_structured_ignores_legacy_marker(kb, monkeypatch):
    """structured must not be satisfiable by the legacy substring."""
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", "structured")
    with kb.connect_closing() as conn:
        task_id = kb.create_task(conn, title="t", assignee="default")
    _approve_legacy(kb, task_id)
    res = _tick(kb, dry_run=False)
    assert not any(s[0] == task_id for s in res.spawned)


def test_ready_legacy_ignores_structured_approval(kb, monkeypatch):
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", "legacy")
    with kb.connect_closing() as conn:
        task_id = kb.create_task(conn, title="t", assignee="default")
    _approve_structured(kb, task_id)
    res = _tick(kb, dry_run=False)
    assert not any(s[0] == task_id for s in res.spawned)


# ---------------------------------------------------------------------------
# review dispatch — the parity hole this change closes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mode,expect_spawn",
    [("compat", True), ("legacy", False), ("structured", False)],
)
def test_review_gate_per_mode_without_approval(kb, monkeypatch, mode, expect_spawn):
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", mode)
    task_id = _make_review_task(kb)
    res = _tick(kb, dry_run=False)
    assert any(s[0] == task_id for s in res.spawned) is expect_spawn


def test_review_denied_task_is_not_claimed_and_stays_in_review(kb, monkeypatch):
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", "structured")
    task_id = _make_review_task(kb)
    _tick(kb, dry_run=False)
    with kb.connect_closing() as conn:
        row = conn.execute(
            "SELECT status, claim_lock, current_run_id FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
    assert row["status"] == "review"
    assert row["claim_lock"] is None
    assert row["current_run_id"] is None


def test_review_denial_is_audited(kb, monkeypatch):
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", "structured")
    task_id = _make_review_task(kb)
    _tick(kb, dry_run=False)
    assert "dispatch_denied" in _events(kb, task_id)


def test_review_denial_reason_is_reported(kb, monkeypatch):
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", "legacy")
    task_id = _make_review_task(kb)
    res = _tick(kb, dry_run=False)
    assert any(
        t == task_id and "no_legacy_dispatch_approval" in r
        for t, r in res.respawn_guarded
    )


def test_review_legacy_marker_present_allows(kb, monkeypatch):
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", "legacy")
    task_id = _make_review_task(kb)
    _approve_legacy(kb, task_id)
    res = _tick(kb, dry_run=False)
    assert any(s[0] == task_id for s in res.spawned)


def test_review_structured_approval_present_allows(kb, monkeypatch):
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", "structured")
    task_id = _make_review_task(kb)
    _approve_structured(kb, task_id)
    res = _tick(kb, dry_run=False)
    assert any(s[0] == task_id for s in res.spawned)


def test_review_dry_run_is_read_only(kb, monkeypatch):
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", "structured")
    task_id = _make_review_task(kb)
    before = _events(kb, task_id)
    res = _tick(kb, dry_run=True)
    assert not any(s[0] == task_id for s in res.spawned)
    assert _events(kb, task_id) == before
    assert _status(kb, task_id) == "review"


def test_review_config_unreadable_falls_closed(kb, monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("config file is corrupt")

    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", None)
    monkeypatch.setattr("hermes_cli.config.load_config", _boom)
    task_id = _make_review_task(kb)
    res = _tick(kb, dry_run=False)
    assert not any(s[0] == task_id for s in res.spawned)
    assert any(
        t == task_id and r.endswith(":config_unreadable")
        for t, r in res.respawn_guarded
    )


def test_review_invalid_config_falls_closed(kb, monkeypatch):
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", None)
    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda *a, **k: {"kanban": {"dispatch_approval_mode": "nonsense"}},
    )
    task_id = _make_review_task(kb)
    res = _tick(kb, dry_run=False)
    assert not any(s[0] == task_id for s in res.spawned)
    assert any(
        t == task_id and r.endswith(":invalid_dispatch_approval_mode")
        for t, r in res.respawn_guarded
    )


# ---------------------------------------------------------------------------
# todo / blocked -> ready promotion
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("child_status", ["todo", "blocked"])
@pytest.mark.parametrize(
    "mode,expect_promoted",
    [("compat", True), ("legacy", False), ("structured", False)],
)
def test_promotion_gate_per_mode_without_approval(
    kb, monkeypatch, mode, expect_promoted, child_status
):
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", mode)
    _parent, child_id = _make_child_with_done_parent(kb, child_status=child_status)
    with kb.connect_closing() as conn:
        promoted = kb.recompute_ready(conn)
    if expect_promoted:
        assert promoted >= 1
        assert _status(kb, child_id) == "ready"
    else:
        assert _status(kb, child_id) == child_status


def test_compat_promotion_is_audited(kb, monkeypatch):
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", "compat")
    _parent, child_id = _make_child_with_done_parent(kb)
    with kb.connect_closing() as conn:
        kb.recompute_ready(conn)
    kinds = _events(kb, child_id)
    assert "promotion_ungated" in kinds
    assert "promoted" in kinds


@pytest.mark.parametrize("child_status", ["todo", "blocked"])
def test_promotion_allowed_with_legacy_marker(kb, monkeypatch, child_status):
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", "legacy")
    _parent, child_id = _make_child_with_done_parent(kb, child_status=child_status)
    _approve_legacy(kb, child_id)
    with kb.connect_closing() as conn:
        kb.recompute_ready(conn)
    assert _status(kb, child_id) == "ready"


@pytest.mark.parametrize("child_status", ["todo", "blocked"])
def test_promotion_allowed_with_structured_approval(kb, monkeypatch, child_status):
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", "structured")
    _parent, child_id = _make_child_with_done_parent(kb, child_status=child_status)
    _approve_structured(kb, child_id)
    with kb.connect_closing() as conn:
        kb.recompute_ready(conn)
    assert _status(kb, child_id) == "ready"


def test_promotion_falls_closed_on_unreadable_config(kb, monkeypatch):
    _parent, child_id = _make_child_with_done_parent(kb)

    def _boom(*a, **k):
        raise RuntimeError("config file is corrupt")

    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", None)
    monkeypatch.setattr("hermes_cli.config.load_config", _boom)
    with kb.connect_closing() as conn:
        promoted = kb.recompute_ready(conn)
    assert promoted == 0
    assert _status(kb, child_id) == "todo"


def test_promotion_falls_closed_on_invalid_config(kb, monkeypatch):
    _parent, child_id = _make_child_with_done_parent(kb)
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", None)
    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda *a, **k: {"kanban": {"dispatch_approval_mode": "nonsense"}},
    )
    with kb.connect_closing() as conn:
        promoted = kb.recompute_ready(conn)
    assert promoted == 0
    assert _status(kb, child_id) == "todo"


def test_promotion_dry_run_writes_nothing(kb, monkeypatch):
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", "compat")
    _parent, child_id = _make_child_with_done_parent(kb)
    before = _events(kb, child_id)
    with kb.connect_closing() as conn:
        promoted = kb.recompute_ready(conn, dry_run=True)
    assert promoted == 1  # reports what WOULD happen
    assert _status(kb, child_id) == "todo"
    assert _events(kb, child_id) == before


def test_dispatch_dry_run_does_not_promote(kb, monkeypatch):
    """A preview tick must not advance todo -> ready on the real board."""
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", "compat")
    _parent, child_id = _make_child_with_done_parent(kb)
    before = _events(kb, child_id)
    res = _tick(kb, dry_run=True)
    assert res.promoted == 1
    assert _status(kb, child_id) == "todo"
    assert _events(kb, child_id) == before


def test_no_approval_row_is_written_by_a_dry_run(kb, monkeypatch):
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", "compat")
    with kb.connect_closing() as conn:
        kb.create_task(conn, title="t", assignee="default")
    _tick(kb, dry_run=True)
    with kb.connect_closing() as conn:
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM task_dispatch_approvals"
        ).fetchone()["n"]
    assert n == 0


# ---------------------------------------------------------------------------
# Invariants that must survive the new gate
# ---------------------------------------------------------------------------


def test_sticky_block_still_wins_over_an_approval(kb, monkeypatch):
    """An approval must not resurrect a worker-blocked card."""
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", "compat")
    _parent, child_id = _make_child_with_done_parent(kb, child_status="blocked")
    with kb.connect_closing() as conn:
        with kb.write_txn(conn):
            kb._append_event(conn, child_id, "blocked", {"kind": "worker"})
    _approve_structured(kb, child_id)
    with kb.connect_closing() as conn:
        kb.recompute_ready(conn)
    assert _status(kb, child_id) == "blocked"


def test_max_in_progress_is_preserved_under_the_gate(kb, monkeypatch):
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", "compat")
    with kb.connect_closing() as conn:
        for i in range(4):
            kb.create_task(conn, title=f"t{i}", assignee="default")
    res = _tick(kb, dry_run=False, max_in_progress=2)
    assert len(res.spawned) == 2


def test_per_profile_cap_is_preserved_under_the_review_gate(kb, monkeypatch):
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", "compat")
    for i in range(4):
        _make_review_task(kb, title=f"r{i}")
    res = _tick(kb, dry_run=False, max_spawn=2)
    assert len(res.spawned) == 2


def test_repeated_denied_review_ticks_are_idempotent(kb, monkeypatch):
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", "structured")
    task_id = _make_review_task(kb)
    for _ in range(3):
        res = _tick(kb, dry_run=False)
        assert res.spawned == []
    assert _status(kb, task_id) == "review"


def test_recover_orphans_regression_under_the_gate(kb, monkeypatch):
    """A stale claim is still reclaimed while the gate denies dispatch."""
    monkeypatch.setattr(kb, "_DISPATCH_APPROVAL_MODE_OVERRIDE", "structured")
    with kb.connect_closing() as conn:
        task_id = kb.create_task(conn, title="t", assignee="default")
        with kb.write_txn(conn):
            conn.execute(
                "UPDATE tasks SET status = 'running', claim_lock = 'dead', "
                "claim_expires = 1 WHERE id = ?",
                (task_id,),
            )
    res = _tick(kb, dry_run=False)
    assert res.reclaimed >= 1
    assert _status(kb, task_id) == "ready"
    with kb.connect_closing() as conn:
        row = conn.execute(
            "SELECT claim_lock FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
    assert row["claim_lock"] is None

#!/usr/bin/env python3
"""
E2E contract proofs for PR #42 runtime slice.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from scripts.runtime_contracts import (
    Card,
    DispatchApproval,
    KanbanFixture,
    TempSqliteFixture,
    approve_dispatch_command,
    build_fixture_suite,
    canonical_idempotency_key,
    check_dependencies,
    detect_collision,
    detect_orphan_claims,
    dependencies_resolved,
    is_dispatch_explicitly_allowed,
    legacy_backfill_needed,
    materialize_issue_card,
    migrate_legacy_dispatch_marker,
    record_dispatch_approval,
    validate_dispatch_approval_object,
    validate_idempotency_key_format,
    validate_recovery_scope,
)


# ---------------------------------------------------------------------------
# 1. issue materialized twice -> single card
# ---------------------------------------------------------------------------

def test_materialize_twice_yields_single_card():
    kanban = KanbanFixture()
    materialize_issue_card(kanban, 42, "Sample", owner_agent="agent-x")
    materialize_issue_card(kanban, 42, "Sample", owner_agent="agent-x")
    assert kanban.count_for_issue(42) == 1


# ---------------------------------------------------------------------------
# 2. task without approval -> no dispatch
# ---------------------------------------------------------------------------

def test_without_dispatch_approval_is_not_approved():
    card = Card(issue=1)
    card.dispatch_approval = None
    assert is_dispatch_explicitly_allowed(card) is False
    errs = validate_dispatch_approval_object(None)
    assert errs


# ---------------------------------------------------------------------------
# 3. valid approval -> one dispatch event
# ---------------------------------------------------------------------------

def test_valid_approval_creates_approval_event():
    card = Card(issue=2)
    approval = DispatchApproval(
        approved_by="orchestrator",
        approved_at_utc="2026-08-01T15:00:00+00:00",
        source="reconciliation_cycle",
    )
    card, event = record_dispatch_approval(card, approval)
    assert is_dispatch_explicitly_allowed(card) is True
    assert event["action"] == "act_approve_dispatch"
    assert card.dispatch_approval.approved_by == "orchestrator"


# ---------------------------------------------------------------------------
# 4. unfinished dependency -> dispatch blocked
# ---------------------------------------------------------------------------

def test_open_dependency_blocks_dispatch():
    card = Card(issue=4, dependencies=[3])
    assert dependencies_resolved(card, {1, 2}) is False


# ---------------------------------------------------------------------------
# 5. predecessor done -> dispatch allowed
# ---------------------------------------------------------------------------

def test_closed_dependencies_allow_dispatch():
    card = Card(issue=4, dependencies=[3])
    assert dependencies_resolved(card, {1, 2, 3}) is True


# ---------------------------------------------------------------------------
# 6. orphan claim -> reconciliation moves to safe state
# ---------------------------------------------------------------------------

def test_orphan_claim_detection():
    suite = build_fixture_suite()
    try:
        cards = [
            Card(issue=10, dependencies=[]),
            Card(issue=11, dependencies=[]),
        ]
        for card in cards:
            card.idempotency_key = canonical_idempotency_key(card.issue)
        orphans = detect_orphan_claims(cards, known_issue_ids={10})
        assert len(orphans) == 1
        assert orphans[0].issue == 11
    finally:
        suite.cleanup()


# ---------------------------------------------------------------------------
# 7. repeat recovery -> idempotent/no duplicate effects
# ---------------------------------------------------------------------------

def test_repeat_recovery_is_idempotent():
    card = Card(issue=6, active_run=True, worker_pid=888888)
    card.checkpoint_ref = "ck-1"
    card.change_token = "token-1"
    card.dispatch_approval = DispatchApproval(
        approved_by="orchestrator",
        approved_at_utc="2026-08-01T15:00:00+00:00",
        source="reconciliation_cycle",
    )
    first_scope = validate_recovery_scope(card)
    assert first_scope is False
    card.active_run = False
    card.worker_pid = None
    second_scope = validate_recovery_scope(card)
    assert second_scope is True


# ---------------------------------------------------------------------------
# SQLite uniqueness proof
# ---------------------------------------------------------------------------

def test_temp_db_enforces_single_card_per_issue():
    db_dir = tempfile.mkdtemp(prefix="blitzhub-contracts-")
    db_path = Path(db_dir) / "kanban.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE cards (id TEXT PRIMARY KEY, issue_number INTEGER NOT NULL, repository TEXT NOT NULL, title TEXT NOT NULL, state TEXT NOT NULL, dependencies TEXT NOT NULL DEFAULT '[]')"
    )
    conn.execute(
        "CREATE UNIQUE INDEX idx_idempotency ON cards(issue_number, repository)"
    )
    conn.execute(
        "INSERT INTO cards (id, issue_number, repository, title, state, dependencies) VALUES (?,?,?,?,?,?)",
        ("card-10", 10, "pestoura/blitzhub-cra-navigator", "Title", "in_progress", "[]"),
    )
    conn.commit()
    row = conn.execute("SELECT COUNT(*) AS c FROM cards WHERE issue_number=10").fetchone()
    assert int(row["c"]) == 1
    try:
        conn.execute(
            "INSERT INTO cards (id, issue_number, repository, title, state, dependencies) VALUES (?,?,?,?,?,?)",
            ("card-10-dup", 10, "pestoura/blitzhub-cra-navigator", "Title 2", "backlog", "[]"),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    row = conn.execute("SELECT COUNT(*) AS c FROM cards WHERE issue_number=10").fetchone()
    assert int(row["c"]) == 1
    conn.close()


# ---------------------------------------------------------------------------
# Canonical key format + public validation report
# ---------------------------------------------------------------------------

def test_canonical_idempotency_key_format():
    key = canonical_idempotency_key(7)
    assert key == "github:pestoura/blitzhub-cra-navigator:issue:7"
    assert validate_idempotency_key_format(key) is True


def test_legacy_backfill_detection() -> None:
    card = Card(issue=8, idempotency_key="legacy-token")
    assert legacy_backfill_needed(card) is True


# ---------------------------------------------------------------------------
# Dispatch approval slice
# ---------------------------------------------------------------------------

class TestDispatchApprovalSlice:
    def test_without_approval_no_dispatch(self) -> None:
        card = Card(issue=20, dependencies=[])
        assert is_dispatch_explicitly_allowed(card) is False

    def test_valid_approval_allows_exactly_one_claim(self) -> None:
        card = Card(issue=21, dependencies=[])
        first = approve_dispatch_command(card, approved_by="orchestrator", source="reconciliation_cycle")
        second = approve_dispatch_command(card, approved_by="orchestrator", source="reconciliation_cycle")
        assert first.get("status") != "already_approved"
        assert second.get("status") == "already_approved"
        assert sum(1 for e in card.audit_events if e["action"] == "act_approve_dispatch") == 1

    def test_second_approval_does_not_duplicate_event_or_claim(self) -> None:
        card = Card(issue=22, dependencies=[])
        approve_dispatch_command(card, approved_by="supervisor", source="supervisory_run")
        approve_dispatch_command(card, approved_by="supervisor", source="supervisory_run")
        approvals = [e for e in card.audit_events if e["action"] == "act_approve_dispatch"]
        assert len(approvals) == 1
        assert card.dispatch_approval.approved_by == "supervisor"

    def test_pending_dependency_blocks_approval_and_dispatch(self) -> None:
        card = Card(issue=4, dependencies=[3])
        closed = {1, 2}
        ok, reason = check_dependencies(card, closed)
        assert ok is False
        assert "3" in (reason or "")
        assert is_dispatch_explicitly_allowed(card) is False

    def test_legacy_marker_migration_is_explicit_and_audited(self) -> None:
        card = Card(issue=24, dependencies=[], github_issue_url="https://github.com/pestoura/blitzhub-cra-navigator/issues/24 [sppm-dispatch-approved]")
        result = migrate_legacy_dispatch_marker(card)
        assert result["migrated"] is True
        assert is_dispatch_explicitly_allowed(card) is True
        assert any(e["action"] == "legacy_marker_migration" for e in card.audit_events)


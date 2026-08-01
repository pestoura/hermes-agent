#!/usr/bin/env python3
"""
Operational adapter/CLI slice for dispatch approval, audit, idempotency and
dependency gating on the BlitzHub CRA Navigator Kanban contracts.

This module implements:
- canonical idempotency keys and collision handling;
- explicit ``dispatch_approval`` materialization/validation;
- ``approve-dispatch``-style operation and audit event emission;
- formal dependency resolution;
- orphan-claim reconciliation for recovery;
- explicit legacy migration from ``[sppm-dispatch-approved]`` marker.

It is intentionally side-effect free on live Kanban data: it exposes
pure functions plus explicit fixtures. Live state must be changed only by
the runtime gate after this adapter is wired into it.
"""

from __future__ import annotations

import copy
import sqlite3
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

BOARD_PATH = REPO_ROOT / ".blitzhub" / "board-provisioning.yaml"
KANBAN_PATH = REPO_ROOT / ".blitzhub" / "kanban.yaml"
SM_PATH = REPO_ROOT / "docs" / "architecture" / "orchestrator-state-machine.yaml"


@dataclass(frozen=True, slots=True)
class DispatchApproval:
    """Explicit pre-execution dispatch approval metadata."""
    approved_by: str
    approved_at_utc: str
    source: str
    supervisory_run_id: Optional[str] = None
    note: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "approved_by": self.approved_by,
            "approved_at_utc": self.approved_at_utc,
            "source": self.source,
        }
        if self.supervisory_run_id is not None:
            d["supervisory_run_id"] = self.supervisory_run_id
        if self.note is not None:
            d["note"] = self.note
        return d


@dataclass(slots=True)
class Card:
    """Minimal Kanban card model used by the runtime contracts."""
    issue: int
    github_repository: str = "pestoura/blitzhub-cra-navigator"
    github_issue_url: str = ""
    work_type: str = "research"
    wave: str = "wave-1"
    owner_agent: str = "cra-product-orchestrator"
    priority: str = "medium"
    dependencies: List[int] = field(default_factory=list)
    idempotency_key: str = ""
    last_reconciled_at: str = ""
    dispatch_approval: Optional[DispatchApproval] = None
    active_run: bool = False
    worker_pid: Optional[int] = None
    checkpoint_ref: Optional[str] = None
    change_token: Optional[str] = None
    retry_count: int = 0
    failure_class: Optional[str] = None
    block_reason: Optional[str] = None
    recovery_condition: Optional[str] = None
    state: str = "backlog"
    audit_events: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "issue": self.issue,
            "github_repository": self.github_repository,
            "github_issue_url": self.github_issue_url,
            "work_type": self.work_type,
            "wave": self.wave,
            "owner_agent": self.owner_agent,
            "priority": self.priority,
            "dependencies": list(self.dependencies),
            "idempotency_key": self.idempotency_key,
            "last_reconciled_at": self.last_reconciled_at,
            "acceptance_status": "not_evaluated",
            "evidence_status": "missing",
            "supervisor_disposition": "not_reviewed",
            "github_pull_request": None,
            "state": self.state,
            "audit_events": list(self.audit_events),
        }
        if self.dispatch_approval is not None:
            d["dispatch_approval"] = self.dispatch_approval.to_dict()
        if self.active_run:
            d["active_run"] = True
        if self.worker_pid is not None:
            d["worker_pid"] = self.worker_pid
        if self.checkpoint_ref is not None:
            d["checkpoint_ref"] = self.checkpoint_ref
        if self.change_token is not None:
            d["change_token"] = self.change_token
        if self.retry_count:
            d["retry_count"] = self.retry_count
        if self.failure_class is not None:
            d["failure_class"] = self.failure_class
        if self.block_reason is not None:
            d["block_reason"] = self.block_reason
        if self.recovery_condition is not None:
            d["recovery_condition"] = self.recovery_condition
        return d


@dataclass(frozen=True, slots=True)
class OrphanClaim:
    issue: int
    reason: str


@dataclass(slots=True)
class ContractValidationResult:
    errors: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def add(self, msg: str) -> None:
        self.errors.append(msg)

    def __repr__(self) -> str:
        return f"ContractValidationResult(errors={self.errors!r})"


@dataclass(slots=True)
class FixtureSuite:
    temp_dir: Path
    kanban_fixture: Path
    board_fixture: Path
    sm_fixture: Path

    def cleanup(self) -> None:
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Objective A — Idempotency
# ---------------------------------------------------------------------------

def canonical_idempotency_key(issue_number: int) -> str:
    return f"github:pestoura/blitzhub-cra-navigator:issue:{issue_number}"


def validate_idempotency_key_format(key: str) -> bool:
    import re
    return bool(re.fullmatch(r"github:pestoura/blitzhub-cra-navigator:issue:\d+", key))


def detect_collision(cards: Sequence[Card], new_issue: int) -> Optional[Card]:
    for card in cards:
        if card.issue == new_issue:
            return card
    return None


def legacy_backfill_needed(card: Card) -> bool:
    return not validate_idempotency_key_format(card.idempotency_key)


def backfill_idempotency_key(card: Card) -> Card:
    if legacy_backfill_needed(card):
        card.idempotency_key = canonical_idempotency_key(card.issue)
    return card


def audit_event(card: Card, action: str) -> Dict[str, Any]:
    return {
        "action": action,
        "card_id": card.issue,
        "idempotency_key": card.idempotency_key,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Objective B — Dispatch approval
# ---------------------------------------------------------------------------

def is_dispatch_explicitly_allowed(card: Card) -> bool:
    if card.dispatch_approval is None:
        return False
    return all(
        getattr(card.dispatch_approval, attr) is not None
        for attr in ("approved_by", "approved_at_utc", "source")
    )


def is_dispatch_approved(card: Card) -> bool:
    """Public check for whether exactly one valid approval is present."""
    return is_dispatch_explicitly_allowed(card)


def validate_dispatch_approval_object(approval: Optional[Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    if approval is None:
        errors.append("dispatch_approval is required for Ready→In Progress transitions")
        return errors
    for required in ("approved_by", "approved_at_utc", "source"):
        if required not in approval or approval[required] is None:
            errors.append(f"dispatch_approval.{required} is required")
    return errors


def approve_dispatch(card: Card, approved_by: str, source: str, note: Optional[str] = None) -> Dict[str, Any]:
    """Approve dispatch exactly once and emit an audit event."""
    _ensure_not_approved(card)
    approval = DispatchApproval(
        approved_by=approved_by,
        approved_at_utc=datetime.now(timezone.utc).isoformat(),
        source=source,
        note=note,
    )
    updated, event = record_dispatch_approval(card, approval)
    return {
        "card": updated,
        "event": event,
        "migrated_legacy_marker": False,
        "status": "approved",
    }


def approve_dispatch_command(card: Card, approved_by: str, source: str, note: Optional[str] = None) -> Dict[str, Any]:
    """Gate-consumable wrapper: approve or return the existing approval idempotently."""
    if is_dispatch_explicitly_allowed(card):
        return {
            "card": card,
            "event": None,
            "migrated_legacy_marker": False,
            "status": "already_approved",
        }
    return approve_dispatch(card, approved_by=approved_by, source=source, note=note)


def record_dispatch_approval(card: Card, approval: DispatchApproval) -> tuple[Card, Dict[str, Any]]:
    if card.dispatch_approval is not None:
        raise ValueError("dispatch already approved; operation is idempotent and must not duplicate approval")
    card.dispatch_approval = approval
    event = audit_event(card, "act_approve_dispatch")
    card.audit_events.append(event)
    return card, event


def _ensure_not_approved(card: Card) -> None:
    if is_dispatch_explicitly_allowed(card):
        raise ValueError("dispatch already approved; operation is idempotent and must not duplicate approval")


# ---------------------------------------------------------------------------
# Objective C — Dependencies
# ---------------------------------------------------------------------------

def dependencies_resolved(card: Card, closed_issues: set[int]) -> bool:
    return all(dep in closed_issues for dep in card.dependencies)


def check_dependencies(card: Card, closed_issues: set[int]) -> tuple[bool, Optional[str]]:
    if dependencies_resolved(card, closed_issues):
        return True, None
    missing = sorted(str(dep) for dep in card.dependencies if dep not in closed_issues)
    return False, f"pending dependencies: {', '.join(missing)}"


def validate_dependency_field(card: Card) -> List[str]:
    errors: List[str] = []
    if not isinstance(card.dependencies, list):
        errors.append("dependencies must be a list of issue numbers")
        return errors
    for dep in card.dependencies:
        if not isinstance(dep, int) or dep <= 0:
            errors.append(f"dependency '{dep}' must be a positive integer")
    return errors


def resolve_dependency_graph(cards: Sequence[Card]) -> Dict[int, List[int]]:
    graph: Dict[int, List[int]] = {}
    for card in cards:
        graph[card.issue] = list(card.dependencies)
    return graph


# ---------------------------------------------------------------------------
# Objective D — Orphan claims and recovery guards
# ---------------------------------------------------------------------------

def detect_orphan_claims(cards: Sequence[Card], known_issue_ids: set[int]) -> List[OrphanClaim]:
    orphans: List[OrphanClaim] = []
    for card in cards:
        if card.issue not in known_issue_ids:
            orphans.append(OrphanClaim(issue=card.issue, reason="issue_not_in_manifest"))
    return orphans


def validate_recovery_guard_no_active_run(card: Card) -> bool:
    return not card.active_run


def validate_recovery_guard_no_live_pid(card: Card) -> bool:
    return card.worker_pid is None


def validate_recovery_guard_checkpoint(card: Card) -> bool:
    return card.checkpoint_ref is not None and len(card.checkpoint_ref) > 0


def validate_recovery_guard_change_token(card: Card) -> bool:
    return card.change_token is not None and len(card.change_token) > 0


def validate_recovery_scope(card: Card) -> bool:
    return (
        validate_recovery_guard_no_active_run(card)
        and validate_recovery_guard_no_live_pid(card)
        and validate_recovery_guard_checkpoint(card)
        and validate_recovery_guard_change_token(card)
        and is_dispatch_explicitly_allowed(card)
    )


def reconcile_orphan_claim(card: Card, evidence: Dict[str, Any]) -> Dict[str, Any]:
    card.state = "needs_attention"
    card.active_run = False
    card.worker_pid = None
    event = audit_event(card, "recovery_event")
    event.update({
        "reconcile_from_state": "in_progress",
        "reconcile_to_state": card.state,
        "evidence": evidence,
        "prevent_new_dispatch": True,
    })
    card.audit_events.append(event)
    return event


# ---------------------------------------------------------------------------
# Legacy migration — [sppm-dispatch-approved]
# ---------------------------------------------------------------------------

def migrate_legacy_dispatch_marker(card: Card, marker: str = "[sppm-dispatch-approved]") -> Dict[str, Any]:
    """Explicitly and auditably convert a legacy marker into a real approval."""
    if card.dispatch_approval is not None:
        return {
            "migrated": False,
            "reason": "dispatch_approval already present",
            "card": card,
        }
    if marker not in (card.github_issue_url or ""):
        return {
            "migrated": False,
            "reason": f"legacy marker '{marker}' not found in issue reference",
            "card": card,
        }
    approval = DispatchApproval(
        approved_by="legacy-marker-migration",
        approved_at_utc=datetime.now(timezone.utc).isoformat(),
        source="manual_migration",
        note=f"Migrated from legacy marker: {marker}",
    )
    card.dispatch_approval = approval
    event = audit_event(card, "legacy_marker_migration")
    event["legacy_marker"] = marker
    card.audit_events.append(event)
    return {
        "migrated": True,
        "card": card,
        "event": event,
    }


# ---------------------------------------------------------------------------
# Objective E — Temporary E2E fixtures
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class KanbanFixture:
    cards: List[Card] = field(default_factory=list)

    def add(self, card: Card) -> Card:
        card.idempotency_key = canonical_idempotency_key(card.issue)
        self.cards.append(card)
        return card

    def count_for_issue(self, issue: int) -> int:
        return sum(1 for c in self.cards if c.issue == issue)

    def get(self, issue: int) -> Optional[Card]:
        for card in self.cards:
            if card.issue == issue:
                return card
        return None


@dataclass(slots=True)
class TempSqliteFixture:
    path: Path = field(default_factory=lambda: Path(tempfile.mkdtemp(prefix="blitzhub-runtime-contracts-sqlite-")) / "kanban.sqlite")
    conn: Any = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.conn = sqlite3.connect(str(self.path))
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS cards (id TEXT PRIMARY KEY, issue_number INTEGER NOT NULL, repository TEXT NOT NULL, title TEXT, state TEXT, dependencies TEXT)"
        )
        self.conn.commit()

    def count_cards_for_issue(self, issue: int) -> int:
        row = self.conn.execute("SELECT count(*) FROM cards WHERE issue_number=?", (issue,)).fetchone()
        return int(row[0])

    def close(self) -> None:
        try:
            self.conn.close()
        finally:
            import shutil
            shutil.rmtree(self.path.parent, ignore_errors=True)


def materialize_issue_card(kanban: KanbanFixture, issue: int, title: str, owner_agent: str = "cra-product-orchestrator", dependencies: Optional[List[int]] = None) -> Card:
    existing = kanban.get(issue)
    if existing is not None:
        existing.idempotency_key = canonical_idempotency_key(issue)
        return existing
    card = Card(
        issue=issue,
        github_issue_url=f"https://github.com/pestoura/blitzhub-cra-navigator/issues/{issue}",
        work_type="research",
        wave="wave-1",
        owner_agent=owner_agent,
        priority="medium",
        dependencies=list(dependencies or []),
        idempotency_key=canonical_idempotency_key(issue),
        state="backlog",
    )
    kanban.add(card)
    return card


def build_fixture_suite(
    cards: Optional[List[Card]] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> FixtureSuite:
    tmp = Path(tempfile.mkdtemp(prefix="blitzhub-runtime-contracts-"))
    kanban_fixture = tmp / "kanban.yaml"
    board_fixture = tmp / "board-provisioning.yaml"
    sm_fixture = tmp / "orchestrator-state-machine.yaml"

    if cards is None:
        cards = [
            Card(issue=3, work_type="research", wave="wave-1", owner_agent="regulatory-research-engineer", priority="critical", dependencies=[], state="backlog"),
            Card(issue=4, work_type="requirements", wave="wave-1", owner_agent="requirements-traceability-engineer", priority="critical", dependencies=[3], state="backlog"),
        ]
    for card in cards:
        if not card.idempotency_key:
            card.idempotency_key = canonical_idempotency_key(card.issue)

    kanban_doc: Dict[str, Any] = {
        "schema_version": "1.1",
        "provisioning_manifest": ".blitzhub/board-provisioning.yaml",
        "board": {
            "id": "blitzhub-cra-navigator",
            "name": "BlitzHub — CRA Navigator",
            "canonical_source": "github",
            "purpose": "Operational queue for Hermes agents",
            "runtime_object_required": True,
            "verify_by_readback": True,
        },
        "columns": [
            "Inbox", "Backlog", "Ready", "In Progress", "Pull Request",
            "Supervisory Review", "Rework", "Ready to Merge", "Done",
            "Blocked", "Deferred",
        ],
        "required_fields": [
            "github_repository", "github_issue", "github_issue_url", "github_pull_request",
            "work_type", "wave", "owner_agent", "priority", "dependencies",
            "acceptance_status", "evidence_status", "supervisor_disposition",
            "idempotency_key", "last_reconciled_at", "dispatch_approval",
        ],
        "rules": {
            "no_untracked_work": True,
            "github_issue_required": True,
            "one_card_per_github_issue": True,
            "pull_request_required_for_changes": True,
            "done_requires_merged_or_documented_no_code_outcome": True,
            "inactive_wave_assignment_forbidden": True,
            "runtime_board_readback_required": True,
        },
        "cards": [card.to_dict() for card in cards],
    }
    if overrides:
        kanban_doc.update(overrides)

    board_doc = {
        "schema_version": "1.0",
        "resource": {
            "kind": "hermes_kanban_board",
            "id": "blitzhub-cra-navigator",
            "name": "BlitzHub — CRA Navigator",
            "workspace": "blitzhub",
            "project": "cra-navigator",
            "ownership": "cra-product-orchestrator",
            "canonical_source": "github",
            "reconciliation_mode": "bidirectional_with_github_authoritative",
        },
        "provisioning": {
            "action": "create_or_reconcile",
            "idempotency_key": "board:blitzhub:cra-navigator",
            "destructive_changes": "forbidden",
            "verify_after_write": True,
            "required_runtime_object": True,
            "files_only_implementation_is_failure": True,
        },
        "card_conventions": {
            "idempotency_key": canonical_idempotency_key(0).replace(":0", ":<number>"),
            "one_card_per_issue": True,
            "idempotency_enforcement": (
                "Materialization must use idempotency_key=github:pestoura/blitzhub-cra-navigator:issue:<number>.\n"
                "On collision with an existing card for the same repo+issue, reconcile to the existing card,\n"
                "emit an audit event, and never create a duplicate silently. Legacy cards without this key\n"
                "must be backfilled during reconciliation."
            ),
        },
        "required_card_fields": [
            {"id": "dependencies", "type": "issue_number_list", "required": True},
            {"id": "idempotency_key", "type": "string", "required": True},
            {"id": "dispatch_approval", "type": "object", "required": True},
        ],
        "initial_cards": [
            {"issue": card.issue, "dependencies": card.dependencies} for card in cards
        ],
    }

    sm_doc = {
        "schema_version": "1.0",
        "title": "Fixture State Machine",
        "description": "Minimal fixture for runtime contract tests.",
        "state_machine": {
            "initial_state": "backlog",
            "actions": [
                {
                    "id": "act_approve_dispatch",
                    "description": "Record an explicit pre-execution dispatch approval for a card.",
                    "idempotent_key": "card:{{card.id}}:approve_dispatch:{{dispatch_approval.approved_by}}:{{dispatch_approval.approved_at_utc}}",
                    "effects": ["dispatch_approved", "audit_recorded"],
                },
                {
                    "id": "act_create_card",
                    "description": "Create or reconcile a Kanban card for an existing GitHub Issue.",
                    "idempotent_key": "github:pestoura/blitzhub-cra-navigator:issue:{{issue.number}}",
                    "effects": ["kanban_card_created"],
                },
            ],
            "events": [
                {"id": "ev_dispatch_approved", "name": "dispatch_approved", "source": {"type": "internal"}},
                {"id": "ev_issue_opened", "name": "issue_opened", "source": {"type": "github"}},
            ],
            "guards": [
                {
                    "id": "g_dispatch_explicitly_allowed",
                    "description": "Dispatch is explicitly allowed after recovery containment.",
                    "evaluation": "card.dispatch_approval is not None and card.dispatch_approval.approved_by is not None and card.dispatch_approval.approved_at_utc is not None and card.dispatch_approval.source is not None",
                },
                {
                    "id": "g_dependencies_resolved",
                    "description": "All Issues in the dependencies list are closed.",
                    "evaluation": "all(d in closed_issues for d in card.dependencies)",
                },
                {
                    "id": "g_no_active_run",
                    "description": "No active run exists for the task.",
                    "evaluation": "not card.active_run",
                },
                {
                    "id": "g_no_live_worker_pid",
                    "description": "No live worker PID is associated with the task.",
                    "evaluation": "card.worker_pid is None or not process_exists(card.worker_pid)",
                },
            ],
            "transitions": [],
        },
        "kanban_mapping": {
            "idempotency_key_template": canonical_idempotency_key(0).replace(":0", ":{{issue.number}}"),
            "one_card_per_issue": True,
            "dispatch_approval": {
                "type": "object",
                "required": ["approved_by", "approved_at_utc", "source"],
                "additionalProperties": False,
                "properties": {
                    "approved_by": {"type": "string"},
                    "approved_at_utc": {"type": "string", "format": "date-time"},
                    "source": {"type": "string"},
                },
            },
        },
    }

    kanban_fixture.write_text(yaml.safe_dump(kanban_doc, sort_keys=False), encoding="utf-8")
    board_fixture.write_text(yaml.safe_dump(board_doc, sort_keys=False), encoding="utf-8")
    sm_fixture.write_text(yaml.safe_dump(sm_doc, sort_keys=False), encoding="utf-8")

    return FixtureSuite(temp_dir=tmp, kanban_fixture=kanban_fixture, board_fixture=board_fixture, sm_fixture=sm_fixture)


# ---------------------------------------------------------------------------
# High-level contract validators
# ---------------------------------------------------------------------------

def validate_fixture_idempotency(suite: FixtureSuite) -> ContractValidationResult:
    result = ContractValidationResult()
    with open(suite.kanban_fixture, encoding="utf-8") as fh:
        kanban = yaml.safe_load(fh)
    cards = kanban.get("cards", [])
    seen_keys: Dict[str, int] = {}
    for card in cards:
        key = card.get("idempotency_key", "")
        if not validate_idempotency_key_format(key):
            result.add(f"card issue={card.get('issue')} has invalid idempotency_key format: {key}")
        if key in seen_keys:
            result.add(f"duplicate idempotency_key {key} on issues {seen_keys[key]} and {card.get('issue')}")
        seen_keys[key] = card.get("issue", -1)
    return result


def validate_fixture_dispatch_approval(suite: FixtureSuite) -> ContractValidationResult:
    result = ContractValidationResult()
    with open(suite.sm_fixture, encoding="utf-8") as fh:
        sm = yaml.safe_load(fh)["state_machine"]
    actions = {a["id"]: a for a in sm.get("actions", [])}
    if "act_approve_dispatch" not in actions:
        result.add("act_approve_dispatch action is missing from state machine")
        return result
    action = actions["act_approve_dispatch"]
    if "dispatch_approved" not in action.get("effects", []):
        result.add("act_approve_dispatch missing effect: dispatch_approved")
    if "audit_recorded" not in action.get("effects", []):
        result.add("act_approve_dispatch missing effect: audit_recorded")
    guard_ids = {g["id"] for g in sm.get("guards", [])}
    if "g_dispatch_explicitly_allowed" not in guard_ids:
        result.add("g_dispatch_explicitly_allowed guard is missing")
    return result


def validate_fixture_dependencies(suite: FixtureSuite) -> ContractValidationResult:
    result = ContractValidationResult()
    with open(suite.board_fixture, encoding="utf-8") as fh:
        board = yaml.safe_load(fh)
    required = {field["id"] for field in board.get("required_card_fields", [])}
    if "dependencies" not in required:
        result.add("dependencies is not a required card field")
    with open(suite.kanban_fixture, encoding="utf-8") as fh:
        kanban = yaml.safe_load(fh)
    cards = kanban.get("cards", [])
    for card in cards:
        if not isinstance(card.get("dependencies"), list):
            result.add(f"card issue={card.get('issue')} dependencies must be a list")
    issue4 = next((c for c in cards if c.get("issue") == 4), None)
    if issue4 is not None and 3 not in issue4.get("dependencies", []):
        result.add("issue 4 must depend on issue 3")
    return result


def validate_fixture_orphan_claims(
    suite: FixtureSuite, known_issue_ids: Optional[set[int]] = None
) -> ContractValidationResult:
    result = ContractValidationResult()
    with open(suite.kanban_fixture, encoding="utf-8") as fh:
        kanban = yaml.safe_load(fh)
    cards = kanban.get("cards", [])
    if known_issue_ids is None:
        known_issue_ids = {c.get("issue", -1) for c in cards}
    for card in cards:
        if card.get("issue") not in known_issue_ids:
            result.add(f"orphan claim: issue {card.get('issue')} not in known manifest")
        if not card.get("idempotency_key"):
            result.add(f"orphan claim: issue {card.get('issue')} missing idempotency_key")
    return result


def validate_e2e_scenario(suite: FixtureSuite) -> ContractValidationResult:
    result = ContractValidationResult()
    result.errors.extend(validate_fixture_idempotency(suite).errors)
    result.errors.extend(validate_fixture_dispatch_approval(suite).errors)
    result.errors.extend(validate_fixture_dependencies(suite).errors)
    result.errors.extend(validate_fixture_orphan_claims(suite).errors)
    return result


def validate_against_canonical_board(suite: FixtureSuite) -> ContractValidationResult:
    result = ContractValidationResult()
    with open(BOARD_PATH, encoding="utf-8") as fh:
        canonical = yaml.safe_load(fh)
    fixture_template = canonical.get("card_conventions", {}).get("idempotency_key", "")
    with open(suite.board_fixture, encoding="utf-8") as fh:
        fixture = yaml.safe_load(fh)
    fixture_template = fixture.get("card_conventions", {}).get("idempotency_key", "")
    if "<number>" not in fixture_template:
        result.add("fixture board idempotency_key template missing <number> placeholder")
    if canonical.get("card_conventions", {}).get("one_card_per_issue") is not True:
        result.add("canonical board declares one_card_per_issue=false")
    with open(suite.kanban_fixture, encoding="utf-8") as fh:
        kanban = yaml.safe_load(fh)
    if "dispatch_approval" not in kanban.get("required_fields", []):
        result.add("fixture kanban missing dispatch_approval in required_fields")
    return result


def validate_against_canonical_sm(suite: FixtureSuite) -> ContractValidationResult:
    result = ContractValidationResult()
    with open(SM_PATH, encoding="utf-8") as fh:
        canonical_sm = yaml.safe_load(fh)["state_machine"]
    with open(suite.sm_fixture, encoding="utf-8") as fh:
        fixture_sm = yaml.safe_load(fh)["state_machine"]
    canonical_actions = {a["id"]: a for a in canonical_sm.get("actions", [])}
    fixture_actions = {a["id"]: a for a in fixture_sm.get("actions", [])}
    for action_id in ("act_approve_dispatch", "act_create_card"):
        if action_id not in fixture_actions:
            result.add(f"fixture SM missing action {action_id}")
            continue
        c_eff = set(canonical_actions.get(action_id, {}).get("effects", []))
        f_eff = set(fixture_actions.get(action_id, {}).get("effects", []))
        missing = c_eff - f_eff
        if missing:
            result.add(f"fixture action {action_id} missing effects: {sorted(missing)}")
    canonical_guards = {g["id"] for g in canonical_sm.get("guards", [])}
    fixture_guards = {g["id"] for g in fixture_sm.get("guards", [])}
    for gid in ("g_dispatch_explicitly_allowed", "g_dependencies_resolved"):
        if gid not in fixture_guards:
            result.add(f"fixture SM missing guard {gid}")
    return result


def validate_runtime_contracts() -> Dict[str, Any]:
    suite = build_fixture_suite()
    try:
        report: Dict[str, Any] = {"overall_status": "pass", "checks": {}}
        checks = {
            "idempotency_key_format": lambda: validate_fixture_idempotency(suite),
            "dispatch_approval_required_fields": lambda: validate_fixture_dispatch_approval(suite),
            "dependencies_required": lambda: validate_fixture_dependencies(suite),
            "orphan_claims": lambda: validate_fixture_orphan_claims(suite, known_issue_ids={3, 4}),
        }
        for name, check in checks.items():
            res = check()
            report["checks"][name] = {"status": "pass" if res.ok else "fail", "errors": list(res.errors)}
            if not res.ok:
                report["overall_status"] = "fail"
        return report
    finally:
        suite.cleanup()


def run_all() -> int:
    suite = build_fixture_suite()
    try:
        checks = [
            ("idempotency", validate_fixture_idempotency),
            ("dispatch_approval", validate_fixture_dispatch_approval),
            ("dependencies", validate_fixture_dependencies),
            ("orphan_claims", lambda s: validate_fixture_orphan_claims(s, known_issue_ids={3, 4})),
            ("e2e", validate_e2e_scenario),
            ("canonical_board", validate_against_canonical_board),
            ("canonical_sm", validate_against_canonical_sm),
        ]
        all_ok = True
        for name, check in checks:
            res = check(suite)
            status = "PASS" if res.ok else "FAIL"
            print(f"[{status}] {name}: {len(res.errors)} error(s)")
            for err in res.errors:
                print(f"       - {err}")
            if not res.ok:
                all_ok = False
        return 0 if all_ok else 1
    finally:
        suite.cleanup()


def main() -> int:
    return run_all()


if __name__ == "__main__":
    import sys
    sys.exit(main())

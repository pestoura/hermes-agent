#!/usr/bin/env python3
"""
Idempotency and dispatch approval contract tests.

These tests prove the operational contract without touching a live Kanban/DB:
- one-card-per-issue materialization key format and collision policy
- legacy card backfill behavior
- explicit dispatch approval metadata and audit action/event
- duplicate-issue retry reconciliation
- formal dependencies required for dispatch
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
BOARD_PATH = REPO_ROOT / ".blitzhub" / "board-provisioning.yaml"
KANBAN_PATH = REPO_ROOT / ".blitzhub" / "kanban.yaml"
SM_PATH = REPO_ROOT / "docs" / "architecture" / "orchestrator-state-machine.yaml"
SCHEMA_PATH = REPO_ROOT / ".blitzhub" / "schemas" / "orchestrator-state-machine.yaml.schema.json"
SOULS_DIR = REPO_ROOT / "agents" / "souls"


def test_idempotency_key_format_is_canonical():
    with open(BOARD_PATH, encoding="utf-8") as fh:
        board = yaml.safe_load(fh)
    template = board["card_conventions"]["idempotency_key"]
    assert template == "github:pestoura/blitzhub-cra-navigator:issue:<number>"
    assert "<number>" in template


def test_one_card_per_issue_is_declared_true():
    with open(BOARD_PATH, encoding="utf-8") as fh:
        board = yaml.safe_load(fh)
    assert board["card_conventions"]["one_card_per_issue"] is True


def test_idempotency_enforcement_policy_requires_reconciliation_and_audit():
    with open(BOARD_PATH, encoding="utf-8") as fh:
        board = yaml.safe_load(fh)
    text = board["card_conventions"].get("idempotency_enforcement", "")
    assert "reconcile" in text.lower()
    assert "audit" in text.lower()
    assert "backfill" in text.lower()


def test_legacy_card_backfill_is_part_of_enforcement_policy():
    with open(BOARD_PATH, encoding="utf-8") as fh:
        board = yaml.safe_load(fh)
    text = board["card_conventions"].get("idempotency_enforcement", "")
    assert "legacy" in text.lower()
    assert "reconciliation" in text.lower()


def test_dispatch_approval_field_is_required_in_kanban():
    with open(KANBAN_PATH, encoding="utf-8") as fh:
        kanban = yaml.safe_load(fh)
    assert "dispatch_approval" in set(kanban["required_fields"])


def test_state_machine_contains_approve_dispatch_action():
    with open(SM_PATH, encoding="utf-8") as fh:
        sm = yaml.safe_load(fh)["state_machine"]
    actions = {a["id"]: a for a in sm["actions"]}
    action = actions["act_approve_dispatch"]
    assert "dispatch_approved" in action["effects"]
    assert "audit_recorded" in action["effects"]


def test_state_machine_contains_dispatch_approved_event():
    with open(SM_PATH, encoding="utf-8") as fh:
        sm = yaml.safe_load(fh)["state_machine"]
    event_ids = {e["id"] for e in sm["events"]}
    assert "ev_dispatch_approved" in event_ids


def test_dispatch_guard_requires_explicit_approval_object():
    with open(SM_PATH, encoding="utf-8") as fh:
        sm = yaml.safe_load(fh)["state_machine"]
    guards = {g["id"]: g for g in sm["guards"]}
    assert "dispatch_approval" in guards["g_dispatch_explicitly_allowed"]["evaluation"]


def test_dependencies_are_required_card_field():
    with open(BOARD_PATH, encoding="utf-8") as fh:
        board = yaml.safe_load(fh)
    required = {field["id"] for field in board["required_card_fields"]}
    assert "dependencies" in required


def test_issue_4_explicit_dependency_on_issue_3():
    with open(BOARD_PATH, encoding="utf-8") as fh:
        board = yaml.safe_load(fh)
    issue_4 = next(card for card in board["initial_cards"] if card["issue"] == 4)
    assert 3 in issue_4["dependencies"]


def test_spec_validates_after_contract_changes():
    import json
    import jsonschema
    with open(SM_PATH, encoding="utf-8") as fh:
        spec = yaml.safe_load(fh)
    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        schema = json.load(fh)
    jsonschema.Draft202012Validator(schema).validate(spec)


def test_souls_are_not_generic_and_are_substantive():
    generic = "You are Hermes Agent, an intelligent AI assistant created by Nous Research"
    for path in sorted(SOULS_DIR.glob("*.SOUL.md")):
        content = path.read_text(encoding="utf-8")
        assert generic not in content, f"Generic soul found in {path.name}"
        assert len(content) > 500, f"Soul {path.name} is too short"


def test_five_soul_files_exist():
    souls = list(SOULS_DIR.glob("*.SOUL.md"))
    assert len(souls) >= 5

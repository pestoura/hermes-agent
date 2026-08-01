#!/usr/bin/env python3
"""
Executable test suite for the CRA Product Orchestrator state machine.

Validates the machine-readable specification in
docs/architecture/orchestrator-state-machine.yaml against Issue #7 acceptance
criteria:

  - states and Kanban column correspondence
  - events from Issues, PRs, comments, checks, and supervisory results
  - guards and preconditions for each transition
  - idempotent actions and deduplication keys
  - retries, backoff, timeout, and dead-letter handling
  - branch conflict handling (Hermes vs ChatGPT)
  - how REQUIRED findings interrupt or reprioritize work
  - how waves limit dispatch
  - normal, rework, block, defer, and recovery scenarios

Run with:  python -m pytest tests/orchestrator_state_machine_test.py -v
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SM_PATH = REPO_ROOT / "docs" / "architecture" / "orchestrator-state-machine.yaml"
SCHEMA_PATH = (
    REPO_ROOT / ".blitzhub" / "schemas" / "orchestrator-state-machine.yaml.schema.json"
)
BOARD_PATH = REPO_ROOT / ".blitzhub" / "board-provisioning.yaml"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def spec() -> dict:
    with open(SM_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.fixture(scope="module")
def sm(spec) -> dict:
    return spec["state_machine"]


@pytest.fixture(scope="module")
def states(sm) -> dict:
    return {s["id"]: s for s in sm["states"]}


@pytest.fixture(scope="module")
def events(sm) -> dict:
    return {e["id"]: e for e in sm["events"]}


@pytest.fixture(scope="module")
def guards(sm) -> dict:
    return {g["id"]: g for g in sm["guards"]}


@pytest.fixture(scope="module")
def actions(sm) -> dict:
    return {a["id"]: a for a in sm["actions"]}


@pytest.fixture(scope="module")
def sim_spec() -> dict:
    with open(SM_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _get_event(t: dict) -> str:
    """Extract the 'on' event from a transition, handling the YAML 'on'→True quirk."""
    event = t.get("on")
    if event is None and True in t:
        event = t[True]
    return event


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

def test_spec_validates_against_schema(spec):
    """The specification must be valid against its JSON schema."""
    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        schema = json.load(fh)
    jsonschema.Draft202012Validator(schema).validate(spec)


def test_spec_has_required_top_level_fields(spec):
    for field in ("schema_version", "title", "description", "state_machine"):
        assert field in spec, f"missing top-level field: {field}"


# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------

def test_states_cover_all_kanban_columns(sm):
    """Every Kanban column name in the manifest must have a corresponding state."""
    with open(BOARD_PATH, encoding="utf-8") as fh:
        board = yaml.safe_load(fh)
    board_columns = {c["name"] for c in board["columns"]}

    sm_columns = {s["kanban_column"] for s in sm["states"]}
    missing = board_columns - sm_columns
    assert not missing, f"states missing for Kanban columns: {missing}"


def test_state_ids_are_unique(sm):
    ids = [s["id"] for s in sm["states"]]
    assert len(ids) == len(set(ids)), "duplicate state ids"


def test_initial_state_exists(states, sm):
    assert sm["initial_state"] in states


def test_work_item_flow_contains_all_states(sm):
    """The work_item_flow list must include every state id."""
    flow = set(sm["work_item_flow"])
    state_ids = {s["id"] for s in sm["states"]}
    assert flow == state_ids, f"work_item_flow != states: diff={state_ids - flow}"


def test_done_is_terminal(sm):
    done = next(s for s in sm["states"] if s["id"] == "done")
    assert done["kind"] == "terminal"


def test_external_review_is_external(sm):
    ext = next(s for s in sm["states"] if s["id"] == "external_review")
    assert ext["kind"] == "terminal_external"


def test_blocked_and_deferred_are_interrupt(sm):
    for sid in ("blocked", "deferred"):
        st = next(s for s in sm["states"] if s["id"] == sid)
        assert st["kind"] == "interruption"


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def test_events_cover_all_required_sources(sm):
    """Events must come from github, supervisory, internal, and agent_runtime."""
    sources = {e["source"]["type"] for e in sm["events"]}
    required = {"github", "supervisory", "internal", "agent_runtime"}
    assert required <= sources, f"missing event sources: {required - sources}"


def test_event_ids_are_unique(sm):
    ids = [e["id"] for e in sm["events"]]
    assert len(ids) == len(set(ids)), "duplicate event ids"


def test_transition_event_references_are_valid(sm, events):
    """Every transition's 'on' field must reference a defined event id."""
    for t in sm["transitions"]:
        event_id = _get_event(t)
        assert event_id in events, (
            f"transition {t['id']} references unknown event '{event_id}'"
        )


def test_transition_from_states_are_valid(sm, states):
    for t in sm["transitions"]:
        assert t["from"] == "any" or t["from"] in states, (
            f"transition {t['id']} has invalid from='{t['from']}'"
        )


def test_transition_to_states_are_valid(sm, states):
    for t in sm["transitions"]:
        assert t["to"] in states, f"transition {t['id']} has invalid to='{t['to']}'"


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

def test_guard_ids_are_unique(sm):
    ids = [g["id"] for g in sm["guards"]]
    assert len(ids) == len(set(ids)), "duplicate guard ids"


def test_transition_guard_references_are_valid(sm, guards):
    """Every guard referenced in a transition must be defined."""
    for t in sm["transitions"]:
        for gid in t["guard"]:
            assert gid in guards, (
                f"transition {t['id']} references undefined guard '{gid}'"
            )


def test_required_guards_exist(sm, guards):
    """The critical dispatch guards from the canonical documents must exist."""
    required = {
        "g_dependencies_resolved",
        "g_agent_active",
        "g_agent_healthy",
        "g_agent_assignable",
        "g_soul_hash_match",
        "g_no_generic_soul",
        "g_definition_of_ready_met",
        "g_wip_in_progress_ok",
        "g_required_checks_complete",
        "g_definition_of_done_met",
        "g_no_required_findings",
        "g_has_required_findings",
        "g_has_failed_checks",
        "g_is_internal_agent",
        "g_is_external_role",
        "g_is_explicitly_deferred",
        "g_exceeds_retry_threshold",
        "g_agent_wave_inactive",
        "g_dependency_issue_3_satisfied",
    }
    found = set(guards)
    assert required <= found, f"missing guards: {required - found}"


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def test_action_ids_are_unique(sm):
    ids = [a["id"] for a in sm["actions"]]
    assert len(ids) == len(set(ids)), "duplicate action ids"


def test_transition_action_references_are_valid(sm, actions):
    """Every action referenced in a transition must be defined."""
    for t in sm["transitions"]:
        for aid in t["action"]:
            assert aid in actions, (
                f"transition {t['id']} references undefined action '{aid}'"
            )


def test_actions_have_idempotent_keys(sm):
    for a in sm["actions"]:
        assert a["idempotent_key"], f"action {a['id']} missing idempotent_key"


# ---------------------------------------------------------------------------
# Dispatch policy
# ---------------------------------------------------------------------------

def test_dispatch_policy_has_wave_activation_source(sm):
    dp = sm["dispatch_policy"]
    assert dp["wave_activation_source"] == "chatgpt_supervisor"


def test_dispatch_wip_limits_match_board_manifest(sm):
    dp = sm["dispatch_policy"]
    with open(BOARD_PATH, encoding="utf-8") as fh:
        board = yaml.safe_load(fh)
    wip = board["wip_limits"]["in_progress"]
    assert dp["wip_limits"]["in_progress_global"] == wip["global"]
    assert dp["wip_limits"]["in_progress_per_agent"] == wip["per_agent"]


def test_dispatch_assignable_criteria_are_complete(sm):
    criteria = sm["dispatch_policy"]["assignable_agent_criteria"]
    required_phrases = [
        "active wave",
        "runtime registry",
        "assignable-agent",
        "health",
        "SOUL hash",
        "generic SOUL",
        "WIP",
    ]
    for phrase in required_phrases:
        assert any(phrase.lower() in c.lower() for c in criteria), (
            f"assignable_agent_criteria missing phrase: {phrase}"
        )


def test_dispatch_dependency_resolution_present(sm):
    assert "requirement" in sm["dispatch_policy"]["dependency_resolution"]


# ---------------------------------------------------------------------------
# Supervisory integration
# ---------------------------------------------------------------------------

def test_supervisory_disposition_mapping_covers_all_findings(sm):
    mapping = sm["supervisory_integration"]["disposition_mapping"]
    required = {"ACCEPTED", "READY_TO_MERGE", "REPAIR_REQUIRED", "SECURITY_FINDING"}
    assert required <= set(mapping), f"missing dispositions: {required - set(mapping)}"


def test_required_findings_interrupt_flow(sm):
    effects = sm["supervisory_integration"]["required_finding_effects"]
    assert any("interrupt" in e.lower() for e in effects)
    assert any("prioritis" in e.lower() for e in effects)


def test_required_finding_guard_routes_to_rework(sm):
    """t08 must use g_has_required_findings to route supervisory_review → rework."""
    t08 = next(t for t in sm["transitions"] if t["id"] == "t08")
    assert "g_has_required_findings" in t08["guard"]
    assert t08["from"] == "supervisory_review"
    assert t08["to"] == "rework"


def test_required_finding_guard_prevents_merge(sm):
    """t06 must require g_no_required_findings before ready_to_merge."""
    t06 = next(t for t in sm["transitions"] if t["id"] == "t06")
    assert "g_no_required_findings" in t06["guard"]


# ---------------------------------------------------------------------------
# Conflict resolution and retry policy
# ---------------------------------------------------------------------------

def test_conflict_resolution_has_branch_prefixes(sm):
    cr = sm["conflict_resolution"]
    prefixes = cr["branch_prefixes"]
    assert prefixes["hermes"] == "hermes/"
    assert prefixes["chatgpt"] == "chatgpt/"
    assert prefixes["orchestrator"] == "orchestrator/"
    assert any("force_push" in p for p in cr["merge_policy"])


def test_retry_policy_has_all_fields(sm):
    rp = sm["retry_policy"]
    for field in ("max_attempts", "backoff_strategy", "base_delay_seconds", "max_delay_seconds", "timeout_seconds"):
        assert field in rp, f"retry_policy missing: {field}"
    assert rp["max_attempts"] >= 1


def test_dead_letter_has_condition_and_action(sm):
    dl = sm["dead_letter"]
    assert "condition" in dl
    assert "action" in dl
    assert "notification_target" in dl


# ---------------------------------------------------------------------------
# Scenario coverage
# ---------------------------------------------------------------------------

def test_normal_flow_transitions_exist(sm):
    """in_progress -> pull_request -> supervisory_review -> ready_to_merge -> done."""
    transition_ids = {t["id"] for t in sm["transitions"]}
    assert {"t04", "t05", "t06", "t07"} <= transition_ids


def test_rework_scenario_exists(sm):
    to_rework = [t for t in sm["transitions"] if t["to"] == "rework"]
    from_rework = [t for t in sm["transitions"] if t["from"] == "rework"]
    assert len(to_rework) >= 1
    assert len(from_rework) >= 1


def test_block_and_recovery_scenarios_exist(sm):
    to_blocked = [t for t in sm["transitions"] if t["to"] == "blocked"]
    from_blocked = [t for t in sm["transitions"] if t["from"] == "blocked"]
    assert len(to_blocked) >= 1
    assert len(from_blocked) >= 1
    assert any(t["to"] == "backlog" for t in from_blocked)


def test_defer_and_reactivation_scenarios_exist(sm):
    to_deferred = [t for t in sm["transitions"] if t["to"] == "deferred"]
    from_deferred = [t for t in sm["transitions"] if t["from"] == "deferred"]
    assert len(to_deferred) >= 1
    assert any(t["to"] == "backlog" for t in from_deferred)


def test_dead_letter_scenario_exists(sm):
    dl_transitions = [t for t in sm["transitions"] if "act_dead_letter" in t.get("action", [])]
    assert len(dl_transitions) >= 1


def test_dependency_gated_transition_exists(sm):
    """Issue #4-style: backlog -> ready when dependency resolved."""
    dep_transitions = [
        t for t in sm["transitions"]
        if t["from"] == "backlog" and t["to"] == "ready" and _get_event(t) == "ev_dependency_resolved"
    ]
    assert len(dep_transitions) >= 1


def test_external_review_transition_exists(sm):
    ext_transitions = [t for t in sm["transitions"] if t["to"] == "external_review"]
    assert len(ext_transitions) >= 1


def test_wave_gated_transition_exists(sm):
    wave_blocked = [
        t for t in sm["transitions"]
        if t["from"] == "ready" and t["to"] == "blocked"
    ]
    assert len(wave_blocked) >= 1


# ---------------------------------------------------------------------------
# Structural integrity
# ---------------------------------------------------------------------------

def test_no_transition_targets_itself(sm):
    for t in sm["transitions"]:
        if t["from"] != "any":
            assert t["from"] != t["to"], f"transition {t['id']} loops on itself"


def test_all_states_are_reachable_from_initial(sm, states):
    """From initial_state, every non-terminal state must be reachable."""
    initial = sm["initial_state"]
    reachable = set()
    queue = [initial]

    adj = {}
    for t in sm["transitions"]:
        src = t["from"]
        if src == "any":
            for s in states:
                adj.setdefault(s, []).append(t["to"])
        else:
            adj.setdefault(src, []).append(t["to"])

    while queue:
        current = queue.pop(0)
        if current in reachable:
            continue
        reachable.add(current)
        for nxt in adj.get(current, []):
            if nxt not in reachable:
                queue.append(nxt)

    terminal = {"done", "external_review"}
    non_terminal = set(states) - terminal
    unreachable = non_terminal - reachable
    assert not unreachable, f"unreachable states: {unreachable}"


def test_kanban_mapping_covers_all_states(sm):
    mapping = {m["state"]: m["column"] for m in sm["kanban_mapping"]["column_correspondence"]}
    state_ids = {s["id"] for s in sm["states"]}
    assert set(mapping) == state_ids


def test_kanban_idempotency_key_template_uses_repo_and_issue(sm):
    key = sm["kanban_mapping"]["idempotency_key_template"]
    assert "pestoura/blitzhub-cra-navigator" in key
    assert "{{issue.number}}" in key


def test_one_card_per_issue_is_true(sm):
    assert sm["kanban_mapping"]["one_card_per_issue"] is True


def test_dispatch_approval_schema_is_present(sm):
    mapping = sm["kanban_mapping"]
    assert "dispatch_approval" in mapping
    approval = mapping["dispatch_approval"]
    assert approval["type"] == "object"
    assert {"approved_by", "approved_at_utc", "source"} <= set(approval["required"])


def test_idempotency_key_template_materializes_unique_card(sm):
    key = sm["kanban_mapping"]["idempotency_key_template"]
    assert key == "github:pestoura/blitzhub-cra-navigator:issue:{{issue.number}}"


def test_act_approve_dispatch_exists(sm, actions):
    assert "act_approve_dispatch" in actions
    action = actions["act_approve_dispatch"]
    assert "dispatch_approved" in action["effects"]
    assert "audit_recorded" in action["effects"]
    assert "approve_dispatch" in action["idempotent_key"]


def test_dispatch_requires_explicit_approval(sm, guards):
    assert guards["g_dispatch_explicitly_allowed"]["evaluation"] != "card.dispatch_allowed is True"
    assert "dispatch_approval" in guards["g_dispatch_explicitly_allowed"]["evaluation"]
    assert guards["g_dispatch_not_authorized"]["evaluation"] != "card.dispatch_allowed is not True or not supervisor_approved_recovery_scope(card)"


def test_ev_dispatch_approved_event_exists(sm, events):
    assert "ev_dispatch_approved" in {e["id"] for e in sm["events"]}


# ---------------------------------------------------------------------------
# ORCH-SUP-009 — strong one-card-per-issue enforcement
# ---------------------------------------------------------------------------

def test_legacy_card_backfill_policy_in_manifest():
    board_path = REPO_ROOT / ".blitzhub" / "board-provisioning.yaml"
    with open(board_path, encoding="utf-8") as fh:
        board = yaml.safe_load(fh)
    conventions = board.get("card_conventions", {})
    assert "idempotency_enforcement" in conventions
    text = conventions.get("idempotency_enforcement", "")
    assert "audit" in text.lower()
    assert "backfill" in text.lower()
    assert "collision" in text.lower()


# ---------------------------------------------------------------------------
# ORCH-SUP-010 — formal dependencies are required
# ---------------------------------------------------------------------------

def test_dependencies_are_required_field():
    board_path = REPO_ROOT / ".blitzhub" / "board-provisioning.yaml"
    with open(board_path, encoding="utf-8") as fh:
        board = yaml.safe_load(fh)
    required = {field["id"] for field in board["required_card_fields"]}
    assert "dependencies" in required


def test_kanban_requires_dispatch_approval():
    kanban_path = REPO_ROOT / ".blitzhub" / "kanban.yaml"
    with open(kanban_path, encoding="utf-8") as fh:
        kanban = yaml.safe_load(fh)
    required = set(kanban["required_fields"])
    assert "dispatch_approval" in required


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_all_transitions_are_deterministic(sm):
    """For a given (state, event) pair, guard sets must not be identical.

    A state machine may have multiple transitions for the same (from, event)
    pair (e.g. ev_supervisory_round from supervisory_review routes to
    ready_to_merge or rework based on guards).  The determinism requirement
    is that overlapping transitions must have different guard sets so exactly
    one applies.
    """
    from collections import defaultdict
    groups = defaultdict(list)

    for t in sm["transitions"]:
        event = _get_event(t)
        key = (t["from"], event)
        groups[key].append(t["id"])

    for (state, event), tids in groups.items():
        if len(tids) <= 1:
            continue
        guard_sets = []
        for tid in tids:
            t = next(x for x in sm["transitions"] if x["id"] == tid)
            guard_sets.append(frozenset(t["guard"]))
        for i in range(len(guard_sets)):
            for j in range(i + 1, len(guard_sets)):
                if guard_sets[i] == guard_sets[j]:
                    pytest.fail(
                        f"ambiguous transitions for ({state}, {event}): "
                        f"{tids[i]} and {tids[j]} have identical guards "
                        f"({guard_sets[i]})"
                    )


# ---------------------------------------------------------------------------
# Scenario transition simulation
# ---------------------------------------------------------------------------

# Normal flow: inbox -> backlog -> ready -> in_progress -> pull_request ->
# supervisory_review -> ready_to_merge -> done
def test_scenario_normal_flow(sim_spec):
    sm = sim_spec["state_machine"]
    transitions = sm["transitions"]
    state = "inbox"
    expected_sequence = [
        ("t01", "backlog"),
        ("t02", "ready"),
        ("t03", "in_progress"),
        ("t04", "pull_request"),
        ("t05", "supervisory_review"),
        ("t06", "ready_to_merge"),
        ("t07", "done"),
    ]
    for tid, expected_state in expected_sequence:
        t = next(t for t in transitions if t["id"] == tid)
        assert t["from"] == state
        assert t["to"] == expected_state
        state = expected_state


# Rework: required finding or failed check sends work to Rework;
# update returns to Supervisory Review.
def test_scenario_rework_flow(sim_spec):
    sm = sim_spec["state_machine"]
    transitions = sm["transitions"]
    t08 = next(t for t in transitions if t["id"] == "t08")
    t09 = next(t for t in transitions if t["id"] == "t09")
    t10 = next(t for t in transitions if t["id"] == "t10")
    assert t08["from"] == "supervisory_review"
    assert t08["to"] == "rework"
    assert "g_has_required_findings" in t08["guard"]
    assert t09["from"] == "pull_request"
    assert t09["to"] == "rework"
    assert "g_has_failed_checks" in t09["guard"]
    assert t10["from"] == "rework"
    assert t10["to"] == "supervisory_review"


# Rework from PR failure: failed checks also route to Rework.
def test_scenario_rework_from_pr_fail(sim_spec):
    sm = sim_spec["state_machine"]
    transitions = sm["transitions"]
    t09 = next(t for t in transitions if t["id"] == "t09")
    assert t09["from"] == "pull_request"
    assert t09["to"] == "rework"
    assert "g_has_failed_checks" in t09["guard"]


# Block: any state can be blocked by a real external impediment via reconciliation.
def test_scenario_block(sim_spec):
    sm = sim_spec["state_machine"]
    transitions = sm["transitions"]
    block_transitions = [
        t for t in transitions
        if t["to"] == "blocked" and t.get("on") == "ev_external_impediment_detected"
    ]
    assert block_transitions
    for t in block_transitions:
        assert t["from"] in {"backlog", "ready", "in_progress"}
        assert "g_external_impediment_present" in t["guard"]
        assert "g_not_execution_failure" in t["guard"]


# Block recovery: blocked item returns to Backlog when unblocked.
def test_scenario_block_recovery(sim_spec):
    sm = sim_spec["state_machine"]
    transitions = sm["transitions"]
    t14 = next(t for t in transitions if t["id"] == "t14")
    assert t14["from"] == "blocked"
    assert t14["to"] == "backlog"
    assert t14.get("on") == "ev_dependency_resolved"


# Defer: explicitly and reversibly defer a work item.
def test_scenario_defer(sim_spec):
    sm = sim_spec["state_machine"]
    transitions = sm["transitions"]
    t15 = next(t for t in transitions if t["id"] == "t15")
    assert t15["from"] == "any"
    assert t15["to"] == "deferred"
    assert "g_is_explicitly_deferred" in t15["guard"]


# Defer reactivation: deferred item returns to Backlog when ready again.
def test_scenario_defer_reactivate(sim_spec):
    sm = sim_spec["state_machine"]
    transitions = sm["transitions"]
    t16 = next(t for t in transitions if t["id"] == "t16")
    assert t16["from"] == "deferred"
    assert t16["to"] == "backlog"


# External review: external-role work items go directly to External Review.
def test_scenario_external_review(sim_spec):
    sm = sim_spec["state_machine"]
    transitions = sm["transitions"]
    t17 = next(t for t in transitions if t["id"] == "t17")
    assert t17["from"] == "inbox"
    assert t17["to"] == "external_review"
    assert "g_is_external_role" in t17["guard"]


# Dead-letter: retry exhaustion routes to logical dead_letter; v0.19 may map to physical Blocked.
def test_scenario_dead_letter(sim_spec):
    sm = sim_spec["state_machine"]
    transitions = sm["transitions"]
    t18 = next(t for t in transitions if t["id"] == "t18")
    assert t18["to"] == "dead_letter"
    assert "g_exceeds_retry_threshold" in t18["guard"]
    assert "act_dead_letter" in t18["action"]
    assert t18.get("on") == "ev_reconciliation_started"
    dl = next(s for s in sm["states"] if s["id"] == "dead_letter")
    assert dl["kanban_column"] == "Blocked"
    assert dl["kind"] == "terminal"


# Dependency gate: backlog -> ready when dependency resolved.
def test_scenario_dependency_gate(sim_spec):
    sm = sim_spec["state_machine"]
    transitions = sm["transitions"]
    t19 = next(t for t in transitions if t["id"] == "t19")
    assert t19["from"] == "backlog"
    assert t19["to"] == "ready"
    assert t19.get("on") == "ev_dependency_resolved"


# Wave gate: item whose owner agent's wave is inactive is blocked.
def test_scenario_wave_gate(sim_spec):
    sm = sim_spec["state_machine"]
    transitions = sm["transitions"]
    t20 = next(t for t in transitions if t["id"] == "t20")
    assert t20["from"] == "ready"
    assert t20["to"] == "blocked"
    assert "g_agent_wave_inactive" in t20["guard"]


def test_sim_spec_validates_against_schema(sim_spec):
    schema_path = REPO_ROOT / ".blitzhub" / "schemas" / "orchestrator-state-machine.yaml.schema.json"
    with open(schema_path, encoding="utf-8") as fh:
        schema = json.load(fh)
    jsonschema.Draft202012Validator(schema).validate(sim_spec)


# ---------------------------------------------------------------------------
# ORCH-SUP-001 — blocked transitions require explicit guards
# ---------------------------------------------------------------------------

def test_blocked_transitions_have_non_empty_guards(sm):
    blocked_transitions = [
        t for t in sm["transitions"] if t["to"] == "blocked"
    ]
    assert blocked_transitions, "expected transitions to blocked"
    for t in blocked_transitions:
        assert t["guard"], f"transition {t['id']} routes to blocked with empty guards"


def test_external_impediment_event_exists(sm):
    event_ids = {e["id"] for e in sm["events"]}
    assert "ev_external_impediment_detected" in event_ids


def test_external_impediment_guards_exist(sm, guards):
    required = {
        "g_external_impediment_present",
        "g_block_reason_present",
        "g_unblock_condition_present",
        "g_not_execution_failure",
    }
    assert required <= set(guards)


# ---------------------------------------------------------------------------
# ORCH-SUP-002 — execution failures are separated from dependency blocked
# ---------------------------------------------------------------------------

def test_logical_states_for_execution_failures_exist(sm):
    required = {"retry_waiting", "needs_attention", "dead_letter"}
    found = {s["id"] for s in sm["states"]}
    assert required <= found


def test_dead_letter_is_logical_state(sm):
    dl = next(s for s in sm["states"] if s["id"] == "dead_letter")
    assert dl["kind"] != "interruption"
    assert dl["kanban_column"] == "Blocked"
    bad = [
        t for t in sm["transitions"]
        if t.get("on") == "ev_reconciliation_started"
        and t["to"] == "dead_letter"
        and "g_dependencies_resolved" in t.get("guard", [])
    ]
    assert not bad, "dead_letter path must not use dependency blocked guard"


def test_runtime_compatibility_block_present(sm):
    assert "runtime_compatibility" in sm
    compat = sm["runtime_compatibility"]["hermes_v0_19"]
    assert compat["rich_transition_cli"] is False
    assert compat["active_run_cancel_cli"] is False
    assert compat["ready_auto_dispatches"] is True
    assert compat["logical_dispatch_guard_enforced"] is False
    assert compat["unblock_no_dispatch_supported"] is False


# ---------------------------------------------------------------------------
# ORCH-SUP-003 — recovery events, guards, actions and transitions
# ---------------------------------------------------------------------------

def test_recovery_events_exist(sm):
    required = {
        "ev_iteration_budget_exhausted",
        "ev_worker_lost",
        "ev_run_timed_out",
        "ev_checkpoint_available",
        "ev_recovery_scope_approved",
        "ev_retry_cooldown_elapsed",
        "ev_run_cancelled",
        "ev_auto_dispatch_detected",
    }
    event_ids = {e["id"] for e in sm["events"]}
    assert required <= event_ids


def test_recovery_guards_exist(sm, guards):
    required = {
        "g_recoverable_failure",
        "g_checkpoint_valid",
        "g_change_token_present",
        "g_no_active_run",
        "g_no_live_worker_pid",
        "g_retry_budget_available",
        "g_recovery_scope_reduced",
        "g_dispatch_explicitly_allowed",
        "g_usable_progress_present",
        "g_no_usable_progress",
        "g_active_run_or_live_pid",
        "g_dispatch_not_authorized",
    }
    assert required <= set(guards)


def test_recovery_actions_exist(sm, actions):
    required = {
        "act_capture_checkpoint",
        "act_schedule_retry",
        "act_resume_from_checkpoint",
        "act_mark_needs_attention",
        "act_cancel_active_run",
        "act_prevent_auto_dispatch",
        "act_record_recovery_event",
    }
    assert required <= set(actions)


def test_budget_exhausted_has_recovery_paths(sm):
    transitions = [
        t for t in sm["transitions"]
        if _get_event(t) == "ev_iteration_budget_exhausted"
    ]
    assert transitions, "expected recovery transitions for iteration budget exhaustion"
    targets = {t["to"] for t in transitions}
    assert "retry_waiting" in targets or "backlog" in targets


# ---------------------------------------------------------------------------
# ORCH-SUP-004 — rework -> supervisory review remediation path
# ---------------------------------------------------------------------------

def test_t10_uses_remediation_guards(sm):
    t10 = next(t for t in sm["transitions"] if t["id"] == "t10")
    assert "g_no_required_findings" not in t10["guard"]
    required = {
        "g_remediation_submitted",
        "g_required_checks_complete",
        "g_findings_in_revalidation_state",
        "g_pull_request_updated",
    }
    assert required <= set(t10["guard"])


# ---------------------------------------------------------------------------
# ORCH-SUP-005 — deterministic exclusive transitions
# ---------------------------------------------------------------------------

def test_state_event_pairs_are_exclusive(sm):
    from collections import defaultdict
    groups = defaultdict(list)
    for t in sm["transitions"]:
        key = (t["from"], _get_event(t))
        groups[key].append(t["id"])

    bad = []
    for (state, event), tids in groups.items():
        if len(tids) <= 1:
            continue
        guard_sets = []
        for tid in tids:
            t = next(x for x in sm["transitions"] if x["id"] == tid)
            guard_sets.append(frozenset(t["guard"]))
        for i in range(len(guard_sets)):
            for j in range(i + 1, len(guard_sets)):
                if guard_sets[i] == guard_sets[j]:
                    bad.append((state, event, tids[i], tids[j]))
    assert not bad, f"ambiguous transitions detected: {bad}"


# ---------------------------------------------------------------------------
# ORCH-SUP-008 — mutually exclusive budget exhaustion paths
# ---------------------------------------------------------------------------

def test_required_guards_exist(sm, guards):
    required = {
        "g_dependencies_resolved",
        "g_agent_active",
        "g_agent_healthy",
        "g_agent_assignable",
        "g_soul_hash_match",
        "g_no_generic_soul",
        "g_definition_of_ready_met",
        "g_wip_in_progress_ok",
        "g_required_checks_complete",
        "g_definition_of_done_met",
        "g_no_required_findings",
        "g_has_required_findings",
        "g_has_failed_checks",
        "g_is_internal_agent",
        "g_is_external_role",
        "g_is_explicitly_deferred",
        "g_exceeds_retry_threshold",
        "g_agent_wave_inactive",
        "g_dependency_issue_3_satisfied",
        "g_recoverable_failure",
        "g_checkpoint_valid",
        "g_change_token_present",
        "g_no_active_run",
        "g_no_live_worker_pid",
        "g_retry_budget_available",
        "g_recovery_scope_reduced",
        "g_dispatch_explicitly_allowed",
        "g_usable_progress_present",
        "g_no_usable_progress",
        "g_no_decomposition_required",
        "g_active_run_or_live_pid",
        "g_dispatch_not_authorized",
        "g_remediation_submitted",
        "g_findings_in_revalidation_state",
        "g_pull_request_updated",
        "g_auto_dispatch_scope_invalid",
        "g_auto_dispatch_unauthorized",
        "g_auto_dispatch_confirmed_contained",
    }
    assert required <= set(guards)


def test_iteration_budget_exhausted_paths_are_mutually_exclusive(sm):
    progress = next(t for t in sm["transitions"] if t["id"] == "t21")
    no_progress = next(t for t in sm["transitions"] if t["id"] == "t22")
    assert progress["from"] == "in_progress"
    assert no_progress["from"] == "in_progress"
    assert progress["to"] == "retry_waiting"
    assert no_progress["to"] == "backlog"
    assert "g_usable_progress_present" in progress["guard"]
    assert "g_no_decomposition_required" in progress["guard"]
    assert "g_no_usable_progress" in no_progress["guard"]
    progress_guard = next(g for g in sm["guards"] if g["id"] == "g_usable_progress_present")
    no_progress_guard = next(g for g in sm["guards"] if g["id"] == "g_no_usable_progress")
    assert "not g_usable_progress_present" in no_progress_guard["evaluation"]


def _recovery_context(
    *,
    checkpoint_ref,
    checkpoint_is_valid,
    change_token,
    progress_reusable,
    recovery_scope_approved,
    decomposition_required,
    active_run,
    live_pid,
    retry_budget_available=True,
    dispatch_allowed=True,
    recovery_scope_reduced=True,
):
    checkpoint_valid_flag = checkpoint_ref is not None and checkpoint_is_valid
    usable_progress = (
        checkpoint_valid_flag
        and change_token is not None
        and progress_reusable is True
        and recovery_scope_approved is True
        and decomposition_required is False
    )
    return {
        "g_recoverable_failure": True,
        "g_checkpoint_valid": checkpoint_valid_flag,
        "g_change_token_present": change_token is not None,
        "g_no_active_run": active_run is False,
        "g_no_live_worker_pid": live_pid is False,
        "g_retry_budget_available": retry_budget_available is True,
        "g_recovery_scope_reduced": recovery_scope_reduced is True,
        "g_dispatch_explicitly_allowed": dispatch_allowed is True,
        "g_usable_progress_present": usable_progress is True,
        "g_no_usable_progress": usable_progress is False,
        "g_no_decomposition_required": decomposition_required is False,
    }


def test_budget_recovery_valid_checkpoint_retry_waiting(sm):
    applicable = _applicable_transitions(
        sm,
        "in_progress",
        "ev_iteration_budget_exhausted",
        _recovery_context(
            checkpoint_ref="ck-1",
            checkpoint_is_valid=True,
            change_token="token-1",
            progress_reusable=True,
            recovery_scope_approved=True,
            decomposition_required=False,
            active_run=False,
            live_pid=False,
        ),
    )
    assert len(applicable) == 1
    assert applicable[0]["to"] == "retry_waiting"


def test_budget_recovery_invalid_checkpoint_backlog(sm):
    applicable = _applicable_transitions(
        sm,
        "in_progress",
        "ev_iteration_budget_exhausted",
        _recovery_context(
            checkpoint_ref="ck-2",
            checkpoint_is_valid=False,
            change_token="token-2",
            progress_reusable=True,
            recovery_scope_approved=True,
            decomposition_required=False,
            active_run=False,
            live_pid=False,
        ),
    )
    assert len(applicable) == 1
    assert applicable[0]["to"] == "backlog"


def test_budget_recovery_missing_checkpoint_backlog(sm):
    applicable = _applicable_transitions(
        sm,
        "in_progress",
        "ev_iteration_budget_exhausted",
        _recovery_context(
            checkpoint_ref=None,
            checkpoint_is_valid=False,
            change_token=None,
            progress_reusable=False,
            recovery_scope_approved=False,
            decomposition_required=True,
            active_run=False,
            live_pid=False,
        ),
    )
    assert len(applicable) == 1
    assert applicable[0]["to"] == "backlog"


def test_budget_recovery_decomposition_required_backlog(sm):
    applicable = _applicable_transitions(
        sm,
        "in_progress",
        "ev_iteration_budget_exhausted",
        _recovery_context(
            checkpoint_ref="ck-3",
            checkpoint_is_valid=True,
            change_token="token-3",
            progress_reusable=True,
            recovery_scope_approved=True,
            decomposition_required=True,
            active_run=False,
            live_pid=False,
        ),
    )
    assert len(applicable) == 1
    assert applicable[0]["to"] == "backlog"


def test_budget_recovery_ready_state_has_no_canonical_transitions(sm):
    applicable = _applicable_transitions(
        sm,
        "ready",
        "ev_iteration_budget_exhausted",
        _recovery_context(
            checkpoint_ref="ck-4",
            checkpoint_is_valid=True,
            change_token="token-4",
            progress_reusable=True,
            recovery_scope_approved=True,
            decomposition_required=False,
            active_run=False,
            live_pid=False,
        ),
    )
    assert len(applicable) == 0


def test_budget_recovery_active_worker_prevents_retry_or_backlog(sm):
    applicable_active = _applicable_transitions(
        sm,
        "in_progress",
        "ev_iteration_budget_exhausted",
        _recovery_context(
            checkpoint_ref="ck-5",
            checkpoint_is_valid=True,
            change_token="token-5",
            progress_reusable=True,
            recovery_scope_approved=True,
            decomposition_required=False,
            active_run=True,
            live_pid=False,
        ),
    )
    assert len(applicable_active) == 0

    applicable_pid = _applicable_transitions(
        sm,
        "in_progress",
        "ev_iteration_budget_exhausted",
        _recovery_context(
            checkpoint_ref="ck-6",
            checkpoint_is_valid=True,
            change_token="token-6",
            progress_reusable=True,
            recovery_scope_approved=True,
            decomposition_required=False,
            active_run=False,
            live_pid=True,
        ),
    )
    assert len(applicable_pid) == 0


# ---------------------------------------------------------------------------
# ORCH-SUP-009 — dead_letter is logical, not dependency blocked
# ---------------------------------------------------------------------------

def test_dead_letter_is_logical_state(sm):
    dl = next(s for s in sm["states"] if s["id"] == "dead_letter")
    assert dl["kind"] != "interruption"
    assert dl["kanban_column"] == "Blocked"
    bad = [
        t for t in sm["transitions"]
        if t.get("on") == "ev_reconciliation_started"
        and t["to"] == "dead_letter"
        and "g_dependencies_resolved" in t.get("guard", [])
    ]
    assert not bad, "dead_letter path must not use dependency blocked guard"


# ---------------------------------------------------------------------------
# ORCH-SUP-010 — containment_required two-phase auto-dispatch containment
# ---------------------------------------------------------------------------

def test_containment_required_state_exists(sm):
    state = next(s for s in sm["states"] if s["id"] == "containment_required")
    assert state["kind"] == "interruption"
    assert state["kanban_column"] == "Blocked"


def test_auto_dispatch_two_phase_containment(sm):
    active = next(t for t in sm["transitions"] if t["id"] == "t28a")
    assert active["from"] == "ready"
    assert active["to"] == "containment_required"
    assert active.get("on") == "ev_auto_dispatch_detected"
    assert "g_active_run_or_live_pid" in active["guard"]
    assert "g_dispatch_not_authorized" in active["guard"]
    assert "act_prevent_auto_dispatch" in active["action"]
    completed = next(t for t in sm["transitions"] if t["id"] == "t29")
    assert completed["from"] == "containment_required"
    assert completed["to"] == "needs_attention"
    assert completed.get("on") == "ev_run_containment_completed"
    assert "g_no_active_run" in completed["guard"]
    assert "g_no_live_worker_pid" in completed["guard"]
    assert "act_mark_needs_attention" in completed["action"]


def test_auto_dispatch_active_containment(sm):
    context = {
        "g_active_run_or_live_pid": True,
        "g_dispatch_not_authorized": True,
    }
    applicable = _applicable_transitions(sm, "ready", "ev_auto_dispatch_detected", context)
    assert len(applicable) == 1
    assert applicable[0]["to"] == "containment_required"


def test_containment_incomplete_stays(sm):
    context = {
        "g_no_active_run": True,
        "g_no_live_worker_pid": False,
    }
    applicable = _applicable_transitions(sm, "containment_required", "ev_run_containment_completed", context)
    assert len(applicable) == 0


def test_containment_completed_needs_attention(sm):
    context = {
        "g_no_active_run": True,
        "g_no_live_worker_pid": True,
    }
    applicable = _applicable_transitions(sm, "containment_required", "ev_run_containment_completed", context)
    assert len(applicable) == 1
    assert applicable[0]["to"] == "needs_attention"


# ---------------------------------------------------------------------------
# ORCH-SUP-011 — retry resume reaches in_progress, not Ready
# ---------------------------------------------------------------------------

def test_retry_resume_goes_to_in_progress(sm):
    transitions = [
        t for t in sm["transitions"]
        if _get_event(t) == "ev_retry_cooldown_elapsed" and t["from"] == "retry_waiting"
    ]
    assert transitions, "expected retry resume transitions"
    in_progress_transitions = [t for t in transitions if t["to"] == "in_progress"]
    assert in_progress_transitions, "retry resume must target in_progress"
    for t in in_progress_transitions:
        assert "act_resume_from_checkpoint" in t["action"]
    ready_transitions = [t for t in transitions if t["to"] == "ready"]
    for t in ready_transitions:
        assert "act_resume_from_checkpoint" not in t["action"]


# ---------------------------------------------------------------------------
# ORCH-SUP-012 — findings states are explicit
# ---------------------------------------------------------------------------

def test_findings_states_exist(sm):
    required = {"open", "remediation_submitted", "pending_revalidation", "accepted", "still_open_after_revalidation"}
    found = {s["id"] for s in sm.get("findings_states", [])}
    assert required <= found, f"missing findings states: {required - found}"


# ---------------------------------------------------------------------------
# ORCH-SUP-013 — v0.19 compatibility prohibits unsafe unblock workarounds
# ---------------------------------------------------------------------------

def test_v019_compatibility_prohibits_unsafe_unblock(sm):
    compat = sm["runtime_compatibility"]["hermes_v0_19"]
    workarounds = " ".join(compat.get("workarounds", [])).lower()
    prohibitions = " ".join(compat.get("prohibitions", [])).lower()
    assert "unblock -> ready" not in workarounds
    assert "unblock -> todo" not in workarounds
    assert "unblock" not in prohibitions or "pre-validated mission metadata" in prohibitions or "do not use unblock" in prohibitions
    assert compat.get("unblock_no_dispatch_supported") is False


# ---------------------------------------------------------------------------
# ORCH-SUP-014 — dead-letter uses logical state for retry exhaustion
# ---------------------------------------------------------------------------

def test_retry_exhaustion_dead_letter_target(sm):
    t25 = next(t for t in sm["transitions"] if t["id"] == "t25")
    assert t25["from"] == "retry_waiting"
    assert t25["to"] == "dead_letter"
    assert t25.get("on") == "ev_retry_cooldown_elapsed"
    assert "g_exceeds_retry_threshold" in t25["guard"]
    assert "act_dead_letter" in t25["action"]


# ---------------------------------------------------------------------------
# ORCH-SUP-015 — context-based guard evaluator
# ---------------------------------------------------------------------------

def _applicable_transitions(sm, state, event, context):
    candidates = [
        t for t in sm["transitions"]
        if (t["from"] == state or t["from"] == "any")
        and _get_event(t) == event
    ]
    return [
        t for t in candidates
        if all(context.get(guard, False) for guard in t["guard"])
    ]


def test_budget_exhaustion_with_progress_retry_waiting(sm):
    context = {
        "g_recoverable_failure": True,
        "g_checkpoint_valid": True,
        "g_change_token_present": True,
        "g_no_active_run": True,
        "g_no_live_worker_pid": True,
        "g_retry_budget_available": True,
        "g_recovery_scope_reduced": True,
        "g_dispatch_explicitly_allowed": True,
        "g_usable_progress_present": True,
        "g_no_decomposition_required": True,
    }
    applicable = _applicable_transitions(sm, "in_progress", "ev_iteration_budget_exhausted", context)
    assert len(applicable) == 1
    assert applicable[0]["to"] == "retry_waiting"


def test_budget_exhaustion_without_progress_backlog(sm):
    context = {
        "g_recoverable_failure": True,
        "g_no_active_run": True,
        "g_no_live_worker_pid": True,
        "g_no_usable_progress": True,
    }
    applicable = _applicable_transitions(sm, "in_progress", "ev_iteration_budget_exhausted", context)
    assert len(applicable) == 1
    assert applicable[0]["to"] == "backlog"


def test_retry_available_resumes_in_progress(sm):
    context = {
        "g_no_active_run": True,
        "g_no_live_worker_pid": True,
        "g_retry_budget_available": True,
        "g_checkpoint_valid": True,
        "g_dispatch_explicitly_allowed": True,
    }
    applicable = _applicable_transitions(sm, "retry_waiting", "ev_retry_cooldown_elapsed", context)
    assert len(applicable) == 1
    assert applicable[0]["to"] == "in_progress"
    assert "act_resume_from_checkpoint" in applicable[0]["action"]


def test_retry_exhausted_dead_letter(sm):
    context = {
        "g_exceeds_retry_threshold": True,
        "g_retry_budget_available": False,
    }
    applicable = _applicable_transitions(sm, "retry_waiting", "ev_retry_cooldown_elapsed", context)
    assert len(applicable) == 1
    assert applicable[0]["to"] == "dead_letter"
    assert "act_dead_letter" in applicable[0]["action"]


def test_auto_dispatch_active_containment(sm):
    context = {
        "g_active_run_or_live_pid": True,
        "g_dispatch_not_authorized": True,
    }
    applicable = _applicable_transitions(sm, "ready", "ev_auto_dispatch_detected", context)
    assert len(applicable) == 1
    assert applicable[0]["to"] == "containment_required"


def test_containment_incomplete_stays(sm):
    context = {
        "g_no_active_run": True,
        "g_no_live_worker_pid": False,
    }
    applicable = _applicable_transitions(sm, "containment_required", "ev_run_containment_completed", context)
    assert len(applicable) == 0


def test_containment_completed_needs_attention(sm):
    context = {
        "g_no_active_run": True,
        "g_no_live_worker_pid": True,
    }
    applicable = _applicable_transitions(sm, "containment_required", "ev_run_containment_completed", context)
    assert len(applicable) == 1
    assert applicable[0]["to"] == "needs_attention"


def test_findings_open_blocks_supervisory_review(sm):
    context = {
        "g_remediation_submitted": False,
        "g_required_checks_complete": True,
        "g_findings_in_revalidation_state": False,
        "g_pull_request_updated": True,
    }
    applicable = _applicable_transitions(sm, "rework", "ev_pr_updated", context)
    assert not any(t["to"] == "supervisory_review" for t in applicable)


def test_findings_remediation_submitted_allows_supervisory_review(sm):
    context = {
        "g_remediation_submitted": True,
        "g_required_checks_complete": True,
        "g_findings_in_revalidation_state": True,
        "g_pull_request_updated": True,
    }
    applicable = _applicable_transitions(sm, "rework", "ev_pr_updated", context)
    assert any(t["to"] == "supervisory_review" for t in applicable)


def test_findings_pending_revalidation_allows_supervisory_review(sm):
    context = {
        "g_remediation_submitted": True,
        "g_required_checks_complete": True,
        "g_findings_in_revalidation_state": True,
        "g_pull_request_updated": True,
    }
    applicable = _applicable_transitions(sm, "rework", "ev_pr_updated", context)
    assert any(t["to"] == "supervisory_review" for t in applicable)


def test_findings_still_open_after_revalidation_blocks_supervisory_review(sm):
    context = {
        "g_remediation_submitted": True,
        "g_required_checks_complete": True,
        "g_findings_in_revalidation_state": False,
        "g_pull_request_updated": True,
    }
    applicable = _applicable_transitions(sm, "rework", "ev_pr_updated", context)
    assert not any(t["to"] == "supervisory_review" for t in applicable)


@pytest.mark.parametrize(
    "state,event,context,expected_count",
    [
        ("in_progress", "ev_iteration_budget_exhausted", {
            "g_recoverable_failure": True,
            "g_checkpoint_valid": True,
            "g_change_token_present": True,
            "g_no_active_run": True,
            "g_no_live_worker_pid": True,
            "g_retry_budget_available": True,
            "g_recovery_scope_reduced": True,
            "g_dispatch_explicitly_allowed": True,
            "g_usable_progress_present": True,
            "g_no_decomposition_required": True,
        }, 1),
        ("in_progress", "ev_iteration_budget_exhausted", {
            "g_recoverable_failure": True,
            "g_no_active_run": True,
            "g_no_live_worker_pid": True,
            "g_no_usable_progress": True,
        }, 1),
        ("ready", "ev_iteration_budget_exhausted", {
            "g_recoverable_failure": True,
            "g_checkpoint_valid": True,
            "g_change_token_present": True,
            "g_no_active_run": True,
            "g_no_live_worker_pid": True,
            "g_retry_budget_available": True,
            "g_recovery_scope_reduced": True,
            "g_dispatch_explicitly_allowed": True,
            "g_usable_progress_present": True,
            "g_no_decomposition_required": True,
        }, 0),
        ("retry_waiting", "ev_retry_cooldown_elapsed", {
            "g_no_active_run": True,
            "g_no_live_worker_pid": True,
            "g_retry_budget_available": True,
            "g_checkpoint_valid": True,
            "g_dispatch_explicitly_allowed": True,
        }, 1),
        ("retry_waiting", "ev_retry_cooldown_elapsed", {
            "g_exceeds_retry_threshold": True,
        }, 1),
        ("ready", "ev_auto_dispatch_detected", {
            "g_active_run_or_live_pid": True,
            "g_dispatch_not_authorized": True,
        }, 1),
        ("in_progress", "ev_auto_dispatch_detected", {
            "g_active_run_or_live_pid": True,
            "g_dispatch_not_authorized": True,
        }, 1),
        ("containment_required", "ev_run_containment_completed", {
            "g_no_active_run": True,
            "g_no_live_worker_pid": True,
        }, 1),
        ("containment_required", "ev_run_containment_completed", {
            "g_no_active_run": True,
            "g_no_live_worker_pid": False,
        }, 0),
    ],
)
def test_applicable_transitions_are_unique(state, event, context, expected_count, sm):
    applicable = _applicable_transitions(sm, state, event, context)
    assert len(applicable) == expected_count


# ---------------------------------------------------------------------------
# ORCH-SUP-006 — v0.19 compatibility coverage
# ---------------------------------------------------------------------------

def test_runtime_compatibility_fields_present(sm):
    compat = sm["runtime_compatibility"]["hermes_v0_19"]
    required = {
        "rich_transition_cli",
        "active_run_cancel_cli",
        "ready_auto_dispatches",
        "logical_dispatch_guard_enforced",
        "unblock_no_dispatch_supported",
        "physical_to_logical_mapping",
        "workarounds",
        "prohibitions",
    }
    assert required <= set(compat)


# ---------------------------------------------------------------------------
# ORCH-SUP-007 — CI target executes the state machine suite
# ---------------------------------------------------------------------------

def test_ci_workflow_executes_state_machine_suite():
    workflow = REPO_ROOT / ".github" / "workflows" / "validate-governance.yml"
    assert workflow.exists()
    text = workflow.read_text(encoding="utf-8")
    assert "pytest" in text
    assert "orchestrator_state_machine_test.py" in text

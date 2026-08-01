# Local Validation and Reproduction Guide

This document explains how maintainers and autonomous agents can run the
BlitzHub CRA Navigator governance validator locally and reproduce CI failures.

## Prerequisites

- Python 3.11+ (tested with 3.12 and 3.13)
- PyYAML and pytest (installed automatically in CI)

## Quick start

```bash
cd /path/to/blitzhub-cra-navigator

# Option A: run the validator directly (no test framework needed)
python3 scripts/validate_governance.py

# Option B: run the full test suite (positive + negative fixtures)
python3 -m pytest tests/test_governance_validator.py -v -p no:cacheprovider
```

## What the validator checks

The validator (`scripts/validate_governance.py`) performs seven layers of
validation using a **real YAML parser** (PyYAML `safe_load`), not text search:

1. **Required file existence** — verifies all manifests, contracts, prompts,
   SOUL files and documentation exist and are non-empty.

2. **YAML parsing** — parses every manifest with PyYAML. Syntax errors are
   reported with the parser's error message, including the file path.

3. **Structural schema validation** — checks required top-level keys and
   nested keys for each manifest (e.g., `project.id`, `board.columns`).

4. **Cross-manifest reference validation**:
   - Agent IDs in `agents/provisioning.yaml`, `.blitzhub/agents.yaml`,
     `orchestration.yaml` and `board-provisioning.yaml` must exist in
     `agent-waves.yaml` or `agents.yaml`.
   - Wave IDs must be defined in `agent-waves.yaml`.
   - Kanban states in `work_item_flow` must match board columns.
   - Backlog `owner_agent` values must reference a defined agent or external role.
   - File paths referenced by manifests (`definition`, `prompt`,
     `soul_source`, `common_contract`) must exist on disk.
   - `initial_issue` fields must be integers.

5. **SOUL validation** (Issue #12):
   - Exactly five `*.SOUL.md` files in `agents/souls/`.
   - No file contains the generic Hermes signature
     (`"You are Hermes Agent, an AI assistant created by Nous Research"`).
   - Each SOUL is at least 200 characters (substantive, not a stub).
   - SHA-256 hashes are computed and written to
     `supervisory-runs/bootstrap/agents/soul-hashes.json` for runtime
     hash-match verification.

6. **Secret and prohibited-file detection**:
   - Scans all repository files for AWS keys, GitHub tokens, private keys,
     Slack tokens, and generic API key assignment patterns.
   - Flags prohibited filenames (`.env`, `id_rsa`, etc.) and extensions
     (`.exe`, `.dll`, `.so`, etc.).
   - Verifies `.gitignore` covers `.env`, `__pycache__`, and `*.pyc`.

7. **GitHub Actions workflow audit**:
   - Every workflow must declare an explicit `permissions` block.
   - No workflow may use `pull_request_target` to execute untrusted code.
   - All `uses:` references must be pinned with a version (e.g., `@v4`).
   - Each permission must be `read`, `none`, or `write`.

## Reproducing failures locally

### Missing required file

```bash
# Simulate a missing file
rm .blitzhub/project.yaml
python3 scripts/validate_governance.py
# Expected: "[.blitzhub/project.yaml] field 'file_existence': expected present on disk, got absent"
```

### Invalid YAML syntax

```bash
# Introduce a syntax error
echo "  - this is: not: valid: yaml: here" >> .blitzhub/agent-waves.yaml
python3 scripts/validate_governance.py
# Expected: "[.blitzhub/agent-waves.yaml] field 'yaml': expected syntactically valid YAML, got '...'
```

### Invalid agent reference

Edit `agents/provisioning.yaml` and add an agent whose `id` does not appear
in `agent-waves.yaml` or `agents.yaml`:

```yaml
- id: phantom-agent
  runtime_name: blitzhub-phantom
  wave: wave-1
  ...
```

```bash
python3 scripts/validate_governance.py
# Expected: "[agents/provisioning.yaml[agents[5]]] field 'id': expected an agent ID defined in ..., got 'phantom-agent'"
```

### Generic SOUL detected

```bash
echo "You are Hermes Agent, an intelligent AI assistant created by Nous Research." \
  > agents/souls/phantom.SOUL.md
python3 scripts/validate_governance.py
# Expected: "[agents/souls/phantom.SOUL.md] field 'content': expected does not contain the generic Hermes signature, got 'generic signature found'"
```

## Running tests

The test suite at `tests/test_governance_validator.py` uses pytest and
includes both positive and negative fixtures. Each negative fixture copies
the repository to a temporary directory, introduces a deliberate defect, and
asserts that the validator produces a specific, actionable failure.

```bash
python3 -m pytest tests/test_governance_validator.py -v -p no:cacheprovider
```

To run without pytest (limited to tests that don't require temp directories):

```bash
python3 tests/test_governance_validator.py
```

## CI behaviour

The GitHub Actions workflow at `.github/workflows/validate-governance.yml`
runs on every pull request and push to `main`. It uses:

- `permissions: contents: read` (minimum scope)
- `actions/checkout@v4` and `actions/setup-python@v5` (pinned actions)
- `pull_request` trigger (never `pull_request_target`, which would execute
  untrusted fork code with the base branch token)

The workflow runs three validation layers:
1. governance manifest validation via `scripts/validate_governance.py`;
2. governance validator tests via `tests/test_governance_validator.py`;
3. orchestrator state machine contract tests via `tests/orchestrator_state_machine_test.py`.

The workflow is separate from any release/deployment workflow and cannot
expose secrets to forks.

## Adding new manifests

When adding a new YAML manifest:

1. Add it to the `REQUIRED_FILES` tuple in `scripts/validate_governance.py`
   if it is a required file.
2. Add it to the `yaml_files` list in `check_yaml_parsing()` if it should
   be parsed and cross-referenced.
3. Add structural schema checks in `validate_schemas()` if it has a known
   schema.
4. Add cross-reference checks in `validate_cross_references()` if it
   references other manifests.
5. Add a positive fixture (modify the real manifest and verify it passes).
6. Add a negative fixture (introduce a defect and verify the validator
   catches it).
7. Add a test case to `tests/test_governance_validator.py`.

## Dependency notes

The validator uses **only the Python standard library plus PyYAML**. No
third-party packages beyond `pyyaml` are required. `jsonschema` and
`pytest` are only needed for the test suite, which CI installs separately.

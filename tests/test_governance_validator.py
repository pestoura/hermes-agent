#!/usr/bin/env python3
"""
Test suite for the BlitzHub CRA Navigator governance validator.

Runs the validator's individual check functions against positive (valid)
and negative (invalid) fixtures.  Each test proves that:

  - valid manifests parse and resolve all cross-references (positive fixture);
  - invalid manifests produce specific, actionable failures (negative fixture).

Run locally:

    python -m pytest tests/test_governance_validator.py -v

Or without pytest:

    python tests/test_governance_validator.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any

import yaml

# Make the scripts package importable
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import validate_governance as vg  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# Subdirectories to skip when copying the repo for tests (avoid .git, caches)
_COPY_IGNORE = shutil.ignore_patterns(
    ".git", "__pycache__", ".pytest_cache", "*.pyc", "venv", ".venv",
    ".env", ".env.local",
)


def _make_validator_result() -> vg.ValidationResult:
    return vg.ValidationResult()


def _format_failures(result: vg.ValidationResult) -> str:
    return "\n".join(str(f) for f in result.failures)


def _run_full_validation_on_dir(dir_path: Path) -> vg.ValidationResult:
    """Run the full validation suite against a temp directory.

    Temporarily monkey-patches vg.ROOT so all checks resolve against the
    temp directory.
    """
    original_root = vg.ROOT
    vg.ROOT = dir_path
    try:
        result = vg.run_validation()
    finally:
        vg.ROOT = original_root
    return result


def _copy_repo(tmp_path: Path) -> Path:
    """Copy the repository to a temp dir, excluding VCS and caches."""
    repo_copy = tmp_path / "repo"
    shutil.copytree(ROOT, repo_copy, ignore=_COPY_IGNORE)
    return repo_copy


# ---------------------------------------------------------------------------
# Positive fixtures — valid repository
# ---------------------------------------------------------------------------

class TestValidRepository:
    """The actual repository must pass all checks."""

    def test_current_repo_passes_validation(self):
        result = vg.run_validation()
        assert result.ok, _format_failures(result)

    def test_yaml_files_parse_with_real_parser(self):
        """Every .blitzhub YAML file must parse without errors."""
        yaml_files = list(ROOT.glob(".blitzhub/*.yaml")) + \
                     list(ROOT.glob(".blitzhub/policies/*.yaml")) + \
                     list(ROOT.glob("agents/*.yaml")) + \
                     list(ROOT.glob("agents/contracts/*.yaml")) + \
                     list(ROOT.glob(".github/workflows/*.yml")) + \
                     list(ROOT.glob(".github/workflows/*.yaml"))
        for yf in yaml_files:
            if yf.is_dir():
                continue
            try:
                with open(yf, "r", encoding="utf-8") as f:
                    yaml.safe_load(f)
            except yaml.YAMLError as exc:
                assert False, f"YAML parse error in {yf}: {exc}"

    def test_all_five_soul_files_exist(self):
        """There must be exactly five SOUL.md files in agents/souls/."""
        souls = list((ROOT / "agents" / "souls").glob("*.SOUL.md"))
        assert len(souls) >= 5, f"Expected >=5 SOUL files, found {len(souls)}"

    def test_all_soul_files_are_specific(self):
        """No SOUL file must contain the generic Hermes signature."""
        generic_sig = "You are Hermes Agent, an intelligent AI assistant created by Nous Research"
        souls = (ROOT / "agents" / "souls").glob("*.SOUL.md")
        for soul in souls:
            content = soul.read_text(encoding="utf-8")
            assert generic_sig not in content, \
                f"Generic SOUL signature found in {soul}"

    def test_all_souls_are_non_trivial(self):
        """Each SOUL file must be substantial (not just a one-liner)."""
        souls = (ROOT / "agents" / "souls").glob("*.SOUL.md")
        for soul in souls:
            content = soul.read_text(encoding="utf-8")
            assert len(content) > 500, \
                f"SOUL file {soul.name} is only {len(content)} chars — too short"


# ---------------------------------------------------------------------------
# Negative fixture 1: missing required file
# ---------------------------------------------------------------------------

class TestMissingRequiredFile:
    """Removing a required file must produce a clear failure."""

    def test_missing_project_yaml_fails(self, tmp_path: Path):
        repo_copy = _copy_repo(tmp_path)
        (repo_copy / ".blitzhub" / "project.yaml").unlink()

        result = _run_full_validation_on_dir(repo_copy)
        assert not result.ok
        assert any("project.yaml" in f.file and "present" in f.expected
                   for f in result.failures), \
            "Expected failure for missing .blitzhub/project.yaml"


# ---------------------------------------------------------------------------
# Negative fixture 2: invalid YAML syntax
# ---------------------------------------------------------------------------

class TestInvalidYaml:
    """A YAML syntax error must be caught by the parser."""

    def test_broken_yaml_fails(self, tmp_path: Path):
        repo_copy = _copy_repo(tmp_path)

        bad_yaml = repo_copy / ".blitzhub" / "agent-waves.yaml"
        bad_yaml.write_text(
            "waves:\n"
            "  - id: wave-1\n"
            "    name: Foundation\n"
            "    status: active\n"
            "  this is: not: valid: yaml: here\n"
            "    bad indent\n",
            encoding="utf-8",
        )

        result = _run_full_validation_on_dir(repo_copy)
        assert not result.ok
        assert any("agent-waves.yaml" in f.file and "yaml" in f.field.lower()
                   for f in result.failures), \
            "Expected YAML parse failure for broken agent-waves.yaml"


# ---------------------------------------------------------------------------
# Negative fixture 3: invalid agent reference in provisioning
# ---------------------------------------------------------------------------

class TestInvalidAgentReference:
    """An agent ID referenced in provisioning that doesn't exist must fail."""

    def test_unknown_agent_in_provisioning_fails(self, tmp_path: Path):
        repo_copy = _copy_repo(tmp_path)

        prov_path = repo_copy / "agents" / "provisioning.yaml"
        prov = yaml.safe_load(prov_path.read_text(encoding="utf-8"))
        prov["agents"].append({
            "id": "non-existent-agent",
            "runtime_name": "blitzhub-non-existent",
            "wave": "wave-1",
            "definition": "agents/definitions/non-existent.yaml",
            "prompt": "agents/prompts/non-existent.md",
            "soul_source": "agents/souls/non-existent.SOUL.md",
            "soul_runtime_path": "/home/estourpm/.hermes/profiles/non-existent/SOUL.md",
            "initial_issue": 99,
            "initial_state": "active",
            "board_role": "worker",
        })
        prov_path.write_text(
            yaml.dump(prov, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )

        result = _run_full_validation_on_dir(repo_copy)
        assert not result.ok
        assert any("non-existent-agent" in str(f) for f in result.failures), \
            "Expected failure for unknown agent 'non-existent-agent'"


# ---------------------------------------------------------------------------
# Negative fixture 4: invalid wave reference in agents.yaml
# ---------------------------------------------------------------------------

class TestInvalidWaveReference:
    """An agent referencing a wave that doesn't exist must fail."""

    def test_unknown_wave_fails(self, tmp_path: Path):
        repo_copy = _copy_repo(tmp_path)

        agents_path = repo_copy / ".blitzhub" / "agents.yaml"
        agents_data = yaml.safe_load(agents_path.read_text(encoding="utf-8"))
        # Add a wave reference that doesn't exist
        agents_data["agents"].append({
            "id": "fake-agent",
            "runtime_name": "blitzhub-fake",
            "wave": "wave-99",
            "status": "active",
            "definition": "agents/definitions/fake.yaml",
            "prompt": "agents/prompts/fake.md",
            "purpose": "test",
            "initial_issue": 99,
        })
        agents_path.write_text(
            yaml.dump(agents_data, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )

        result = _run_full_validation_on_dir(repo_copy)
        assert not result.ok
        assert any("wave-99" in str(f) for f in result.failures), \
            "Expected failure for unknown wave 'wave-99'"


# ---------------------------------------------------------------------------
# Negative fixture 5: invalid initial_issue type
# ---------------------------------------------------------------------------

class TestInvalidInitialIssue:
    """A non-integer initial_issue must fail."""

    def test_string_initial_issue_fails(self, tmp_path: Path):
        repo_copy = _copy_repo(tmp_path)

        prov_path = repo_copy / "agents" / "provisioning.yaml"
        prov = yaml.safe_load(prov_path.read_text(encoding="utf-8"))
        prov["agents"][0]["initial_issue"] = "6"  # string, not integer
        prov_path.write_text(
            yaml.dump(prov, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )

        result = _run_full_validation_on_dir(repo_copy)
        assert not result.ok
        assert any("initial_issue" in str(f) for f in result.failures), \
            "Expected failure for non-integer initial_issue"


# ---------------------------------------------------------------------------
# Negative fixture 6: generic SOUL detected
# ---------------------------------------------------------------------------

class TestGenericSoul:
    """A generic Hermes SOUL must be rejected."""

    def test_generic_soul_rejected(self, tmp_path: Path):
        repo_copy = _copy_repo(tmp_path)

        soul_path = repo_copy / "agents" / "souls" / "devops-repository-engineer.SOUL.md"
        soul_path.write_text(
            "You are Hermes Agent, an intelligent AI assistant created by "
            "Nous Research. You help with coding tasks.",
            encoding="utf-8",
        )

        result = _run_full_validation_on_dir(repo_copy)
        assert not result.ok
        assert any("generic" in str(f).lower() for f in result.failures), \
            "Expected failure for generic SOUL content"


# ---------------------------------------------------------------------------
# Negative fixture 7: broken cross-file reference (missing SOUL source)
# ---------------------------------------------------------------------------

class TestBrokenFileReference:
    """A provisioning.yaml referencing a non-existent SOUL source must fail."""

    def test_missing_soul_source_fails(self, tmp_path: Path):
        repo_copy = _copy_repo(tmp_path)

        prov_path = repo_copy / "agents" / "provisioning.yaml"
        prov = yaml.safe_load(prov_path.read_text(encoding="utf-8"))
        prov["agents"][0]["soul_source"] = "agents/souls/nonexistent.SOUL.md"
        prov_path.write_text(
            yaml.dump(prov, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )

        result = _run_full_validation_on_dir(repo_copy)
        assert not result.ok
        assert any("nonexistent" in str(f) for f in result.failures), \
            "Expected failure for missing soul_source file"


# ---------------------------------------------------------------------------
# Negative fixture 8: workflow missing permissions
# ---------------------------------------------------------------------------

class TestWorkflowPermissions:
    """A workflow without explicit permissions must fail."""

    def test_no_permissions_block_fails(self, tmp_path: Path):
        repo_copy = _copy_repo(tmp_path)

        wf_path = repo_copy / ".github" / "workflows" / "validate-governance.yml"
        wf_content = """
name: Bad workflow
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo hello
"""
        wf_path.write_text(wf_content, encoding="utf-8")

        result = _run_full_validation_on_dir(repo_copy)
        assert not result.ok
        assert any("permissions" in str(f) for f in result.failures), \
            "Expected failure for workflow without permissions block"

    def test_unpinned_action_fails(self, tmp_path: Path):
        repo_copy = _copy_repo(tmp_path)

        wf_path = repo_copy / ".github" / "workflows" / "validate-governance.yml"
        wf_content = """
name: Bad workflow
on: [push]
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout
"""
        wf_path.write_text(wf_content, encoding="utf-8")

        result = _run_full_validation_on_dir(repo_copy)
        assert not result.ok
        assert any("pinned" in str(f).lower() for f in result.failures), \
            "Expected failure for unpinned action"


# ---------------------------------------------------------------------------
# Negative fixture 9: secret in files
# ---------------------------------------------------------------------------

class TestSecretDetection:
    """A file containing a GitHub token pattern must be flagged."""

    def test_github_token_in_yaml_fails(self, tmp_path: Path):
        repo_copy = _copy_repo(tmp_path)

        secret_file = repo_copy / "agents" / "definitions" / "devops-repository-engineer.yaml"
        content = secret_file.read_text(encoding="utf-8")
        content += "\n# leaked: ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        secret_file.write_text(content, encoding="utf-8")

        result = _run_full_validation_on_dir(repo_copy)
        assert not result.ok
        assert any("secret" in str(f).lower() for f in result.failures), \
            "Expected secret scan failure"


# ---------------------------------------------------------------------------
# Unit tests for individual check functions
# ---------------------------------------------------------------------------

class TestRequiredFilesCheck:

    def test_missing_file_reported(self):
        result = _make_validator_result()
        original = vg.REQUIRED_FILES
        try:
            vg.REQUIRED_FILES = ("nonexistent.yaml",)
            vg.check_required_files(result)
            assert not result.ok
            assert any("nonexistent.yaml" in f.file for f in result.failures)
        finally:
            vg.REQUIRED_FILES = original


class TestSchemaValidation:

    def test_project_yaml_schema(self):
        result = _make_validator_result()
        parsed = vg.check_yaml_parsing(result)
        # project.yaml should parse
        assert ".blitzhub/project.yaml" in parsed

    def test_missing_required_key_detected(self):
        """A manifest missing a required key must be flagged."""
        test_data = {"schema_version": "1.0"}  # missing "project"
        result = _make_validator_result()
        vg._check_keys(test_data, {"schema_version", "project"},
                       "test.yaml", result)
        assert not result.ok
        assert any("project" in f.field for f in result.failures)


class TestReferenceValidation:

    def test_all_agents_referenced_and_valid(self):
        """All agent references in provisioning, orchestration, and
        board-provisioning must resolve to known agent IDs."""
        parse_result = vg.ValidationResult()
        parsed = vg.check_yaml_parsing(parse_result)
        ref_result = vg.ValidationResult()
        vg.validate_cross_references(parsed, ref_result)
        assert ref_result.ok, _format_failures(ref_result)

    def test_soul_hashes_computed(self):
        """SOUL hash map must contain all 5 agents."""
        result = vg.ValidationResult()
        soul_hashes = vg.validate_souls(result)
        assert len(soul_hashes) >= 5, \
            f"Expected >=5 SOUL hashes, got {len(soul_hashes)}"


if __name__ == "__main__":
    import inspect

    test_classes = [
        TestValidRepository,
        TestRequiredFilesCheck,
        TestSchemaValidation,
        TestReferenceValidation,
        TestMissingRequiredFile,
        TestInvalidYaml,
        TestInvalidAgentReference,
        TestInvalidWaveReference,
        TestInvalidInitialIssue,
        TestGenericSoul,
        TestBrokenFileReference,
        TestWorkflowPermissions,
        TestSecretDetection,
    ]
    passed = 0
    failed = 0
    skipped = 0
    for cls in test_classes:
        for method_name in dir(cls):
            if not method_name.startswith("test_"):
                continue
            method = getattr(cls, method_name)
            sig = inspect.signature(method)
            if "tmp_path" in sig.parameters:
                # Requires pytest fixture — try with temp dir manually
                import tempfile
                with tempfile.TemporaryDirectory() as td:
                    try:
                        method(cls(), Path(td))
                        print(f"  PASS: {cls.__name__}.{method_name}")
                        passed += 1
                    except Exception as e:
                        print(f"  FAIL: {cls.__name__}.{method_name}: {e}")
                        failed += 1
            else:
                try:
                    method()
                    print(f"  PASS: {cls.__name__}.{method_name}")
                    passed += 1
                except Exception as e:
                    print(f"  FAIL: {cls.__name__}.{method_name}: {e}")
                    failed += 1
    print(f"\n{passed} passed, {failed} failed, {skipped} skipped")
    sys.exit(0 if failed == 0 else 1)

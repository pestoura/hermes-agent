#!/usr/bin/env python3
"""Validate BlitzHub governance with a stable importable API.

The CLI and the test suite use the same validation path.  The module keeps the
public API expected by the repository tests while validating the current
hourly supervisory policy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
import re
import sys
from typing import Any, Iterable

import yaml


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = (
    ".blitzhub/project.yaml",
    ".blitzhub/bootstrap.yaml",
    ".blitzhub/agent-waves.yaml",
    ".blitzhub/agents.yaml",
    ".blitzhub/orchestration.yaml",
    ".blitzhub/kanban.yaml",
    ".blitzhub/quality-gates.yaml",
    ".blitzhub/definition-of-ready.yaml",
    ".blitzhub/definition-of-done.yaml",
    ".blitzhub/initial-backlog.yaml",
    ".blitzhub/policies/source-policy.yaml",
    ".blitzhub/policies/visual-assets-policy.yaml",
    ".blitzhub/policies/supervisory-policy.yaml",
    ".blitzhub/policies/public-repository-policy.yaml",
    "BOOTSTRAP_DIRECTIVE.md",
    "docs/product/vision.md",
    "docs/architecture/orchestrator.md",
)

REQUIRED_MARKERS = {
    ".blitzhub/project.yaml": ("canonical_source: github", "chatgpt:"),
    ".blitzhub/agent-waves.yaml": ("wave-1", "wave-2", "wave-3"),
    ".blitzhub/orchestration.yaml": (
        "source_of_truth: github",
        "direct_main_writes: forbidden",
    ),
    ".blitzhub/policies/source-policy.yaml": (
        "primary_required_for_product_rules: true",
    ),
    ".blitzhub/policies/visual-assets-policy.yaml": (
        "authority: chatgpt-supervisor",
    ),
    ".blitzhub/policies/supervisory-policy.yaml": ("cadence_hours: 1",),
}

SOUL_IDS = (
    "cra-product-orchestrator",
    "regulatory-research-engineer",
    "requirements-traceability-engineer",
    "solution-architect",
    "devops-repository-engineer",
)

GENERIC_SOUL_SIGNATURE = (
    "You are Hermes Agent, an intelligent AI assistant created by Nous Research"
)

SECRET_PATTERNS = (
    ("GitHub token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("fine-grained GitHub token", re.compile(r"github_pat_[A-Za-z0-9_]{60,}")),
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----")),
)


@dataclass(frozen=True, slots=True)
class ValidationFailure:
    file: str
    field: str
    expected: str
    actual: str | None = None

    def __str__(self) -> str:
        message = f"{self.file}: {self.field} expected {self.expected}"
        if self.actual is not None:
            message += f"; actual={self.actual}"
        return message


@dataclass(slots=True)
class ValidationResult:
    failures: list[ValidationFailure] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures

    def add(
        self,
        file: str,
        field: str,
        expected: str,
        actual: str | None = None,
    ) -> None:
        self.failures.append(
            ValidationFailure(
                file=file,
                field=field,
                expected=expected,
                actual=actual,
            )
        )


def _relative(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _check_keys(
    data: Any,
    required_keys: Iterable[str],
    file: str,
    result: ValidationResult,
) -> None:
    if not isinstance(data, dict):
        result.add(file, "root", "a YAML mapping", type(data).__name__)
        return
    for key in required_keys:
        if key not in data:
            result.add(file, key, "present")


def check_required_files(result: ValidationResult) -> None:
    for relative_path in REQUIRED_FILES:
        path = ROOT / relative_path
        if not path.is_file():
            result.add(relative_path, "file", "present")
        elif path.stat().st_size == 0:
            result.add(relative_path, "file", "non-empty", "empty")


def _yaml_paths() -> list[Path]:
    patterns = (
        ".blitzhub/*.yaml",
        ".blitzhub/policies/*.yaml",
        "agents/*.yaml",
        "agents/definitions/*.yaml",
        "agents/contracts/*.yaml",
        ".github/workflows/*.yml",
        ".github/workflows/*.yaml",
    )
    paths: set[Path] = set()
    for pattern in patterns:
        paths.update(path for path in ROOT.glob(pattern) if path.is_file())
    return sorted(paths)


def check_yaml_parsing(result: ValidationResult) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for path in _yaml_paths():
        relative_path = _relative(path)
        try:
            parsed[relative_path] = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            result.add(relative_path, "yaml", "valid YAML", str(exc))
    return parsed


def _known_waves(parsed: dict[str, Any]) -> set[str]:
    document = parsed.get(".blitzhub/agent-waves.yaml") or {}
    waves = document.get("waves", []) if isinstance(document, dict) else []
    return {
        wave.get("id")
        for wave in waves
        if isinstance(wave, dict) and isinstance(wave.get("id"), str)
    }


def _check_path_reference(
    owner_file: str,
    owner_id: str,
    field_name: str,
    value: Any,
    result: ValidationResult,
) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not value:
        result.add(owner_file, f"{owner_id}.{field_name}", "a non-empty path")
        return
    if not (ROOT / value).is_file():
        result.add(
            owner_file,
            f"{owner_id}.{field_name}",
            f"existing file '{value}'",
            "missing",
        )


def _check_initial_issue(
    owner_file: str,
    owner_id: str,
    value: Any,
    result: ValidationResult,
) -> None:
    if value is not None and not isinstance(value, int):
        result.add(
            owner_file,
            f"{owner_id}.initial_issue",
            "integer",
            type(value).__name__,
        )


def _validate_workflow(relative_path: str, result: ValidationResult) -> None:
    path = ROOT / relative_path
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError:
        return

    if not isinstance(document, dict) or "permissions" not in document:
        result.add(relative_path, "permissions", "explicit permissions block")

    for match in re.finditer(r"(?m)^\s*-?\s*uses:\s*([^\s#]+)", text):
        action = match.group(1)
        if "@" not in action or action.endswith("@"):
            result.add(
                relative_path,
                "uses",
                "action pinned with an @ reference",
                action,
            )


def validate_cross_references(
    parsed: dict[str, Any], result: ValidationResult
) -> None:
    agents_document = parsed.get(".blitzhub/agents.yaml") or {}
    agents = agents_document.get("agents", []) if isinstance(agents_document, dict) else []
    known_agent_ids = {
        agent.get("id")
        for agent in agents
        if isinstance(agent, dict) and isinstance(agent.get("id"), str)
    }
    waves = _known_waves(parsed)

    for agent in agents:
        if not isinstance(agent, dict):
            continue
        agent_id = str(agent.get("id", "<unknown>"))
        wave = agent.get("wave")
        if wave is not None and wave not in waves:
            result.add(
                ".blitzhub/agents.yaml",
                f"{agent_id}.wave",
                f"one of {sorted(waves)}",
                str(wave),
            )
        _check_initial_issue(
            ".blitzhub/agents.yaml", agent_id, agent.get("initial_issue"), result
        )
        for field_name in ("definition", "prompt"):
            _check_path_reference(
                ".blitzhub/agents.yaml",
                agent_id,
                field_name,
                agent.get(field_name),
                result,
            )

    provisioning_document = parsed.get("agents/provisioning.yaml") or {}
    provisioning_agents = (
        provisioning_document.get("agents", [])
        if isinstance(provisioning_document, dict)
        else []
    )
    for agent in provisioning_agents:
        if not isinstance(agent, dict):
            continue
        agent_id = str(agent.get("id", "<unknown>"))
        if agent_id not in known_agent_ids:
            result.add(
                "agents/provisioning.yaml",
                f"agent.{agent_id}",
                "agent id declared in .blitzhub/agents.yaml",
                agent_id,
            )
        wave = agent.get("wave")
        if wave is not None and wave not in waves:
            result.add(
                "agents/provisioning.yaml",
                f"{agent_id}.wave",
                f"one of {sorted(waves)}",
                str(wave),
            )
        _check_initial_issue(
            "agents/provisioning.yaml", agent_id, agent.get("initial_issue"), result
        )
        for field_name in ("definition", "prompt", "soul_source"):
            _check_path_reference(
                "agents/provisioning.yaml",
                agent_id,
                field_name,
                agent.get(field_name),
                result,
            )

    _validate_workflow(".github/workflows/validate-governance.yml", result)


def validate_souls(result: ValidationResult) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for agent_id in SOUL_IDS:
        relative_path = f"agents/souls/{agent_id}.SOUL.md"
        path = ROOT / relative_path
        if not path.is_file():
            result.add(relative_path, "file", "present")
            continue
        content = path.read_text(encoding="utf-8")
        if GENERIC_SOUL_SIGNATURE in content:
            result.add(
                relative_path,
                "soul",
                "role-specific content without generic Hermes signature",
                "generic signature found",
            )
        hashes[agent_id] = sha256(path.read_bytes()).hexdigest()
    return hashes


def validate_required_markers(result: ValidationResult) -> None:
    for relative_path, markers in REQUIRED_MARKERS.items():
        path = ROOT / relative_path
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                result.add(relative_path, "marker", f"contains '{marker}'")


def scan_secrets(result: ValidationResult) -> None:
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts or "tests" in path.parts:
            continue
        if path.stat().st_size > 1_000_000:
            continue
        if path.suffix.lower() in {
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".ico",
            ".pdf",
            ".zip",
        }:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(content):
                result.add(
                    _relative(path),
                    "secret",
                    f"no potential {label}",
                    "pattern detected",
                )


def run_validation() -> ValidationResult:
    result = ValidationResult()
    check_required_files(result)
    parsed = check_yaml_parsing(result)
    validate_cross_references(parsed, result)
    validate_souls(result)
    validate_required_markers(result)
    scan_secrets(result)
    return result


def main() -> int:
    result = run_validation()
    if not result.ok:
        print("Governance validation failed:")
        for failure in result.failures:
            print(f"- {failure}")
        return 1

    print(f"Governance validation passed: {len(REQUIRED_FILES)} required files checked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

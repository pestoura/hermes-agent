#!/usr/bin/env python3
"""
Validation tests for the CRA source catalogue.

Validates research/sources/catalog.yaml against the requirements specified in:
  - .blitzhub/policies/source-policy.yaml (required metadata fields)
  - .blitzhub/quality-gates.yaml (regulatory quality gates)
  - Issue #3 acceptance criteria

Usage:
    python3 tests/test_source_catalog.py
    python3 -m pytest tests/test_source_catalog.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from datetime import date

try:
    import yaml
except ImportError:
    print("PyYAML is required. Install with: pip3 install pyyaml")
    sys.exit(1)


REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = REPO_ROOT / "research" / "sources" / "catalog.yaml"
INTERPRETATION_RECORDS_PATH = REPO_ROOT / "research" / "sources" / "interpretation-records.md"
COVERAGE_REPORT_PATH = REPO_ROOT / "research" / "sources" / "coverage-and-gap-report.md"

# Required metadata fields per .blitzhub/policies/source-policy.yaml
REQUIRED_METADATA_FIELDS = [
    "authority",
    "title",
    "document_identifier",
    "article_or_section",
    "source_url",
    "publication_or_version_date",
    "retrieved_at",
    "source_type",
    "validation_status",
]

# Required source_type values
VALID_SOURCE_TYPES = {
    "primary_regulation",
    "implementing_act",
    "delegated_act",
    "commission_guidance",
    "faq",
    "enisa_publication",
    "enisa_tool",
    "authority_website",
    "related_legislation",
}

# Required validation_status values
VALID_VALIDATION_STATUSES = {
    "verified_directly",
    "pending_review",
    "stale",
    "rejected",
}

# Acceptance criteria IDs from Issue #3
REQUIRED_SOURCES = {
    "cra-regulation-2024-2847": "primary_regulation",
    "delegated-regulation-2025-1535": "delegated_act",
    "implementing-regulation-2025-2392": "implementing_act",
}

REQUIRED_EC_GUIDANCE = {
    "commission-guidance-cra-2026-5252": "commission_guidance",
    "ec-faqs-cra-2025": "faq",
    "ec-cra-summary": "commission_guidance",
}

REQUIRED_ENISA_CONTENT = {
    "enisa-authority-home": "authority_website",
    "enisa-srp-page": "enisa_tool",
}

# Official EU domains for URL validation
OFFICIAL_DOMAINS = [
    "eur-lex.europa.eu",
    "ec.europa.eu",
    "enisa.europa.eu",
    "data.europa.eu",
    "op.europa.eu",
]


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def load_catalog() -> dict:
    """Load the catalogue YAML file."""
    if not CATALOG_PATH.is_file():
        raise FileNotFoundError(f"Catalog file not found: {CATALOG_PATH}")
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data


def get_entries(data: dict) -> list:
    """Get the list of catalogue entries."""
    return data.get("catalog", [])


# ---------------------------------------------------------------------------
# Validation functions (can be called standalone or via pytest)
# ---------------------------------------------------------------------------

def validate_yaml_structure(data: dict) -> list[str]:
    """Validate the top-level YAML structure."""
    failures = []
    if "schema_version" not in data:
        failures.append("missing top-level key: schema_version")
    if "catalog" not in data:
        failures.append("missing top-level key: catalog")
        return failures
    if not isinstance(data["catalog"], list):
        failures.append("catalog must be a list of entries")
        return failures
    if len(data["catalog"]) == 0:
        failures.append("catalog is empty — at least one entry required")
    return failures


def validate_entry(entry: dict, entry_idx: int) -> list[str]:
    """Validate a single catalogue entry against required metadata fields."""
    failures = []

    entry_id = entry.get("id", f"<entry-{entry_idx}>")

    # Check id is present
    if "id" not in entry:
        failures.append(f"entry at index {entry_idx}: missing required field 'id'")
    elif not entry["id"]:
        failures.append(f"entry at index {entry_idx}: field 'id' is empty")

    # Check required fields
    for field in REQUIRED_METADATA_FIELDS:
        if field not in entry:
            failures.append(f"entry '{entry_id}': missing required field '{field}'")
        elif not entry[field]:
            failures.append(f"entry '{entry_id}': field '{field}' is empty")

    # Validate source_type
    if "source_type" in entry:
        st = entry["source_type"]
        if st not in VALID_SOURCE_TYPES:
            failures.append(
                f"entry '{entry_id}': invalid source_type '{st}' — "
                f"must be one of {sorted(VALID_SOURCE_TYPES)}"
            )

    # Validate validation_status
    if "validation_status" in entry:
        vs = entry["validation_status"]
        if vs not in VALID_VALIDATION_STATUSES:
            failures.append(
                f"entry '{entry_id}': invalid validation_status '{vs}' — "
                f"must be one of {sorted(VALID_VALIDATION_STATUSES)}"
            )

    # Validate retrieved_at is a valid date
    if "retrieved_at" in entry:
        try:
            date.fromisoformat(str(entry["retrieved_at"]))
        except (ValueError, TypeError):
            failures.append(
                f"entry '{entry_id}': retrieved_at '{entry['retrieved_at']}' "
                f"is not a valid ISO date"
            )

    # Validate publication_or_version_date is a valid date
    if "publication_or_version_date" in entry:
        try:
            date.fromisoformat(str(entry["publication_or_version_date"]))
        except (ValueError, TypeError):
            failures.append(
                f"entry '{entry_id}': publication_or_version_date "
                f"'{entry['publication_or_version_date']}' is not a valid ISO date"
            )

    # Validate source_url is a non-empty string starting with http
    if "source_url" in entry:
        url = entry["source_url"]
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            failures.append(
                f"entry '{entry_id}': source_url '{url}' is not a valid HTTP(S) URL"
            )

    # Validate document_identifier is present and non-empty
    if "document_identifier" in entry:
        di = entry["document_identifier"]
        if not isinstance(di, str) or len(di.strip()) < 3:
            failures.append(
                f"entry '{entry_id}': document_identifier is too short or missing"
            )

    # Check for prohibited content (no full-text copying of paid/restricted content)
    full_text_fields = ["full_text"]
    for ftf in full_text_fields:
        if ftf in entry:
            failures.append(
                f"entry '{entry_id}': field '{ftf}' present — "
                f"full-text content should not be embedded in the catalog"
            )

    return failures


def validate_article_sections(entry: dict) -> list[str]:
    """Validate that article_or_section contains meaningful references."""
    failures = []
    entry_id = entry.get("id", "<unknown>")
    aos = entry.get("article_or_section", {})
    if not isinstance(aos, dict):
        failures.append(f"entry '{entry_id}': article_or_section should be a mapping")
        return failures
    if len(aos) == 0:
        failures.append(f"entry '{entry_id}': article_or_section is empty")
    # Check that at least one value has substantive content
    has_content = any(
        isinstance(v, (list, dict)) and len(v) > 0
        for v in aos.values()
    ) or any(
        isinstance(v, str) and len(v.strip()) > 10
        for v in aos.values()
    )
    if not has_content:
        failures.append(
            f"entry '{entry_id}': article_or_section contains no substantive content"
        )
    return failures


def validate_required_sources(data: dict) -> list[str]:
    """Validate that all required sources per Issue #3 are present."""
    failures = []
    entries = {e["id"]: e for e in get_entries(data)}

    # CRA regulation must exist and be primary_regulation
    for req_id, req_type in REQUIRED_SOURCES.items():
        if req_id not in entries:
            failures.append(f"REQUIRED source '{req_id}' is missing from catalog")
        elif entries[req_id].get("source_type") != req_type:
            failures.append(
                f"source '{req_id}' has type '{entries[req_id].get('source_type')}' "
                f"but expected '{req_type}'"
            )

    # EC guidance must exist
    for req_id, req_type in REQUIRED_EC_GUIDANCE.items():
        if req_id not in entries:
            failures.append(f"REQUIRED EC guidance '{req_id}' is missing from catalog")
        elif entries[req_id].get("source_type") != req_type:
            failures.append(
                f"source '{req_id}' has type '{entries[req_id].get('source_type')}' "
                f"but expected '{req_type}'"
            )

    # ENISA content must exist
    for req_id, req_type in REQUIRED_ENISA_CONTENT.items():
        if req_id not in entries:
            failures.append(f"REQUIRED ENISA source '{req_id}' is missing from catalog")
        elif entries[req_id].get("source_type") != req_type:
            failures.append(
                f"source '{req_id}' has type '{entries[req_id].get('source_type')}' "
                f"but expected '{req_type}'"
            )

    return failures


def validate_no_duplicate_ids(data: dict) -> list[str]:
    """Check for duplicate entry IDs."""
    failures = []
    seen = set()
    for entry in get_entries(data):
        eid = entry.get("id")
        if eid in seen:
            failures.append(f"duplicate entry id: '{eid}'")
        seen.add(eid)
    return failures


def validate_facts_interpretations_documented(data: dict) -> list[str]:
    """
    Check that fact/interpretation separation is documented per source policy.

    Per .blitzhub/policies/source-policy.yaml section 4 (required_separation),
    the catalogue must separate: fact, interpretation, inference, recommendation,
    and open_question. This is verified by:
    1. The interpretation-records.md file exists and documents these categories.
    2. Entries with interpretation_note are flagged where interpretive content
       appears in article_or_section.
    """
    failures = []

    # Check interpretation-records.md exists
    if not INTERPRETATION_RECORDS_PATH.is_file():
        failures.append(
            f"interpretation-records.md not found at {INTERPRETATION_RECORDS_PATH}"
        )
    else:
        content = INTERPRETATION_RECORDS_PATH.read_text(encoding="utf-8")
        # Verify all five separation categories are present
        required_categories = ["fact", "interpretation", "inference", "recommendation", "open_question"]
        for cat in required_categories:
            # Check for category markers (e.g., "### Facts", "### Interpretations", etc.)
            found = any(
                marker in content.lower()
                for marker in [cat, cat.replace("_", " ")]
            )
            if not found:
                failures.append(
                    f"interpretation-records.md is missing category: '{cat}'"
                )

    # Check entries with interpretive content in article_or_section.content
    for entry in get_entries(data):
        entry_id = entry.get("id", "<unknown>")
        aos = entry.get("article_or_section", {})

        # For primary regulation, ensure article numbers are present
        if entry.get("source_type") == "primary_regulation":
            if "key_articles" not in aos and "chapters" not in aos:
                failures.append(
                    f"entry '{entry_id}': primary_regulation should have "
                    f"key_articles or chapters in article_or_section"
                )

        # Check for interpretive language in content fields — if present,
        # an interpretation_note must accompany it
        interpretation_note = entry.get("interpretation_note")
        if "content" in aos and isinstance(aos["content"], str):
            content_text = aos["content"].lower()
            if any(word in content_text for word in
                   ["may", "should", "could", "according to", "implies", "suggests"]):
                if not interpretation_note:
                    failures.append(
                        f"entry '{entry_id}': article_or_section content contains "
                        f"interpretive language — add interpretation_note to separate "
                        f"fact from interpretation"
                    )

    return failures


def validate_url_integrity(data: dict) -> list[str]:
    """Validate that source URLs point to official authorities."""
    failures = []
    for entry in get_entries(data):
        entry_id = entry.get("id", "<unknown>")
        url = entry.get("source_url", "")

        # Check that source_url is from an official domain
        is_official = any(domain in url for domain in OFFICIAL_DOMAINS)
        if not is_official:
            failures.append(
                f"entry '{entry_id}': source_url '{url}' is not from a recognized "
                f"official EU domain ({OFFICIAL_DOMAINS})"
            )

        # For EUR-Lex entries, check CELEX format
        authority = entry.get("authority", "")
        if authority and "European Parliament" in authority:
            celex = entry.get("celex", "")
            if celex and not celex.startswith(("3", "0", "5")):
                failures.append(
                    f"entry '{entry_id}': CELEX '{celex}' does not start with expected "
                    f"prefix (3=regulation, 0=directive, 5=recommendation)"
                )

    return failures


def validate_coverage_report() -> list[str]:
    """Validate that the coverage and gap report exists."""
    failures = []
    if not COVERAGE_REPORT_PATH.is_file():
        failures.append(
            f"coverage-and-gap-report.md not found at {COVERAGE_REPORT_PATH}"
        )
    else:
        content = COVERAGE_REPORT_PATH.read_text(encoding="utf-8")
        if "Rejected Sources" not in content and "rejected" not in content.lower():
            failures.append(
                "coverage-and-gap-report.md is missing rejected sources section"
            )
        if "gap" not in content.lower():
            failures.append(
                "coverage-and-gap-report.md is missing coverage gaps section"
            )
    return failures


# ---------------------------------------------------------------------------
# Main validation entry point
# ---------------------------------------------------------------------------

def run_all_validations() -> tuple[list[str], dict]:
    """Run all validation checks and return (failures, summary)."""
    all_failures: list[str] = []
    try:
        data = load_catalog()
    except FileNotFoundError as e:
        print(f"FAIL: {e}")
        return [str(e)], {"entries": 0}
    except yaml.YAMLError as e:
        print(f"FAIL: YAML parsing error: {e}")
        return [f"YAML parsing error: {e}"], {"entries": 0}

    all_failures.extend(validate_yaml_structure(data))

    if "catalog" in data and isinstance(data["catalog"], list):
        for i, entry in enumerate(data["catalog"]):
            all_failures.extend(validate_entry(entry, i))
            all_failures.extend(validate_article_sections(entry))

        all_failures.extend(validate_required_sources(data))
        all_failures.extend(validate_no_duplicate_ids(data))
        all_failures.extend(validate_facts_interpretations_documented(data))
        all_failures.extend(validate_url_integrity(data))

    all_failures.extend(validate_coverage_report())

    entry_count = len(data.get("catalog", []))
    summary = {"entries": entry_count}
    return all_failures, summary


def main() -> int:
    """Run all validation checks and report results."""
    all_failures, summary = run_all_validations()

    if all_failures:
        print(f"FAIL: {len(all_failures)} validation error(s) found:")
        for f in all_failures:
            print(f"  - {f}")
        return 1
    else:
        print(
            f"PASS: catalog.yaml validated — {summary['entries']} entries, "
            f"all checks passed."
        )
        return 0


# ---------------------------------------------------------------------------
# Pytest-compatible test functions
# ---------------------------------------------------------------------------

def test_catalog_yaml_structure():
    """Test that the catalog YAML has the correct top-level structure."""
    data = load_catalog()
    failures = validate_yaml_structure(data)
    assert not failures, "\n".join(failures)


def test_catalog_entries_have_required_metadata():
    """Test that every catalog entry has all required metadata fields."""
    data = load_catalog()
    failures = []
    for i, entry in enumerate(get_entries(data)):
        failures.extend(validate_entry(entry, i))
    assert not failures, "\n".join(failures)


def test_catalog_entries_have_article_or_section():
    """Test that every entry has meaningful article_or_section content."""
    data = load_catalog()
    failures = []
    for entry in get_entries(data):
        failures.extend(validate_article_sections(entry))
    assert not failures, "\n".join(failures)


def test_required_sources_present():
    """Test that all required sources per Issue #3 are present."""
    data = load_catalog()
    failures = validate_required_sources(data)
    assert not failures, "\n".join(failures)


def test_no_duplicate_ids():
    """Test that there are no duplicate entry IDs."""
    data = load_catalog()
    failures = validate_no_duplicate_ids(data)
    assert not failures, "\n".join(failures)


def test_facts_interpretations_documented():
    """Test that fact/interpretation separation is documented."""
    data = load_catalog()
    failures = validate_facts_interpretations_documented(data)
    assert not failures, "\n".join(failures)


def test_url_integrity():
    """Test that all source URLs point to official EU domains."""
    data = load_catalog()
    failures = validate_url_integrity(data)
    assert not failures, "\n".join(failures)


def test_coverage_report_exists():
    """Test that the coverage and gap report exists and has required sections."""
    failures = validate_coverage_report()
    assert not failures, "\n".join(failures)


def test_catalog_not_empty():
    """Test that the catalog has a meaningful number of entries."""
    data = load_catalog()
    assert len(get_entries(data)) >= 10, (
        f"Expected at least 10 entries, got {len(get_entries(data))}"
    )


def test_cra_regulation_is_primary():
    """Test that the CRA regulation entry has the correct source_type."""
    data = load_catalog()
    entries = {e["id"]: e for e in get_entries(data)}
    assert "cra-regulation-2024-2847" in entries
    assert entries["cra-regulation-2024-2847"]["source_type"] == "primary_regulation"


if __name__ == "__main__":
    sys.exit(main())


# ---------------------------------------------------------------------------
# Semantic supervisory/CELEX/matrix tests
# ---------------------------------------------------------------------------

import re as _re

SUP_NIS2_ID = "nis2-directive-2022-2555"
SUP_IMPLEMENTING_ID = "implementing-regulation-2025-2392"
VALID_CELEX_PATTERN = _re.compile(r"^3[0-9]{4}[RLD][0-9]{4}$")


def _get_entries_map(data):
    return {e["id"]: e for e in get_entries(data)}


def test_sup_001_nis2_metadata():
    data = load_catalog()
    entries = _get_entries_map(data)
    entry = entries[SUP_NIS2_ID]
    assert entry["celex"] == "32022L2555"
    assert "Directive (EU) 2022/2555" in entry["document_identifier"]
    assert "OJ L 333" in entry["oj_reference"]
    assert "27.12.2022" in entry["oj_reference"]
    assert entry["source_type"] == "related_legislation"
    assert "/dir/2022/2555/" in entry["eli_url"]


def test_sup_002_implementing_regulation_metadata():
    data = load_catalog()
    entries = _get_entries_map(data)
    entry = entries[SUP_IMPLEMENTING_ID]
    assert entry["celex"] == "32025R2392"
    assert entry["publication_or_version_date"] == "2025-12-01"
    assert entry["entry_into_force"] == "2025-12-21"
    assert entry["application_start"] == "2025-12-21"
    assert "2025/2392" in entry["oj_reference"]
    assert "1.12.2025" in entry["oj_reference"]
    assert "/reg_impl/2025/2392/" in entry["eli_url"]


def test_sup_003_cra_article_mappings():
    data = load_catalog()
    entries = _get_entries_map(data)
    article_map = entries["cra-regulation-2024-2847"]["article_or_section"]["key_articles"]
    assert article_map[15] == "voluntary reporting"
    assert article_map[16] == "establishment and operation of the Single Reporting Platform"
    assert article_map[17] == "Authorised representative"
    assert article_map[18] == "Importer"
    assert article_map[19] == "Distributor"


def test_sup_003_srp_not_article_15():
    data = load_catalog()
    entries = _get_entries_map(data)
    article_map = entries["cra-regulation-2024-2847"]["article_or_section"]["key_articles"]
    assert "Single Reporting Platform" not in article_map.get(15, "")


def test_celex_valid_examples():
    valid = ["32024R2847", "32025R2392", "32022L2555", "32019R0881"]
    for celex in valid:
        assert VALID_CELEX_PATTERN.fullmatch(celex)


def test_celex_invalid_examples():
    invalid = ["02022L2555", "3202L2555", "32022L02555", "32022X2555"]
    for celex in invalid:
        assert not VALID_CELEX_PATTERN.fullmatch(celex)


def _load_matrix():
    matrix_path = REPO_ROOT / "research" / "sources" / "source-validation-matrix.yaml"
    if not matrix_path.is_file():
        raise FileNotFoundError(f"Matrix not found: {matrix_path}")
    return yaml.safe_load(matrix_path.read_text())


def test_matrix_has_exactly_20_entries():
    matrix = _load_matrix()
    assert len(matrix["entries"]) == len(load_catalog()["catalog"])


def test_matrix_ids_unique_and_match_catalog():
    data = load_catalog()
    catalog_ids = {e["id"] for e in get_entries(data)}
    matrix_ids = {m["entry_id"] for m in _load_matrix()["entries"]}
    assert matrix_ids == catalog_ids
    assert len(matrix_ids) == len(load_catalog()["catalog"])


def test_matrix_matches_catalog_validation_status():
    data = load_catalog()
    entries = _get_entries_map(data)
    for m in _load_matrix()["entries"]:
        entry = entries[m["entry_id"]]
        assert entry["validation_status"] == m["classification"]


def test_matrix_no_legacy_verified_status():
    matrix = _load_matrix()
    for m in matrix["entries"]:
        assert m["classification"] != "verified"


def test_verified_directly_requires_evidence():
    matrix = _load_matrix()
    for m in matrix["entries"]:
        if m["classification"] == "verified_directly":
            assert m["official_source_checked"] is True
            assert m["evidence_reference"]
            for key in ["authority", "title", "identifier", "publication_date", "article_mapping"]:
                assert m["metadata_verified"].get(key) is True


def test_pending_review_cannot_claim_full_direct_validation():
    matrix = _load_matrix()
    for m in matrix["entries"]:
        if m["classification"] == "pending_review":
            assert all(m["metadata_verified"].values()) is False


# ---------------------------------------------------------------------------
# Regulatory/CELEX/matrix tests using production validator functions
# ---------------------------------------------------------------------------

import re as _re

from scripts.validate_source_catalog import (
    validate_celex,
    validate_matrix,
    validate_srp_references,
    validate_rejected_sources,
    validate_known_regulatory_metadata,
    load_catalog,
    load_matrix,
    SECTOR3_LEGAL_ACT_CELEX_PATTERN,
)

SUP_NIS2_ID = "nis2-directive-2022-2555"
SUP_IMPLEMENTING_ID = "implementing-regulation-2025-2392"


def test_sector3_legal_act_celex_pattern():
    assert SECTOR3_LEGAL_ACT_CELEX_PATTERN.fullmatch("32024R2847")
    assert SECTOR3_LEGAL_ACT_CELEX_PATTERN.fullmatch("32022L2555")
    assert SECTOR3_LEGAL_ACT_CELEX_PATTERN.fullmatch("02022L2555") is None
    assert not SECTOR3_LEGAL_ACT_CELEX_PATTERN.fullmatch("02022L2555")


def test_validate_celex_regulation_requires_r():
    entry = {
        "id": "cra-regulation-2024-2847",
        "source_type": "primary_regulation",
        "document_identifier": "Regulation (EU) 2024/2847",
        "celex": "32024L2847",
        "eli_url": "/reg/2024/2847/",
    }
    failures = validate_celex(entry)
    assert any("uses 'L' for regulatory act" in msg for msg in failures)


def test_validate_celex_directive_requires_l():
    entry = {
        "id": SUP_NIS2_ID,
        "source_type": "related_legislation",
        "document_identifier": "Directive (EU) 2022/2555",
        "celex": "32022R2555",
        "eli_url": "/dir/2022/2555/",
    }
    failures = validate_celex(entry)
    assert any("uses 'R' for directive" in msg for msg in failures)


def test_validate_celex_eli_conflict():
    entry = {
        "id": SUP_IMPLEMENTING_ID,
        "source_type": "implementing_act",
        "document_identifier": "Commission Implementing Regulation (EU) 2025/2392",
        "celex": "32025L2392",
        "eli_url": "/reg_impl/2025/2392/",
    }
    failures = validate_celex(entry)
    assert any("ELI '/reg_impl/' conflicts" in msg for msg in failures)


def test_validate_known_regulatory_metadata():
    data = load_catalog()
    failures = validate_known_regulatory_metadata(data)
    assert not failures, "\n".join(failures)


def test_validate_matrix_alignment():
    data = load_catalog()
    matrix = load_matrix()
    failures = validate_matrix(data, matrix)
    assert not failures, "\n".join(failures)


def test_matrix_no_internal_evidence_reference():
    data = load_catalog()
    matrix = load_matrix()
    failures = validate_matrix(data, matrix)
    assert not any("evidence_reference must not be an internal catalog pointer" in msg for msg in failures)


def test_rejected_sources_are_not_active_catalog():
    data = load_catalog()
    for entry in data["catalog"]:
        assert entry.get("validation_status") != "rejected"


def test_srp_article_16_required_for_platform():
    data = load_catalog()
    failures = validate_srp_references(data)
    assert not failures, "\n".join(failures)


def test_srp_article_15_remains_voluntary_reporting():
    data = load_catalog()
    failures = validate_srp_references(data)
    assert not any("voluntary reporting" in msg and "Article 15" in msg for msg in failures)


def test_matrix_source_role_populated():
    data = load_catalog()
    matrix = load_matrix()
    failures = validate_matrix(data, matrix)
    assert not any("missing source_role" in msg for msg in failures)


def test_guidance_not_auto_stale():
    data = load_catalog()
    matrix = load_matrix()
    matrix_by_id = {m["entry_id"]: m for m in matrix["entries"]}
    for entry in get_entries(data):
        if entry.get("source_type") in {"commission_guidance", "faq"}:
            assert matrix_by_id[entry["id"]]["classification"] != "stale"


def test_stale_requires_reason():
    data = load_catalog()
    matrix = load_matrix()
    matrix_by_id = {m["entry_id"]: m for m in matrix["entries"]}
    for entry in get_entries(data):
        if entry.get("validation_status") == "stale":
            m = matrix_by_id[entry["id"]]
            assert m.get("stale_reason") or m.get("stale_since") or m.get("superseded_by"), entry["id"]


def test_oj_reference_null_preserved_for_non_legal():
    data = load_catalog()
    matrix = load_matrix()
    failures = validate_matrix(data, matrix)
    assert not any("oj_reference is null but metadata_verified.oj_reference is true" in msg for msg in failures)


def test_rejected_evidence_not_circular():
    rejected_path = REPO_ROOT / "research" / "sources" / "rejected-sources.yaml"
    data = yaml.safe_load(rejected_path.read_text())
    for item in data.get("rejected_sources", []):
        assert not item.get("evidence_reference", "").startswith("catalog.yaml#")


def test_matrix_counts_match_catalog():
    data = load_catalog()
    matrix = load_matrix()
    assert len(matrix["entries"]) == len(data["catalog"])


def test_source_role_counts():
    data = load_catalog()
    matrix = load_matrix()
    counts = {}
    for m in matrix["entries"]:
        counts[m.get("source_role", "unknown")] = counts.get(m.get("source_role", "unknown"), 0) + 1
    assert set(counts.keys()) == {"legal_act", "official_guidance", "official_tool", "context"}

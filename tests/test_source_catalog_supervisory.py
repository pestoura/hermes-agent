#!/usr/bin/env python3
"""
Adversarial / mutation tests for the supervisory decisions applied to the
CRA source catalogue.

These are intentionally separate from tests/test_source_catalog.py to avoid
duplicate pytest names and to keep the supervisory extension isolated.
"""

from __future__ import annotations

import yaml
from pathlib import Path

from scripts.validate_source_catalog import (
    load_catalog,
    load_matrix,
    validate_matrix,
    validate_srp_references,
    validate_rejected_sources,
    validate_stale_semantics,
    validate_metadata_applicability,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_matrix_source_role_populated():
    data = load_catalog()
    matrix = load_matrix()
    failures = validate_matrix(data, matrix)
    assert not any("missing source_role" in msg for msg in failures)
    assert not any("source_role" in msg for msg in failures), "\n".join(failures)


def test_guidance_not_auto_stale():
    data = load_catalog()
    matrix = load_matrix()
    matrix_by_id = {m["entry_id"]: m for m in matrix["entries"]}
    for entry in data["catalog"]:
        if entry.get("source_type") in {"commission_guidance", "faq"}:
            assert matrix_by_id[entry["id"]]["classification"] != "stale"


def test_stale_requires_reason():
    data = load_catalog()
    matrix = load_matrix()
    matrix_by_id = {m["entry_id"]: m for m in matrix["entries"]}
    for entry in data["catalog"]:
        if entry.get("validation_status") == "stale":
            m = matrix_by_id[entry["id"]]
            assert m.get("stale_reason") or m.get("stale_since") or m.get("superseded_by"), entry["id"]


def test_stale_mutation_rejected_without_reason():
    data = load_catalog()
    matrix = load_matrix()
    pending = next(m for m in matrix["entries"] if m["classification"] == "pending_review")
    pending["classification"] = "stale"
    failures = validate_matrix(data, matrix)
    assert any("stale classification requires" in msg for msg in failures)


def test_stale_mutation_accepted_with_reason():
    data = load_catalog()
    matrix = load_matrix()
    pending = next(m for m in matrix["entries"] if m["classification"] == "pending_review")
    pending["classification"] = "stale"
    pending["stale_reason"] = "superseded by later update"
    for entry in data["catalog"]:
        if entry["id"] == pending["entry_id"]:
            entry["validation_status"] = "stale"
    failures = validate_matrix(data, matrix)
    assert not failures, "\n".join(failures)


def test_matrix_classification_counts():
    data = load_catalog()
    matrix = load_matrix()
    assert sum(1 for m in matrix["entries"] if m["classification"] == "verified_directly") == 6
    assert sum(1 for m in matrix["entries"] if m["classification"] == "pending_review") == 14
    assert sum(1 for m in matrix["entries"] if m["classification"] == "stale") == 0


def test_rejected_entry_is_not_active():
    data = load_catalog()
    assert not any(entry.get("validation_status") == "rejected" for entry in data["catalog"])


def test_rejected_sources_validated():
    data = load_catalog()
    matrix = load_matrix()
    failures = validate_rejected_sources(data, matrix)
    assert not failures, "\n".join(failures)


def test_rejected_evidence_not_circular():
    rejected_path = REPO_ROOT / "research" / "sources" / "rejected-sources.yaml"
    data = yaml.safe_load(rejected_path.read_text())
    for item in data.get("rejected_sources", []):
        assert not item.get("evidence_reference", "").startswith("catalog.yaml#")


def test_srp_article_16_required_for_platform():
    data = load_catalog()
    failures = validate_srp_references(data)
    assert not failures, "\n".join(failures)


def test_srp_article_15_remains_voluntary_reporting():
    data = load_catalog()
    failures = validate_srp_references(data)
    assert not any("voluntary reporting" in msg and "Article 15" in msg for msg in failures)


def test_srp_authority_home_article_15_mutation_fails():
    data = load_catalog()
    entry = next(e for e in data["catalog"] if e["id"] == "enisa-authority-home")
    entry["article_or_section"]["content"] = "ENISA operates the CRA Single Reporting Platform per Article 15"
    failures = validate_srp_references(data)
    assert any("ENISA operates the platform per Article 15" in msg for msg in failures)


def test_srp_srp_page_article_15_mapping_fails():
    data = load_catalog()
    entry = next(e for e in data["catalog"] if e["id"] == "enisa-srp-page")
    entry["article_or_section"] = {
        "content": "ENISA maintains the Single Reporting Platform reference page.",
        "references": {"article_15": "Single Reporting Platform"},
    }
    failures = validate_srp_references(data)
    assert any("Single Reporting Platform is referenced without Article 16" in msg for msg in failures)


def test_srp_notification_established_under_article_15_fails():
    data = load_catalog()
    entry = next(e for e in data["catalog"] if e["id"] == "enisa-srp-notification")
    entry["article_or_section"]["content"] = "The Single Reporting Platform is established under Article 15."
    failures = validate_srp_references(data)
    assert any("platform establishment/operation must not be assigned to Article 15" in msg for msg in failures)


def test_srp_user_registration_operation_under_article_15_fails():
    data = load_catalog()
    entry = next(e for e in data["catalog"] if e["id"] == "enisa-srp-user-registration")
    entry["article_or_section"]["content"] = "Operation of the Single Reporting Platform is under Article 15."
    failures = validate_srp_references(data)
    assert any("Single Reporting Platform is referenced without Article 16" in msg for msg in failures)


def test_srp_new_entry_without_article_16_fails():
    data = load_catalog()
    data["catalog"].append({
        "id": "new-srp-page",
        "article_or_section": {"content": "The Single Reporting Platform is available."},
        "source_type": "enisa_tool",
        "validation_status": "pending_review",
        "authority": "ENISA",
        "title": "new",
        "document_identifier": "new",
        "source_url": "https://enisa.europa.eu/new",
        "publication_or_version_date": "2026-01-01",
        "retrieved_at": "2026-01-01",
    })
    failures = validate_srp_references(data)
    assert any("Single Reporting Platform is referenced without Article 16" in msg for msg in failures)


def test_srp_lowercase_variation_fails():
    data = load_catalog()
    entry = next(e for e in data["catalog"] if e["id"] == "enisa-authority-home")
    entry["article_or_section"]["content"] = "Operates the single reporting platform per article 15"
    failures = validate_srp_references(data)
    assert any("per Article 15" in msg for msg in failures)


def test_srp_article_15_voluntary_with_article_16_platform_passes():
    data = load_catalog()
    entry = next(e for e in data["catalog"] if e["id"] == "enisa-srp-page")
    entry["article_or_section"]["references"] = {
        "article_15": "voluntary reporting",
        "article_16": "establishment and operation of the Single Reporting Platform",
    }
    entry["article_or_section"]["content"] = (
        "The SRP supports reporting under Articles 14 and 15. "
        "The Single Reporting Platform is established under Article 16."
    )
    failures = validate_srp_references(data)
    assert not failures, "\n".join(failures)


def test_rejected_requires_https_and_official_domain():
    data = load_catalog()
    matrix = load_matrix()
    rejected_http = {
        "entry_id": "bad-rejected-http",
        "classification": "rejected",
        "source_role": "official_tool",
        "source_url": "https://example.com/ok",
        "evidence_reference": "http://example.com/bad",
        "oj_reference": None,
        "article_mapping": None,
    }
    rejected_domain = {
        "entry_id": "bad-rejected-domain",
        "classification": "rejected",
        "source_role": "official_tool",
        "source_url": "https://example.com/ok",
        "evidence_reference": "https://example.com/bad",
        "oj_reference": None,
        "article_mapping": None,
    }
    rejected_empty = {
        "entry_id": "bad-rejected-empty",
        "classification": "rejected",
        "source_role": "official_tool",
        "source_url": "",
        "evidence_reference": "https://example.com/bad",
        "oj_reference": None,
        "article_mapping": None,
    }
    rejected_path = REPO_ROOT / "research" / "sources" / "rejected-sources.yaml"
    original = yaml.safe_load(rejected_path.read_text())
    original_rejected = list(original.get("rejected_sources", []))
    original["rejected_sources"] = [rejected_http, rejected_domain, rejected_empty]
    rejected_path.write_text(yaml.safe_dump(original, sort_keys=False, allow_unicode=True, default_flow_style=False))
    try:
        failures = validate_rejected_sources(data, matrix)
        assert any("must be an HTTPS URL" in msg for msg in failures)
        assert any("must belong to an official allowed domain" in msg for msg in failures)
        assert any("source_url must not be empty" in msg for msg in failures)
    finally:
        original["rejected_sources"] = original_rejected
        rejected_path.write_text(yaml.safe_dump(original, sort_keys=False, allow_unicode=True, default_flow_style=False))


def test_metadata_applicability_rejects_non_null_for_non_legal():
    matrix = load_matrix()
    data = load_catalog()
    entry = next(e for e in data["catalog"] if e["id"] == "ec-cra-factpage-implementation")
    m = next(m for m in matrix["entries"] if m["entry_id"] == "ec-cra-factpage-implementation")
    m["oj_reference"] = "incorrect"
    m["article_mapping"] = "incorrect"
    failures = validate_metadata_applicability(m, entry, entry["id"])
    assert any("must use null oj_reference" in msg for msg in failures)
    assert any("must use null article_mapping" in msg for msg in failures)


def test_stale_semantics_rejects_non_stale_stale_fields_without_history():
    m = {"classification": "pending_review", "stale_reason": "old"}
    failures = validate_stale_semantics(m, "dummy")
    assert any("without explicit_history" in msg for msg in failures)


def test_stale_semantics_accepts_stale_with_reason():
    m = {"classification": "stale", "stale_reason": "superseded"}
    failures = validate_stale_semantics(m, "dummy")
    assert not failures

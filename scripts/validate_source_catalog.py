#!/usr/bin/env python3
"""
Quick validation script for the CRA source catalogue.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required.")
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = REPO_ROOT / "research" / "sources" / "catalog.yaml"
MATRIX_PATH = REPO_ROOT / "research" / "sources" / "source-validation-matrix.yaml"
REJECTED_PATH = REPO_ROOT / "research" / "sources" / "rejected-sources.yaml"

REQUIRED_FIELDS = [
    "id",
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

VALID_VALIDATION_STATUSES = {
    "verified_directly",
    "pending_review",
    "stale",
    "rejected",
}

VALID_SOURCE_ROLES = {
    "legal_act",
    "official_guidance",
    "official_tool",
    "context",
}

SECTOR3_LEGAL_ACT_CELEX_PATTERN = re.compile(r"^3[0-9]{4}[RLD][0-9]{4}$")


def load_catalog() -> dict:
    if not CATALOG_PATH.is_file():
        raise FileNotFoundError(f"Catalog file not found: {CATALOG_PATH}")
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_matrix() -> dict:
    if not MATRIX_PATH.is_file():
        raise FileNotFoundError(f"Matrix file not found: {MATRIX_PATH}")
    with open(MATRIX_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def validate_celex(entry: dict) -> list[str]:
    failures = []
    eid = entry.get("id", "<unknown>")
    celex = entry.get("celex")
    if not celex:
        return failures
    if not SECTOR3_LEGAL_ACT_CELEX_PATTERN.fullmatch(celex):
        failures.append(f"entry '{eid}': invalid sector-3 legal act CELEX format '{celex}'")
        return failures

    celex_letter = celex[5]
    source_type = entry.get("source_type", "")
    document_identifier = entry.get("document_identifier", "")
    eli_url = entry.get("eli_url", "")

    if source_type in {"primary_regulation", "implementing_act", "delegated_act"} and celex_letter != "R":
        failures.append(f"entry '{eid}': CELEX '{celex}' uses '{celex_letter}' for regulatory act")

    if source_type == "related_legislation":
        if "Directive" in document_identifier and celex_letter != "L":
            failures.append(f"entry '{eid}': CELEX '{celex}' uses '{celex_letter}' for directive")
        if "Regulation" in document_identifier and celex_letter != "R":
            failures.append(f"entry '{eid}': CELEX '{celex}' uses '{celex_letter}' for related regulation")
        if "Decision" in document_identifier and celex_letter != "D":
            failures.append(f"entry '{eid}': CELEX '{celex}' uses '{celex_letter}' for decision")

    if "/reg/" in eli_url and celex_letter != "R":
        failures.append(f"entry '{eid}': ELI '/reg/' conflicts with CELEX '{celex}'")
    if "/reg_impl/" in eli_url and celex_letter != "R":
        failures.append(f"entry '{eid}': ELI '/reg_impl/' conflicts with CELEX '{celex}'")
    if "/reg_del/" in eli_url and celex_letter != "R":
        failures.append(f"entry '{eid}': ELI '/reg_del/' conflicts with CELEX '{celex}'")
    if "/dir/" in eli_url and celex_letter != "L":
        failures.append(f"entry '{eid}': ELI '/dir/' conflicts with CELEX '{celex}'")
    if "/dec/" in eli_url and celex_letter != "D":
        failures.append(f"entry '{eid}': ELI '/dec/' conflicts with CELEX '{celex}'")
    return failures


def validate_stale_semantics(matrix_entry: dict, entry_id: str) -> list[str]:
    failures = []
    classification = matrix_entry.get("classification")
    stale_reason = matrix_entry.get("stale_reason")
    stale_since = matrix_entry.get("stale_since")
    superseded_by = matrix_entry.get("superseded_by")
    explicit_history = matrix_entry.get("explicit_history") or matrix_entry.get("historical_note")

    if classification == "stale":
        if not any([stale_reason, stale_since, superseded_by]):
            failures.append(f"entry '{entry_id}': stale classification requires stale_reason, stale_since or superseded_by")
    else:
        contradictory = []
        if stale_reason and not explicit_history:
            contradictory.append("stale_reason")
        if stale_since and not explicit_history:
            contradictory.append("stale_since")
        if superseded_by and not explicit_history:
            contradictory.append("superseded_by")
        if contradictory:
            failures.append(
                f"entry '{entry_id}': classification '{classification}' uses stale-only fields without explicit_history: {', '.join(contradictory)}"
            )
    return failures


def validate_metadata_applicability(matrix_entry: dict, catalog_entry: dict, entry_id: str) -> list[str]:
    failures = []
    source_role = matrix_entry.get("source_role")
    source_type = catalog_entry.get("source_type")
    binding_legal_types = {"primary_regulation", "implementing_act", "delegated_act"}
    if source_type == "related_legislation":
        document_identifier = catalog_entry.get("document_identifier", "")
        binding_legal_types = binding_legal_types | {
            document_identifier.startswith(prefix) for prefix in ("Regulation", "Directive", "Decision", "Council")
        }
    legal_roles = source_role == "legal_act" or source_type in binding_legal_types
    oj_reference = matrix_entry.get("oj_reference")
    article_mapping = matrix_entry.get("article_mapping")
    mv = matrix_entry.get("metadata_verified", {})
    if legal_roles:
        if oj_reference is None:
            failures.append(f"entry '{entry_id}': legal act requires oj_reference")
        if article_mapping is None:
            failures.append(f"entry '{entry_id}': legal act requires article_mapping")
        if mv.get("oj_reference") is None:
            failures.append(f"entry '{entry_id}': metadata_verified.oj_reference must be true for legal acts")
        if mv.get("article_mapping") is None:
            failures.append(f"entry '{entry_id}': metadata_verified.article_mapping must be true for legal acts")
        if oj_reference is False:
            failures.append(f"entry '{entry_id}': oj_reference cannot be false for legal acts")
        if article_mapping is False:
            failures.append(f"entry '{entry_id}': article_mapping cannot be false for legal acts")
    else:
        if oj_reference not in (None, False):
            failures.append(f"entry '{entry_id}': non-legal source_role '{source_role}' must use null oj_reference")
        if article_mapping not in (None, False):
            failures.append(f"entry '{entry_id}': non-legal source_role '{source_role}' must use null article_mapping")
        if mv.get("oj_reference") not in (None, False):
            failures.append(f"entry '{entry_id}': metadata_verified.oj_reference must be null for non-legal sources")
        if mv.get("article_mapping") not in (None, False):
            failures.append(f"entry '{entry_id}': metadata_verified.article_mapping must be null for non-legal sources")
    return failures


def validate_matrix(catalog: dict, matrix: dict) -> list[str]:
    failures = []
    entries = catalog.get("catalog", [])
    catalog_map = {e["id"]: e for e in entries}
    matrix_entries = matrix.get("entries", [])

    if len(matrix_entries) != len(entries):
        failures.append(
            f"matrix entry count {len(matrix_entries)} does not match catalog entry count {len(entries)}"
        )

    matrix_ids = []
    for m in matrix_entries:
        eid = m.get("entry_id")
        matrix_ids.append(eid)
        if eid not in catalog_map:
            failures.append(f"matrix references missing catalog entry: {eid}")
            continue
        entry = catalog_map[eid]
        if entry.get("validation_status") != m.get("classification"):
            failures.append(f"entry '{eid}': matrix classification does not match catalog validation_status")
        if m.get("classification") == "verified_directly":
            if not m.get("official_source_checked"):
                failures.append(f"entry '{eid}': verified_directly requires official_source_checked=true")
            if not m.get("evidence_reference"):
                failures.append(f"entry '{eid}': verified_directly requires evidence_reference")
            critical = ["authority", "title", "identifier", "publication_date", "article_mapping"]
            if not all(m.get("metadata_verified", {}).get(k) for k in critical):
                failures.append(f"entry '{eid}': verified_directly requires critical metadata_verified=true")
        if m.get("classification") == "pending_review" and all(m.get("metadata_verified", {}).values()):
            failures.append(f"entry '{eid}': pending_review cannot claim complete direct metadata verification")
        if m.get("evidence_reference", "").startswith("catalog.yaml#"):
            failures.append(f"entry '{eid}': evidence_reference must not be an internal catalog pointer")
        if m.get("classification") == "rejected" and m.get("source_role") == "legal_act":
            failures.append(f"entry '{eid}': rejected legal acts require explicit inactive handling")

        source_role = m.get("source_role")
        if not source_role or source_role not in VALID_SOURCE_ROLES:
            failures.append(f"entry '{eid}': matrix entry source_role '{source_role}' is invalid")

        failures.extend(validate_stale_semantics(m, eid))
        failures.extend(validate_metadata_applicability(m, entry, eid))

    if len(set(matrix_ids)) != len(matrix_ids):
        failures.append("matrix contains duplicate entry_id values")

    return failures


def iter_text_values(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, nested in value.items():
            yield str(key)
            yield from iter_text_values(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from iter_text_values(nested)


def validate_srp_references(catalog: dict) -> list[str]:
    failures = []
    entries = catalog.get("catalog", [])

    def has_article_16(text: str) -> bool:
        return (
            "article 16" in text
            or "article_16" in text
            or "16:" in text
            or " article 16 " in text
        )

    def article_15_maps_srp(text: str) -> bool:
        return "article_15" in text or "article 15" in text or "15:" in text

    srp_platform = "single reporting platform"
    voluntary_reporting = "voluntary reporting"

    for entry in entries:
        eid = entry.get("id", "<unknown>")
        if eid == "cra-regulation-2024-2847":
            continue
        text = " ".join(iter_text_values(entry)).casefold()
        if srp_platform not in text:
            continue
        if not has_article_16(text):
            failures.append(f"entry '{eid}': Single Reporting Platform is referenced without Article 16")
        if "per article 15" in text or "platform operated per article 15" in text:
            failures.append(f"entry '{eid}': ENISA operates the platform per Article 15 — must be Article 16")
        if "established under article 15" in text or "operation under article 15" in text:
            failures.append(f"entry '{eid}': platform establishment/operation must not be assigned to Article 15")
        if article_15_maps_srp(text) and voluntary_reporting not in text:
            failures.append(f"entry '{eid}': Article 15 must not be mapped to the Single Reporting Platform")
    return failures


def load_rejected() -> dict:
    if not REJECTED_PATH.is_file():
        return {"rejected_sources": []}
    with open(REJECTED_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {"rejected_sources": []}


def validate_rejected_sources(catalog: dict, matrix: dict) -> list[str]:
    failures = []
    active_ids = {e["id"] for e in catalog.get("catalog", [])}
    rejected = load_rejected().get("rejected_sources", [])
    matrix_ids = {m["entry_id"] for m in matrix.get("entries", [])}
    allowed_domains = ["eur-lex.europa.eu", "ec.europa.eu", "enisa.europa.eu", "data.europa.eu", "op.europa.eu"]

    for item in rejected:
        eid = item.get("entry_id")
        if eid in active_ids:
            failures.append(f"rejected entry '{eid}' still exists in active catalog")
        evidence = item.get("evidence_reference", "")
        if not evidence.startswith("https://"):
            failures.append(f"rejected entry '{eid}': evidence_reference must be an HTTPS URL")
        if not any(domain in evidence for domain in allowed_domains):
            failures.append(f"rejected entry '{eid}': evidence_reference must belong to an official allowed domain")
        if not item.get("source_url"):
            failures.append(f"rejected entry '{eid}': source_url must not be empty")
        if item.get("classification") != "rejected":
            failures.append(f"rejected entry '{eid}': classification must be rejected")
        if item.get("source_role") not in VALID_SOURCE_ROLES:
            failures.append(f"rejected entry '{eid}': source_role must be one of {sorted(VALID_SOURCE_ROLES)}")
        if item.get("oj_reference") not in (None, False):
            failures.append(f"rejected entry '{eid}': metadata applicability must use null oj_reference")
        if item.get("article_mapping") not in (None, False):
            failures.append(f"rejected entry '{eid}': metadata applicability must use null article_mapping")
        if eid in matrix_ids:
            failures.append(f"rejected entry '{eid}': must not remain in active source-validation-matrix.yaml")

    return failures


def validate_known_regulatory_metadata(catalog: dict) -> list[str]:
    failures = []
    entries = {e["id"]: e for e in catalog.get("catalog", [])}

    cra = entries.get("cra-regulation-2024-2847")
    if cra:
        if cra.get("publication_or_version_date") != "2024-11-20":
            failures.append("CRA 2024/2847 publication_or_version_date must be 2024-11-20")
        if cra.get("entry_into_force") != "2024-12-10":
            failures.append("CRA 2024/2847 entry_into_force must be 2024-12-10")
        if cra.get("application_start") != "2027-12-11":
            failures.append("CRA 2024/2847 application_start must be 2027-12-11")
        key = cra.get("article_or_section", {}).get("key_articles", {})
        if key.get(15) != "voluntary reporting":
            failures.append("CRA article 15 must remain 'voluntary reporting'")
        if key.get(16) != "establishment and operation of the Single Reporting Platform":
            failures.append("CRA article 16 must remain Single Reporting Platform")

    delegated = entries.get("delegated-regulation-2025-1535")
    if delegated:
        if delegated.get("oj_reference") != "OJ L, 2025/1535, 29.10.2025":
            failures.append("Delegated Regulation 2025/1535 OJ reference must be 'OJ L, 2025/1535, 29.10.2025'")
        if delegated.get("publication_or_version_date") != "2025-10-29":
            failures.append("Delegated Regulation 2025/1535 publication date must be 2025-10-29")
        if delegated.get("entry_into_force") != "2025-11-18":
            failures.append("Delegated Regulation 2025/1535 entry_into_force must be 2025-11-18")
        articles = delegated.get("article_or_section", {}).get("key_articles", {})
        if articles.keys() != {1, 2}:
            failures.append("Delegated Regulation 2025/1535 must expose only articles 1 and 2")

    cyb = entries.get("cybersecurity-act-2019-881")
    if cyb:
        if "17 April 2019" not in cyb.get("title", ""):
            failures.append("Cybersecurity Act title must contain '17 April 2019'")
        if cyb.get("publication_or_version_date") != "2019-06-07":
            failures.append("Cybersecurity Act publication date must be 2019-06-07")
        if cyb.get("entry_into_force") != "2019-06-27":
            failures.append("Cybersecurity Act entry_into_force must be 2019-06-27")
        if 49 in cyb.get("article_or_section", {}).get("key_articles", {}):
            failures.append("Cybersecurity Act must not include article 49 SRP mapping")

    market = entries.get("market-surveillance-reg-2019-1020")
    if market:
        if market.get("publication_or_version_date") != "2019-06-25":
            failures.append("Market Surveillance Regulation publication date must be 2019-06-25")
        if market.get("entry_into_force") != "2019-07-15":
            failures.append("Market Surveillance Regulation entry_into_force must be 2019-07-15")

    implementing = entries.get("implementing-regulation-2025-2392")
    if implementing:
        annexes = implementing.get("article_or_section", {}).get("annexes", {})
        if annexes.get("Annex I") != "technical descriptions corresponding to CRA Annex III":
            failures.append("Implementing Regulation Annex I description incorrect")
        if annexes.get("Annex II") != "technical descriptions corresponding to CRA Annex IV":
            failures.append("Implementing Regulation Annex II description incorrect")
        if "key_articles" in implementing.get("article_or_section", {}):
            failures.append("Implementing Regulation must not use key_articles")

    return failures


def validate_yaml_structure(data: dict) -> list[str]:
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
    failures = []
    entry_id = entry.get("id", f"<entry-{entry_idx}>")
    if "id" not in entry or not entry["id"]:
        failures.append(f"entry at index {entry_idx}: missing required field 'id'")
    for field in REQUIRED_FIELDS:
        if field not in entry or not entry[field]:
            failures.append(f"entry '{entry_id}': missing or empty field '{field}'")
    if entry.get("source_type") not in VALID_SOURCE_TYPES:
        failures.append(f"entry '{entry_id}': invalid source_type '{entry.get('source_type')}'")
    if entry.get("validation_status") not in VALID_VALIDATION_STATUSES:
        failures.append(f"entry '{entry_id}': invalid validation_status '{entry.get('validation_status')}'")
    if "retrieved_at" in entry:
        try:
            date.fromisoformat(str(entry["retrieved_at"]))
        except (ValueError, TypeError):
            failures.append(f"entry '{entry_id}': retrieved_at '{entry['retrieved_at']}' is not a valid ISO date")
    if "publication_or_version_date" in entry:
        try:
            date.fromisoformat(str(entry["publication_or_version_date"]))
        except (ValueError, TypeError):
            failures.append(
                f"entry '{entry_id}': publication_or_version_date '{entry['publication_or_version_date']}' is not a valid ISO date"
            )
    url = entry.get("source_url", "")
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        failures.append(f"entry '{entry_id}': source_url '{url}' is not a valid HTTP(S) URL")
    di = entry.get("document_identifier", "")
    if not isinstance(di, str) or len(di.strip()) < 3:
        failures.append(f"entry '{entry_id}': document_identifier is too short or missing")
    if "full_text" in entry:
        failures.append(f"entry '{entry_id}': full_text content should not be embedded in the catalog")
    return failures


def validate_required_sources(data: dict) -> list[str]:
    failures = []
    entries = {e["id"]: e for e in data.get("catalog", [])}
    required = {
        "cra-regulation-2024-2847": "primary_regulation",
        "delegated-regulation-2025-1535": "delegated_act",
        "implementing-regulation-2025-2392": "implementing_act",
        "commission-guidance-cra-2026-5252": "commission_guidance",
        "ec-faqs-cra-2025": "faq",
        "enisa-srp-page": "enisa_tool",
        "enisa-authority-home": "authority_website",
    }
    for req_id, req_type in required.items():
        if req_id not in entries:
            failures.append(f"REQUIRED source '{req_id}' is missing from catalog")
        elif entries[req_id].get("source_type") != req_type:
            failures.append(
                f"source '{req_id}' has type '{entries[req_id].get('source_type')}' but expected '{req_type}'"
            )
    return failures


def validate_no_duplicate_ids(data: dict) -> list[str]:
    failures = []
    seen = set()
    for entry in data.get("catalog", []):
        eid = entry.get("id")
        if eid in seen:
            failures.append(f"duplicate entry id: '{eid}'")
        seen.add(eid)
    return failures


def validate_facts_interpretations_documented(data: dict) -> list[str]:
    failures = []
    interpretation_path = REPO_ROOT / "research" / "sources" / "interpretation-records.md"
    if not interpretation_path.is_file():
        failures.append("interpretation-records.md not found")
    else:
        content = interpretation_path.read_text(encoding="utf-8").lower()
        category_markers = ["fact", "interpretation", "inference", "recommendation"]
        for category in category_markers:
            if category not in content:
                failures.append(f"interpretation-records.md is missing category: '{category}'")
        if "open_question" not in content and "open questions" not in content:
            failures.append("interpretation-records.md is missing category: 'open_question'")
    for entry in data.get("catalog", []):
        aos = entry.get("article_or_section", {})
        if entry.get("source_type") == "primary_regulation" and "key_articles" not in aos and "chapters" not in aos:
            failures.append(f"entry '{entry.get('id')}': primary_regulation should have key_articles or chapters")
    return failures


def validate_url_integrity(data: dict) -> list[str]:
    failures = []
    official_domains = ["eur-lex.europa.eu", "ec.europa.eu", "enisa.europa.eu", "data.europa.eu", "op.europa.eu"]
    for entry in data.get("catalog", []):
        url = entry.get("source_url", "")
        if not any(domain in url for domain in official_domains):
            failures.append(f"entry '{entry.get('id')}': source_url '{url}' is not from an official EU domain")
    return failures


def validate_coverage_report() -> list[str]:
    failures = []
    coverage_path = REPO_ROOT / "research" / "sources" / "coverage-and-gap-report.md"
    if not coverage_path.is_file():
        failures.append("coverage-and-gap-report.md not found")
    else:
        content = coverage_path.read_text(encoding="utf-8").lower()
        if "rejected" not in content and "gap" not in content:
            failures.append("coverage-and-gap-report.md is missing rejected sources or gaps section")
    return failures


def _source_role_counts(matrix: dict) -> dict:
    return dict(Counter(m.get("source_role") for m in matrix.get("entries", [])))


def run_all_validations() -> tuple[list[str], dict]:
    all_failures: list[str] = []
    try:
        data = load_catalog()
        matrix = load_matrix()
    except FileNotFoundError as e:
        return [str(e)], {"entries": 0}

    all_failures.extend(validate_yaml_structure(data))
    entries = data.get("catalog", [])
    matrix_entries = matrix.get("entries", [])
    if isinstance(entries, list) and entries:
        for i, entry in enumerate(entries):
            all_failures.extend(validate_entry(entry, i))
        all_failures.extend(validate_required_sources(data))
        all_failures.extend(validate_no_duplicate_ids(data))
        all_failures.extend(validate_facts_interpretations_documented(data))
        all_failures.extend(validate_url_integrity(data))
        for entry in entries:
            all_failures.extend(validate_celex(entry))
        all_failures.extend(validate_matrix(data, matrix))
        all_failures.extend(validate_srp_references(data))
        all_failures.extend(validate_rejected_sources(data, matrix))
        all_failures.extend(validate_known_regulatory_metadata(data))

    all_failures.extend(validate_coverage_report())

    summary = {
        "entries": len(entries),
        "active_entries": len(entries),
        "rejected_entries": len(load_rejected().get("rejected_sources", [])),
        "verified_directly": sum(1 for m in matrix_entries if m.get("classification") == "verified_directly"),
        "pending_review": sum(1 for m in matrix_entries if m.get("classification") == "pending_review"),
        "stale": sum(1 for m in matrix_entries if m.get("classification") == "stale"),
        "source_role_counts": _source_role_counts(matrix),
    }
    return all_failures, summary


def main() -> int:
    from datetime import date
    all_failures, summary = run_all_validations()
    if all_failures:
        print(f"FAIL: {len(all_failures)} error(s):")
        for failure in all_failures:
            print(f"  - {failure}")
        return 1
    print(f"PASS: source-catalog validation passed — {summary['entries']} entries, all checks passed.")
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())

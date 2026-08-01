# 18 — Sequência de Implementação & Dependências

## 1. Princípio

A baseline desta Issue #5 **não implementa** — define ordem, contratos e gates de
verificação para que as vagas 2/3 construam sem reinventar stack, limites ou segurança.
Cada item tem um **owner esperado** e um **gate de verificação**.

## 2. Sequência (onde a baseline desbloqueia)

| Ordem | Item | Dependência | Owner esperado (wave) | Gate de verificação |
|---|---|---|---|---|
| 0 | (Concluído) Esta baseline arquitetonal | vision + policies | solution-architect (#5) | merge da PR #5 |
| 1 | Schema do store (`contracts/01-store-schema.yaml`) | baseline | backend-domain-engineer (w2) | `store_schema_valid` |
| 2 | Persistência: SQLCipher + DPAPI key provider | #1 | backend-domain-engineer (w2) | `store_encrypted_at_rest` |
| 3 | Evidence Vault + validateSafety (magic bytes) | baseline, ADR-009 | backend-domain-engineer (w2) | `path_traversal_rejected`, `mime_spoof_detected` |
| 4 | Report Generator (template estatico, escaping) | #3, #2 | rules-reporting-engineer (w2) | `report_is_deterministic` |
| 5 | Rules Engine (pure) + Rule Package loading (signed manifest) | #3 REG-001, #4 REQ-001 | rules-reporting-engineer (w2) | `rule_package_tamper_detected` |
| 6 | Domain Engine (IPC orchestration) | #2, #3, #4 | backend-domain-engineer (w2) | `domain_orchestrates_rules` |
| 7 | UI Renderer + frontend-sanitizer | #6 | frontend-engineer (w2) | `sanitizer_rejects_traversal` |
| 8 | AI Assistant (opt-in, local LLM) | #7 | backend-domain-engineer (w2) | `ai_output_never_reaches_rule_decision` |
| 9 | Update Service (signed release) | ADR-006, ADR-008 | desktop-packaging-engineer (w3) | `update_rejected_without_signature` |
| 10 | Backup/Restore + migrations | #2 | backend-domain-engineer (w3) | `backup_integrity_verified` |
| 11 | Desktop packaging (Electron + signing) | ADR-001, ADR-008 | desktop-packaging-engineer (w3) | code-signed build + ACL check |
| 12 | Observabilidade (logs estruturados, health) | #2 | quality-engineering (w3) | `engine_heartbeat_logged` |

## 3. Gates de qualidade (do `quality-gates.yaml`)

Cada PR subsequente deve passar:
- `universal`: issue_traceability, acceptance_criteria_covered, tests_declared_and_executed,
  documentation_updated, evidence_attached, no_secrets_detected, supervisory_review_complete.
- `code`: formatting, lint, type_check, unit_tests, secret_scanning, dependency_review.
- `regulatory`: official_primary_source, article_or_annex_reference, traceability_to_requirement.

## 4. Mapeamento de tests de contrato → componentes

| Contract test | Componentes envolvidos | Ficheiro de teste esperado |
|---|---|---|
| `scoping.evaluateScope deterministic` | rules-engine, scope-service | `tests/rules/scoping.golden.ts` |
| `ai_output_never_reaches_rule_decision` | domain-engine, ai-assistant, rules-engine | `tests/domain/ai-separation.contract.test.ts` |
| `store_encrypted_at_rest` | local-store, crypto-key-provider | `tests/store/encryption.contract.test.ts` |
| `backup_integrity_verified` | store, vault | `tests/store/backup.contract.test.ts` |
| `mime_spoof_detected` | vault | `tests/vault/mime.contract.test.ts` |
| `path_traversal_rejected` | vault | `tests/vault/path.contract.test.ts` |
| `report_is_deterministic_excluding_timestamp` | report-generator | `tests/report/determinism.golden.test.ts` |
| `update_rejected_without_signature` | update-service | `tests/updates/signature.contract.test.ts` |
| `rule_package_tamper_detected` | rules-engine, rule-package | `tests/rules/package-integrity.contract.test.ts` |
| `config_never_contains_secrets_at_build` | build | `tests/build/no-secrets.test.ts` + CI |

## 5. Dependência entre Issues (resolvimento no kanban)

```
#3 (REG-001 — source catalog)     → [blizzhub-cra-regulatory-research]  (wave 1, ativo)
#4 (REQ-001 — requirements schema) → depende de #3 aceite              (wave 1, bloqueado)
#5 (ARCH-001 — arquitetura)        → ESTA BASELINE                      (wave 1, concluída)
#6 (CI-001 — validação governo)    → DevOps                              (wave 1, ativo)
```

A baseline da Issue #5 **não depende** de #3 ou #4 para ser aprovada (usa o catálogo
como *interface*, não como conteúdo). A implementação concreta do Rules Engine (#5)
**dependerá** de #3 (catalog accepted) e #4 (schema de requisitos).

## 6. Entregas desta baseline (arquivos produzidos)

Ver `README.md` §2 (Critérios de aceitação vs evidência) para o índice completo.

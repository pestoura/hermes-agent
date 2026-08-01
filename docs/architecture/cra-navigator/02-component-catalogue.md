# 02b — Catálogo de Componentes e Interfaces

Catálogo máquina/humano das interfaces públicas entre componentes. Cada interface é
identificada por um ID versionável usado em testes de contrato (contract tests) e no
grafo de dependências (veja `02-component-model.md` seção 3).

> Todos os contratos live em [`contracts/`](contracts/) como YAML versionáveis.

## 1. Legenda

- `sync` = chamada síncrona dentro do mesmo processo.
- `async` = mensagem via IPC / coluna.
- `file-io` = operação de filesystem (sempre atravessando o Evidence Vault).

## 2. Catálogo

### `ui.sanitizer.sanitizeText`
- **Provider**: `frontend-sanitizer` (C2)
- **Protocol**: sync (in-renderer)
- **Input**: `string`
- **Output**: `string` (escaped, no control chars > U+007F exceto newline/tab)
- **Guarantee**: output is safe for markdown + DOM insertion; rejects path-like segments.
- **Contract**: `contracts/00-common-types.yaml#text-sanitization`

### `ui.sanitizer.sanitizeFileMeta`
- **Provider**: C2
- **Protocol**: sync
- **Input**: `FileMeta` {name, size, mime, lastModified, sha256}
- **Output**: `FileMeta` com `name` sanitizado (leaf only, UTF-8, no traversal)
- **Contract**: `contracts/02-evidence-vault.yaml#sanitized-meta`

### `ui.sanitizer.validateSchema`
- **Provider**: C2
- **Protocol**: sync
- **Input**: `obj`, `schemaId: string`
- **Output**: `boolean` + `errors?: ValidationError[]`
- **Guarantee**: every object crossing the IPC boundary is schema-validated here before
  reaching Domain Engine; Domain Engine RE-validates on receive (defense in depth).

### `shell.updates.checkForUpdates`
- **Provider**: `shell` (C1) → `update-service` (C9)
- **Protocol**: async IPC
- **Output**: `UpdateInfo | null` {version, releaseNotes, signature, url}
- **Guarantee**: signature verified before return; no auto-download.

### `shell.updates.applyUpdate`
- **Provider**: C1 → C9
- **Protocol**: async IPC
- **Input**: `{path: string}` (inside app-local temp dir only)
- **Output**: `Promise<void>`
- **Guarantee**: verifies signature again at apply time.

### `shell.evidence.openFilePicker`
- **Provider**: C1
- **Protocol**: async IPC (native dialog)
- **Output**: sanitized path within vault OR `null`
- **Guarantee**: never returns an absolute OS path to the domain layer.

### `domain.scoping.evaluateScope`
- **Provider**: `domain-engine` (C3) → `rules-engine` (C4)
- **Protocol**: sync (in-process)
- **Input**: `ScopeInput` {productType, economicOperator, market}
- **Output**: `ScopeDecision` {inScope: boolean, articles: Article[], rationale: EvidenceRef[]}
- **Guarantee**: deterministic; output reproducible for identical input.

### `domain.assessment.assessProduct`
- **Provider**: C3 → C4
- **Protocol**: sync
- **Input**: `AssessmentInput`
- **Output**: `AssessmentResult` {obligations: ObligationCheck[], gaps: Gap[]}

### `domain.evidence.ingestEvidence`
- **Provider**: C3 → `evidence-vault` (C6)
- **Protocol**: async (file I/O bound)
- **Input**: `{ref: string}` (temp file from picker)
- **Output**: `EvidenceRecord` {id, sha256, mime, size, meta, storedPath}
- **Guarantee**: input validated by C6.validateSafety; path traversal blocked.

### `domain.evidence.queryEvidence`
- **Provider**: C3 → `local-store` (C5)
- **Protocol**: sync
- **Input**: `EvidenceFilter`
- **Output**: `EvidencePage`

### `domain.reporting.generateReport`
- **Provider**: C3 → `report-generator` (C7)
- **Protocol**: sync
- **Input**: `scopeId: string`
- **Output**: `ReportBundle` {markdownPath, manifest}
- **Guarantee**: deterministic template + input digest recorded in manifest.

### `rules.evaluateScopeCRA`
- **Provider**: `rules-engine` (C4)
- **Protocol**: sync (pure function)
- **Input**: `ScopeInput`
- **Output**: `ScopeDecision`
- **Guarantee**: no I/O, no randomness, no external calls.

### `rules.listApplicableArticles`
- **Provider**: C4
- **Protocol**: sync
- **Input**: `scopeId`
- **Output**: `Article[]`

### `rules.checkObligations`
- **Provider**: C4
- **Protocol**: sync
- **Input**: `ass artefact`
- **Output**: `ObligationCheck[]`

### `store.put / store.get / store.query`
- **Provider**: `local-store` (C5)
- **Protocol**: sync (SQLCipher)
- **Input/output**: typed rows
- **Guarantee**: schema-validated on write; migrations run before read.

### `store.migrate`
- **Provider**: C5
- **Protocol**: sync
- **Input**: `toVersion`
- **Output**: `MigrationResult` {from, to, ok, applied: string[]}
- **Guarantee**: atomic per step; rollback file kept until commit.

### `store.backup / store.restore`
- **Provider**: C5
- **Protocol**: async
- **Input**: backup target path
- **Output**: `BackupHandle` / `MigrationResult`
- **Guarantee**: backup encrypted with user key; restore verifies integrity.

### `vault.ingest`
- **Provider**: `evidence-vault` (C6)
- **Protocol**: async
- **Input**: `{tempFile, meta}`
- **Output**: `EvidenceRecord`
- **Guarantee**: SHA-256 content addressing; unsafe files rejected.

### `vault.validateSafety`
- **Provider**: C6
- **Protocol**: sync
- **Input**: `FileMeta + bytes`
- **Output**: `SafetyVerdict` {safe: boolean, reason?: string, mime: string}
- **Guarantee**: checks magic bytes vs claim, size cap, name sanitization.

### `ai.summarise / ai.tagEvidence`
- **Provider**: `ai-assistant` (C8, optional)
- **Protocol**: async
- **Output**: `{text, confidence, provenance}`
- **Guarantee**: provenance tags each result; confidence < 0.8 requires human review.

## 3. Contract-first principle

Cada interface acima tem um contrato versionado em `contracts/`. Mudanças de interface:
1. bump `schema_version` do contrato;
2. implementam migration no `rules-engine` ou `domain-engine`;
3. testes de contrato atualizados.

Ver `18-implementation-sequence.md` para a ordem de implementação.

# 02 — Modelo de Componentes & Catálogo de Interfaces

## 1. Objetivo

Catálogo dos componentes da arquitetura local-first do CRA Navigator, com:

- fronteira de cada componente (responsabilidade única);
- interface pública (contrato);
- dependências direcionais (setas apontam para "depende de");
- localização física (desktop / store / vault).

O modelo está em **três níveis**: Shell (desktop), Domain (lógica) e Persistence (dados).
Nenhum componente da camada Domain ou Persistence aceita input do utilizador sem passar
pelo Shell ou pelo frontend-sanitizer.

## 2. Componentes do MVP

### C1 — Application Shell (`shell`)
- **Camada**: Desktop (processo principal Electron).
- **Responsabilidade**: ciclo de vida da aplicação, gestão de janelas, gate de IPC,
  verificação de atualizações, acesso controlado ao OS (apenas para I/O de ficheiros
  deleagado e update checks).
- **Interface pública**:
  - `ShellAPI.openEvidenceFilePicker()` → `Promise<string | null>` (caminho dentro do vault).
  - `ShellAPI.checkForUpdates()` → `Promise<UpdateInfo | null>`.
  - `ShellAPI.applyUpdate(path)` → `Promise<void>`.
  - `ShellAPI.exportReport(id)` → `Promise<BlobUrl>`.
- **Dependências**: `update-service`, `evidence-vault` (apenas para sanitização de caminho).
- **Nota**: não contém lógica de domínio nem lê diretamente o store.

### C2 — Frontend Sanitizer (`frontend-sanitizer`)
- **Camada**: UI Renderer (processo Chromium isolado).
- **Responsabilidade**: saneie e reencodifique qualquer input proveniente do utilizador ou
  da IA antes de qualquer serialização para o Domain Engine. Neutraliza HTML, caminhos,
  injeção de markdown/template e content-type spoofed.
- **Interface pública**:
  - `sanitizeText(input: string): string`
  - `sanitizeFileMeta(meta: FileMeta): FileMeta`
  - `validateSchema(obj, schemaId): boolean`
- **Dependências**: dependência da Zona C (untrusted input).
- **Contrato**: ver `contracts/00-common-types.yaml`.

### C3 — Domain Engine (`domain-engine`)
- **Camada**: Node service (IPC).
- **Responsabilidade**: orquestração de casos de uso, validação de domínio, delegação ao
  Rules Engine, coordenação entre store e vault. É a única API de negócio.
- **Interface pública (IPC)**:
  - `Domain.evaluateScope(input)` → `ScopeResult`
  - `Domain.assessProduct(req)` → `AssessmentResult`
  - `Domain.ingestEvidence(fileRef)` → `EvidenceRecord`
  - `Domain.generateReport(scopeId)` → `ReportJob`
  - `Domain.queryEvidence(filter)` → `EvidencePage`
- **Dependências**: `rules-engine`, `local-store`, `evidence-vault`, `report-generator`.
- **Nota**: todas as chamadas são síncronas de schema validado; inputs validados pelo
  `frontend-sanitizer` antes de chegar aqui.

### C4 — Rules Engine (`rules-engine`)
- **Camada**: Domain (biblioteca pura, sem I/O).
- **Responsabilidade**: **fonte de verdade regulamentar**. Aplica regras determinísticas
  derivadas do catálogo validado (Issues #3/#4). Não consome IA nem ficheiros do utilizador.
- **Interface pública**:
  - `Rules.evaluateScopeCRA(productType, economicOperator, market)` → `ScopeDecision`
  - `Rules.listApplicableArticles(scopeId)` → `Article[]`
  - `Rules.checkObligations(scopeId, artefact)` → `ObligationCheck[]`
  - `Rules.exportRuleSetMeta()` → `RuleSetMeta` (versão, hash, fonte).
- **Dependências**: rule-package (trusted, versioned, signed — ver ADR-006).
- **Nota**: é a única fonte de verdade para conclusões regulamentares.

### C5 — Local Store (`local-store`)
- **Camada**: persistência local.
- **Responsabilidade**: dados estruturados (scopes, assessments, evidence metadata,
  rule-package meta, report metadata). Cifra em repouso via SQLCipher. Schema versionado.
- **Interface pública**:
  - `Store.put(table, row)`, `Store.get(...)`, `Store.query(indexedExpr)`
  - `Store.migrate(toVersion)`
  - `Store.backup(path?)` → `BackupHandle`
  - `Store.restore(backupFile)` → `MigrationResult`
- **Dependências**: cryptography-key-provider (Zona B).
- **Contrato**: `contracts/01-store-schema.yaml`.

### C6 — Evidence Vault (`evidence-vault`)
- **Camada**: persistência local (filesystem sandboxed).
- **Responsabilidade**: armazenamento de binários de evidências carregadas. Path
  traversal proibido; content-addressing (SHA-256); tipo MIME forçado; tamanho limitado.
- **Interface pública**:
  - `Vault.ingest(file)` → `EvidenceRecord`
  - `Vault.read(id)` → `Blob`
  - `Vault.sha256(blob)` → `string`
  - `Vault.validateSafety(file)` → `SafetyVerdict`
- **Dependências**: cryptography-key-provider (cifra opcional por ficheiro).
- **Contrato**: `contracts/02-evidence-vault.yaml`.

### C7 — Report Generator (`report-generator`)
- **Camada**: Domain (sem I/O direto; escreve em caminos aprovados pelo Domain).
- **Responsabilidade**: gera relatórios Markdown/PDF deterministicamente a partir de store
  + vault. Não aceita input de IA; apenas metadados de proveniância.
- **Interface pública**:
  - `Report.build(scopeId)` → `ReportBundle`
  - `Report.manifest(bundle)` → `Manifest` (hash, template_id, inputs_digest).
- **Dependências**: `local-store`, `evidence-vault`, `rules-engine` (meta only).

### C8 — AI Assistant (`ai-assistant`) — **reversível / opcional**
- **Camada**: externa à Zona A (não confiável).
- **Responsabilidade**: sumário, classificação preliminar, sugestão de texto. Nunca decide.
- **Interface pública**:
  - `AI.summarise(text)` → `{text, confidence, provenance}`
  - `AI.tagEvidence(record)` → `{tags, confidence, provenance}`
- **Dependências**: `frontend-sanitizer` (input), `local-llm-runtime` (opcional).
- **Nota**: quando indisponível, o fluxo é idêntico sem IA (modo degrade).

### C9 — Update Service (`update-service`) — **reversível**
- **Camada**: externo à Zona A.
- **Responsabilidade**: verifica assinatura de releases no GitHub e aplica patch.
- **Interface pública**:
  - `Updates.check()` → `UpdateInfo | null`
  - `Updates.verify(sig, payload)` → `boolean`
- **Dependências**: `shell` (aplicação).

## 3. Matriz de dependências (setas: → "usa")

```
Shell            → evidence-vault (path sanitize), update-service, domain-engine (IPC gate)
FrontendSanitizer → (trusted types only)
Domain Engine    → rules-engine, local-store, evidence-vault, report-generator
Rules Engine     → rule-package (trusted)
Local Store      → crypto-key-provider
Evidence Vault   → crypto-key-provider
Report Generator → local-store, evidence-vault, rules-engine (meta)
AI Assistant     → local-llm-runtime (optional), frontend-sanitizer
Update Service   → github-releases (external, verified)
```

## 4. Localização física por contentor

| Contentor | Componentes | Confiança |
|---|---|---|
| UI Renderer | C2 frontend-sanitizer | Zona C (untrusted input) |
| Node main | C1 shell, C3 domain-engine, C4 rules-engine, C7 report-generator | Zona A/B (core) |
| Store (fs) | C5 local-store | Zona B (cifrada) |
| Vault (fs) | C6 evidence-vault | Zona B (sandbox + content-addressing) |
| Externo | C8 ai-assistant, C9 update-service | Zona D/E |

## 5. Componentes de suporte da vaga 3 (definidos pela baseline, implementados depois)

| Componente | Responsabilidade |
|---|---|
| `crypto-key-provider` | DERIVA e fornece chaves do OS keychain (Windows DPAPI). Nunca persiste a chave em texto no disk do app. |
| `local-llm-runtime` | Runtime local opcional para o AI Assistant (ex.: llama.cpp). Sem rede. |
| `accessibility-gateway` | Camada de acessibilidade (NVDA/JAWS) — não afeta o core. |

Ver `14-desktop-packaging.md` e `11-configuration-and-secrets.md`.

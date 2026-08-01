# 17 — Decisões Adiadas (Deferred Decisions)

Princípio: "Prefer clear contracts and reversible decisions over premature abstraction."
As decisões seguintes **não bloqueiam o MVP** — a arquitetura preserva a opção futura sem
impor complexidade. Cada uma tem um **review gate** e um **owner esperado**.

## 1. Tabela resumida

| ID | Decisão adiada | Por que adiar | Caminho de evolução | Review gate |
|---|---|---|---|---|
| D-01 | Stack de embalagem desktop | Nenhuma ainda implementa; arquitetura é independente | Electron vs Tauri vs .NET MAUI | v1.0-beta, ADR-001 v2 |
| D-02 | Formato do Local LLM runtime | nenhuma prova de performance Windows-native | llama.cpp (GGUF) vs onnx vs provider pluggable | v1.1, ADR-010 v2 |
| D-03 | Auto-update silenciosa | MVP é opt-in; requer signing pipeline maduro | toggle `updates.auto_install_security` | v1.1, ADR-008 |
| D-04 | Seleção de framework UI | React já existente na política visual; mas não fixado | Lightswind open-source (política visual) | v1.0-beta, wave-2 frontend-engineer |
| D-05 | Cloud sync (B2) | Nenhum requisito cloud no MVP; preserva privacy-first | plugin `cloud-sync` boundary | v2.0, ADR-010 (sealed) |
| D-06 | Formato canónico de exportação regulado | Regulated body é future-boundary (B3) | JSON-LD + PDF/A-3 | v2.0, ADR futuro B3 |
| D-07 | SBOM tool | requirement de release, mas tool não decidido | SPDX vs CycloneDX | v1.0, DevOps |
| D-08 | Code signing cert authority | Compra comercial; decisão reversível até assinatura do primeiro release | EV cert vs ov | v0.9, ADR-008 |
| D-09 | SQLite vs IndexedDB para store | ambos cifrados; SQLite/SQLCipher escolhido como baseline-reversível | ADR-002 | v1.0-beta |

## 2. Detalhe

### D-01 — Stack de embalagem desktop
- **Opção temporária**: Electron + electron-builder + code signing.
- **Alternativas rejeitadas (porque maduras demais / proibidas)**:
  - Proton Native / Tauri — bom, mas menos testado no Windows SME; mantido como opção v2.
  - .NET MAUI — exigiria runtime Windows separado; aumenta surface.
- **Reversibilidade**: a boundary `shell` expõe `ShellAPI`; swap de stack não toca TZ-A/B.

### D-02 — Local LLM runtime
- **Opção temporária**: nenhuma (IA é opt-in / desativada no MVP).
- **Review gate**: quando AI opt-in for implementado (wave-2), validar latência/memory.

### D-09 — Motor de base de dados local
- **Opção temporária**: SQLCipher (sqlite) com WAL. [ADR-002]
- **Por que não IndexedDB**: falta transaction atomicity robusta + não há crypto built-in
  tão maduro quanto SQLCipher. IndexedDB mantido como fallback se Electron for trocado
  por web-puro (D-01).

## 3. Decisões que NÃO são adiáveis (blocking)

Estas já foram decididas e são **irreversíveis o suficiente** para bloquear o MVP:

| ID | Decisão | Por que não adiar | ADR |
|---|---|---|---|
| ADR-003 | AI não é fonte de verdade | requisito do produto + issue #5 | ADR-003 |
| ADR-005 | Cifra em repouso via DPAPI | segurança desde o início | ADR-005 |
| ADR-006 | Signed rule package + update | integridade regulamentar crítica | ADR-006 |
| ADR-009 | Magic-byte validation | segurança de ficheiros | ADR-009 |

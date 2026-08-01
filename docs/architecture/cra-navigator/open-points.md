# Open Points & Deferred Decisions (consolidated)

Este documento consolida os pontos abertos e decisões adiadas da baseline da Issue #5.
Conteúdo detalhado em: `17-deferred-decisions.md` (tabela + detalhe) e `16-risk-register.md`.

## 1. Decisões adiadas que não bloqueiam o MVP

| ID | Decisão | Por que não bloqueia | Review gate | Owner esperado |
|---|---|---|---|---|
| D-01 | Stack de embalagem (Electron vs Tauri) | arquitetura independente (ShellAPI boundary) | v1.0-beta, ADR-001 v2 | desktop-packaging-engineer |
| D-02 | Local LLM runtime (llama.cpp vs onnx) | IA é opt-in | v1.1 | backend-domain-engineer |
| D-03 | Auto-update silenciosa | MVP é opt-in | v1.1, ADR-008 | desktop-packaging-engineer |
| D-04 | Framework UI (React vs Lightswind) | política visual fixa, mas não prescritiva | v1.0-beta | frontend-engineer |
| D-05 | Cloud sync (B2) | plugin boundary, nada no MVP | v2.0, ADR-010 | rules-reporting-engineer |
| D-06 | Formato canónico exportação regulador | future boundary (B3) | v2.0 | rules-reporting-engineer |
| D-07 | SBOM tool (SPDX vs CycloneDX) | tooling-level | v1.0 | devops-repository-engineer |
| D-08 | Code signing cert authority | autoridade comercial; reversível até release | v0.9 | desktop-packaging-engineer |
| D-09 | Store engine (SQLCipher vs IndexedDB) | baseline SQLCipher; ambos cifrados | v1.0-beta | backend-domain-engineer |

## 2. Decisões que SÃO blocking (não adiáveis)

| ID | Decisão | ADR |
|---|---|---|
| ADR-003 | AI não é fonte de verdade | ADR-003 |
| ADR-005 | Cifra em repouso via DPAPI | ADR-005 |
| ADR-006 | Signed rule package + update | ADR-006 |
| ADR-009 | Magic-byte validation | ADR-009 |

## 3. Dependências entre Issues (para o orquestrador)

```
#3 (REG-001 — source catalog)        → regulatory-research-engineer  (wave 1, ativo)
#4 (REQ-001 — requirements schema)   → requirements-traceability     (bloqueada até #3 aceite)
#5 (ARCH-001 — arquitetura)          → ESTA BASELINE                 (concluída)
#6 (CI-001 — validação governo)      → devops-repository-engineer    (wave 1, ativo)
```

- A baseline da #5 **não depende** de #3/#4 para ser aprovada — consome-as como
  *interface* (contracts), não como conteúdo.
- A implementação do Rules Engine (vaga 2) **depende** de #3 (catalog accepted) e #4
  (schema de requisitos) para ter conteúdo autoritativo.

## 4. Restrições que permanecem em aberto (para vaga 3)

- Threat model de supply-chain mais profundo (npm native modules, asar integrity) —
  parcialmente coberto em `15-threat-model.md` (T-DEPCOMP); detalhe técnico na vaga 3.
- Threat model de runtime Windows mais profundo (AppContainer, exploit mitigations) —
  coberto em `14-desktop-packaging.md`; hardening detalhado na vaga 3.

## 5. Condições de revisão da baseline

A revista da baseline deve ocorrer:
- após #3 (catalog) e #4 (schema) serem aceites — para validar que o Rules Engine
  contract está alinhado;
- após a primeira iteração de implementação do store (vaga 2) — para validar
  `contracts/01-store-schema.yaml`;
- antes do primeiro release assinado (v0.9) — para validar ADR-008.

# BlitzHub CRA Navigator — Arquitetura (baseline local-first)

## 0. Visão geral

Documento de índice da arquitetura inicial do **BlitzHub CRA Navigator**, produzido no âmbito da
[Issue #5 — ARCH-001](/home/estourpm/.hermes/kanban/boards/blitzhub-cra-navigator/workspaces/t_905d1aff/_repo?att=0)
(`[ARCH-001] Definir arquitetura local-first do CRA Navigator`).

O documento não implementa funcionalidades. Ele define: fronteiras, fluxos, contratos,
decisões (ADRs), threat model, risco e decisões adiadas, para que as vagas 2 e 3 construam
o produto de forma coerente.

## 1. Acesso rápido aos artefactos

| Artefacto | Caminho |
|---|---|
| Contexto do sistema e contentores | `docs/architecture/cra-navigator/01-system-context.md` + `diagrams/01-c4-context.drawio` / `.svg` |
| Modelo de componentes e catálogo | `docs/architecture/cra-navigator/02-component-model.md` |
| Fluxos de dados e fronteiras de confiança | `docs/architecture/cra-navigator/03-data-flows.md` + `diagrams/03-data-flow-trust-boundaries.drawio` |
| Persistência local, backup, restore e migrações | `docs/architecture/cra-navigator/04-persistence-and-data-lifecycle.md` |
| Motor de regras e separação de IA | `docs/architecture/cra-navigator/06-rules-and-ai-boundary.md` |
| Conversa: regras determinísticas vs IA | `docs/architecture/cra-navigator/07-deterministic-vs-ai.md` |
| Evidências e armazenamento de ficheiros | `docs/architecture/cra-navigator/08-evidence-ingestion.md` |
| Geração de relatórios | `docs/architecture/cra-navigator/09-report-generation.md` |
| Atualizações e mecanismo de update | `docs/architecture/cra-navigator/10-update-mechanism.md` |
| Configuração e segredos | `docs/architecture/cra-navigator/11-configuration-and-secrets.md` |
| Observabilidade (software local) | `docs/architecture/cra-navigator/12-observability.md` |
| Fronteiras de integração futuras | `docs/architecture/cra-navigator/13-future-integration-boundaries.md` |
| Embalagem desktop Windows | `docs/architecture/cra-navigator/14-desktop-packaging.md` |
| Threat model | `docs/architecture/cra-navigator/15-threat-model.md` |
| Registo de riscos | `docs/architecture/cra-navigator/16-risk-register.md` |
| Decisões adiadas | `docs/architecture/cra-navigator/17-deferred-decisions.md` |
| Sequência de implementação e dependências | `docs/architecture/cra-navigator/18-implementation-sequence.md` |
| Catálogo de componentes e interfaces | `docs/architecture/cra-navigator/02-component-catalogue.md` |
| ADRs | `docs/architecture/cra-navigator/decisions/` |
| Contratos de componente | `docs/architecture/cra-navigator/contracts/` |

> Nota de layout: os diagramas são versionáveis em formato `.drawio` (XML, editável) e
> exportados para `.svg` (visão). Ambos vivem em `docs/architecture/cra-navigator/diagrams/`.

## 2. Critérios de aceitação da Issue #5 vs evidência

| Critério da Issue #5 | Evidência na arquitetura |
|---|---|
| Define frontend, domínio, persistência, motor de regras, evidências e relatórios | `02-component-model.md`, `04-persistence-and-data-lifecycle.md`, `06-rules-and-ai-boundary.md`, `08-evidence-ingestion.md`, `09-report-generation.md` |
| Modelo desktop Windows sem exigir Docker ao utilizador | `14-desktop-packaging.md`, ADR-001, ADR-004 |
| Separa lógica regulamentar determinística de funcionalidades assistidas por IA | `07-deterministic-vs-ai.md`, ADR-003, `06-rules-and-ai-boundary.md` |
| Limites de confiança e tratamento de ficheiros carregados | `08-evidence-ingestion.md`, `15-threat-model.md`, `03-data-flows.md` |
| Armazenamento local, cifragem, backup, restore e migrações | `04-persistence-and-data-lifecycle.md`, ADR-002, ADR-005 |
| Interfaces internas e contratos entre componentes | `02-component-catalogue.md`, `contracts/` |
| Threat model inicial e principais riscos | `15-threat-model.md`, `16-risk-register.md` |
| Regista decisões em ADRs, incluindo alternativas rejeitadas | `decisions/ADR-001.md` … `ADR-006.md` |
| Identifica decisões que podem ser diferidas sem bloquear o MVP | `17-deferred-decisions.md` |

## 3. Princípios arquitetónicos aplicados

- **Local-first**: zero dependência de serviço externo para a função MVP; tudo corre offline.
- **Limites de confiança explícitos**: tudo o que entra pelo utilizador (ficheiros, IA, pacotes de regras) cruza uma fronteira de confiança com validação.
- **Deterministico separado de AI**: o motor de regras é a fonte de verdade regulamentar; IA é apenas assistência auditável.
- **Migrações e versionamento**: modelo de dados versionado `schema_version` com caminho de migração.
- **Reveribilidade**: decisões incertas são reversíveis ou registadas como adiadas.
- **Mínima dependência externa**: sem cloud no MVP; a IA é opcional e degrade gracefulmente.

## 4. Não-cobertura (fora de âmbito desta baseline)

- Implementação funcional (reservado às vagas 2/3).
- Escolha comercial definitiva / licenciamento.
- Infraestrutura cloud de produção.
- Normas pagas ou conteúdo sem direito de redistribuição.

## 5. Estado de revisão

| Campo | Valor |
|---|---|
| Versão da baseline | `1.0` |
| Autor | Solution Architect (agente Hermes) |
| Issue GitHub | #5 (ARCH-001) |
| Estado | `baseline` |
| Próxima revisão | após Issue #3 (catálogo de fontes) e #4 (schema de requisitos) — veja `18-implementation-sequence.md` |

# 13 — Fronteiras de Integração Futuras

Estas fronteiras são **definidas pela baseline** para que a evolução para appliance/cloud
não exija re-arquitetura. Nenhuma delas é implementada no MVP.

## 1. Princípio

Qualquer integração futura **deve** cruzar uma fronteira de confiança explícita, com
validação de schema e integridade. O core local-first **não** é modificado para
acreditar em cloud.

## 2. Boundaries versionáveis

### B1 — Appliance virtual
- **Fronteira**: `appliance-bridge` (novo contentor, Zona D).
- **Interface**: export/import de backup via `Store.backup` (`BackupHandle`).
- **Auth**: mutual TLS ou signed token (definir no ADR futuro B1).
- **Invariança**: o appliance não altera o Rules Engine local.

### B2 — Serviço cloud opcional
- **Fronteira**: `cloud-sync` (Zona D, opt-in).
- **Interface**: `Store.exportDelta` / `Store.importDelta` (CRDTs ou LWW-resolve).
- **Confiança**: dados cloud são tratados como **untrusted** ao import; reválidos.
- **Cifrra de ponta-a-ponta**: chave nunca sai do cliente (definir no ADR futuro B2).
- **Proibição**: cloud **não** vê o master key, nem ficheiros de evidence não-cifrados.

### B3 — Regulated body (market surveillance)
- **Fronteira**: `report-export`.
- **Interface**: `ReportGenerator.buildExport(scopeId)` → selo + manifest assinado.
- **Formato canónico**: JSON-LD + PDF/A-3 (ISO 19005-3).
- **Selo de timestamp**: via TSA externa (definir no ADR futuro B3).

### B4 — Local LLM runtime
- **Fronteira**: `ai-assistant` (Zona D).
- **Interface**: provider plugin (`AI.summarise`, `AI.tagEvidence`).
- **Invariança**: AI output **nunca** é input diretamente para o Rules Engine.
- **Modelos suportados**: llama.cpp (GGUF) — offline, sem rede. Futuro: provider pluggable.

### B5 — CI/CD de pipelines
- **Fronteira**: external contributor (GitHub Actions).
- **Interface**: apenas leitura de artefactos públicos (store schema, rule package meta).
- **Proibição**: não lê dados do utilizador nem ficheiros de evidence.

## 3. Matriz de integridade entre zonas

| Origem → Destino | Zona de destino | Validação exigida |
|---|---|---|
| UI / AI → Domain | A | schema + revalidação (defense in depth) |
| Domain → Store | B | cifra + schema |
| Domain → Vault | B | sanitize path + magic bytes |
| Domain → Rules Engine | A (pure) | input schema + determinismo test |
| External → App | D | assinatura + hash |
| App → Regulated body (futuro) | externo | selo + manifest assinado |

## 4. Reversibilidade

Todas as fronteiras acima são **plugin boundaries** (interface versionada). Adicionar B1–B5
não requer alterar a Zona A ou B — apenas novos adaptadores na Zona D. Ver ADR-005 (sealed)
e ADR-010 (pluggable vault).

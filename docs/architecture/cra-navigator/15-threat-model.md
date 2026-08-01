# 15 — Threat Model

**Método**: abordagem baseada em elementos de risco (STRIDE) e linha de defesa (trust
zones). Estrutura YAML versionável em `docs/architecture/cra-navigator/threat-model.yaml`.

> Este threat model não é uma prova de conformidade legal. Documenta riscos e controles
> arquitetónicos com caminhos de verificação.

## 1. Trust zones recapitulado

| ID | Zona | Descrição | Trust Level |
|---|---|---|---|
| TZ-C | UI Renderer + frontend-sanitizer | Input do utilizador/IA | Untrusted |
| TZ-A | Domain Engine + Rules Engine | Lógica de decisão | Trusted core |
| TZ-B | Local Store + Evidence Vault | Persistência cifrada | Protected at rest |
| TZ-D | Update Service + AI Assistant | Externo/opcional | Untrusted/Optional |
| TZ-OS | Windows OS | Sistema operativo do utilizador | Untrusted (shared) |

## 2. Elementos de risco (STRIDE)

### T-FILEUP — Ficheiros carregados maliciosos
- **Categoria**: Spoofing / Tampering
- **Atacante**: utilizador (malicioso ou negligente) carrega ficheiro.
- **Impacto**: execução arbitrária, traversal, MIME spoofing.
- **Controlo**:
  - `vault.validateSafety`: magic-bytes verification (ADR-009).
  - Tipo/MIME proibido em lista negra + allowlist.
  - Sandbox de extraction para archives (profundidade/quota limitada).
- **Verificação**: teste `mime_spoof_detected`, `path_traversal_rejected`,
  `zip_bomb_limit` (para vaga 2).
- **Severidade**: HIGH (confidencialidade/integridade de host).

### T-PATHTRAVERSAL — Path traversal no vault
- **Categoria**: Tampering / Information disclosure
- **Atacante**: utilizador malicioso (nome de ficheiro `..\..\windows\system32`).
- **Impacto**: escrita/fora do vault ou leitura de ficheiros do OS.
- **Controlo**: `Vault.ingest` reduce a leaf-only, rejeita `..`, `/`, `\\`, NUL,
  `\\uXXXX`; path é content-addressado (`<sha256>.<ext>`).
- **Verificação**: teste `path_traversal_rejected` + fuzzing de nomes.
- **Severidade**: HIGH.

### T-ARCHIVE — Extração de arquivos
- **Categoria**: Denial of Service / Tampering
- **Atacante**: zip-bomb ou arquivos com member paths traversal.
- **Impacto**: disk exhaustion, overwrite.
- **Controlo**: quota de extraction (200 MB total, 10.000 members, depth 5); re-aplica
  `validateSafety` a cada member; member paths sanitizados.
- **Verificação**: teste `zip_bomb_limit`.
- **Severidade**: MEDIUM.

### T-AI — Contaminação de decisões pela IA
- **Categoria**: Tampering / Repudiation
- **Atacante**: IA maliciosa ou prompt injection no input.
- **Impacto**: conclusão regulamentar alterada sem fonte determinística.
- **Controlo**: **separação hard** — AI output nunca toca Rules Engine; provenance +
  confidence sempre registados; confidence < 0.8 = revisão humana.
- **Verificação**: teste `ai_output_never_reaches_rule_decision`.
- **Severidade**: CRITICAL (integridade regulamentar).

### T-DATASTORE — Exposição de dados locais
- **Categoria**: Information disclosure
- **Atacante**: terceiro com acesso físico ao disco.
- **Impacto**: acesso a evidências, decisões, rule package meta.
- **Controlo**: cifra em repouso (SQLCipher AES-256-GCM, DPAPI key); folder `%LOCALAPPDATA%`
  ACL'd ao utilizador Windows.
- **Verificação**: teste `store_encrypted_at_rest`; inspecção de folder (ACEs).
- **Severidade**: HIGH.

### T-SECRETS — Vazamento de segredos
- **Categoria**: Information disclosure
- **Atacante**: developer, CI logs, repositório público.
- **Impacto**: master key, license keys.
- **Controlo**: chave no DPAPI (nunca em texto); `secret_scan` no CI; build-time check
  de `config/*.json`. Proibição no repo (`public-repository-policy.yaml`).
- **Verificação**: teste `config_never_contains_secrets_at_build`; secret scanning no CI.
- **Severidade**: CRITICAL.

### T-REPORT-INJECTION — Injeção em relatórios
- **Categoria**: Spoofing / Tampering
- **Atacante**: input do utilizador ou output de IA em texto do relatório.
- **Impacto**: relatório fraudulento que parece canónico.
- **Controlo**: template engine com escaping por defeito; AI output sanitizado;
  `inputs_digest` + `provenance[]` no manifest do report.
- **Verificação**: teste `report_is_deterministic_excluding_timestamp`; teste de
  injection em field `product.name`.
- **Severidade**: MEDIUM.

### T-DEPCOMP — Compromisso de dependências
- **Categoria**: Tampering / Denial of service
- **Atacante**: supply chain (npm, native modules).
- **Impacto**: execução de código, exfiltração.
- **Controlo**: `npm audit`, lockfile versionado, Dependabot, SBOM (quality gates). Para
  Electron: integridade do asar verificada.
- **Verificação**: `dependency_review` + `npm audit --audit-level=high` no CI.
- **Severidade**: HIGH.

### T-UPDATE — Mecanismo de atualização inseguro
- **Categoria**: Tampering / Elevation of privilege
- **Atacante**: MITM ou repositório comprometido.
- **Impacto**: instalação de binário malicioso.
- **Controlo**: SHA-256 comparado; assinatura verificada com chave pública embutida
  (trusted-root); download apenas a `temp/`; opt-in ao utilizador.
- **Verificação**: teste `update_rejected_without_signature`.
- **Severidade**: CRITICAL.

### T-RULEPKG — Integridade do pacote de regras
- **Categoria**: Tampering
- **Atacante**: utilizador ou attacker que substitui o package.
- **Impacto**: decisões regulamentais falsas.
- **Controlo**: manifest assinado verificado no boot; atualização apenas via Update Service
  (Fluxo 8). Nenhum package do utilizador é aceite.
- **Verificação**: teste `rule_package_tamper_detected`.
- **Severidade**: CRITICAL.

### T-WIN-PRIV — Fronteira de privilégio no Windows
- **Categoria**: Elevation of privilege
- **Atacante**: processo com menos privilégio tenta escalar.
- **Impacto**: acesso a stores de outros utilizadores.
- **Controlo**: app roda como standard user; dados em `%LOCALAPPDATA%` (ACL per-user);
  nenhuma escrita em HKLM/Program Files no MVP.
- **Verificação**: smoke test de abertura na pasta falha para outro utilizador.
- **Severidade**: MEDIUM.

### T-BACKUP — Confidencialidade e integridade do backup
- **Categoria**: Information disclosure / Tampering
- **Atacante**: terceiro com acesso ao ficheiro de backup.
- **Impacto**: restauro de dados adulterados ou acesso não autorizado.
- **Controlo**: backup cifrado (chave do utilizador); `integrity_hash` (SHA-256) verificado
  antes de restore; password-derived export opcional.
- **Verificação**: teste `backup_integrity_verified`; `restore_rejects_corrupt`.
- **Severidade**: HIGH.

## 3. Matriz de risco

| Threat ID | Severidade | Likelihood | Tratamento | Verificação | Bloqueia MVP? |
|---|---|---|---|---|---|
| T-FILEUP | HIGH | medium | prevent+detect | testes de ingestão | não (arqu. coberta) |
| T-PATHTRAVERSAL | HIGH | medium | prevent | tests + fuzz | não |
| T-ARCHIVE | MEDIUM | low | prevent | teste zip-bomb | não |
| T-AI | CRITICAL | low | prevent+detect | contract test | **SIM** (AI separation) |
| T-DATASTORE | HIGH | medium | prevent | store_encrypted_at_rest | não (cifra definida) |
| T-SECRETS | CRITICAL | medium | prevent | secret_scan + build check | não (política) |
| T-REPORT-INJECTION | MEDIUM | low | prevent | report injection test | não |
| T-DEPCOMP | HIGH | medium | detect | npm audit + SBOM | não |
| T-UPDATE | CRITICAL | low | prevent | signature test | não (assinatura definida) |
| T-RULEPKG | CRITICAL | low | prevent+detect | tamper test | **SIM** (package boundary) |
| T-WIN-PRIV | MEDIUM | low | prevent | privilege smoke | não |
| T-BACKUP | HIGH | low | prevent+detect | backup integrity test | não (backup definido) |

## 4. Linha de defesa (defense in depth)

1. **Zona C** — sanitizador de input (primeira linha).
2. **IPC gate** — schema validation no Domain Engine (revalidação).
3. **Zona A** — Rules Engine como fonte de verdade (nunca input de IA).
4. **Zona B** — cifra em repouso + content-addressing.
5. **Zona D** — assinatura/verificação em updates e rule package.

## 5. Verificação (mapping para quality gates)

Todos os controles acima têm um **caminho de verificação** expresso como teste de
contrato (contract test) ou CI check, listados em `18-implementation-sequence.md`.
Nenhum controlo é declarado sem verificação (princípio do SOUL do Solution Architect).

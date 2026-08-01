# 12 — Observabilidade (software local)

## 1. Princípio

O produto é local-first. A observabilidade é **on-device** e **não telemétrizado sem
consentimento explícito**. Em nenhum momento do MVP são enviados dados para serviços
externos.

## 2. Logs estruturados (Zona A/B)

- Formato: JSONL com `timestamp`, `level`, `component`, `traceId`, `event`, `context`.
- Nível por padrão: `INFO`; `DEBUG` apenas em modo diagnóstico (feature flag).
- **Nenhum** log contém secrets, dados pessoais brutos ou chaves. Campos sensíveis são
  hashados ou omitidos (`[REDACTED]`).
- Local: `%LOCALAPPDATA%\BlitzHub\CRANavigator\logs\` — rotacionado (max 10 MB × 5 files).

### 2.1 Eventos de segurança (não repúdio)

| Evento | Zona | Log? | Observação |
|---|---|---|---|
| `rule_package_loaded` | A | sim | inclui sha256 verificado |
| `evidence_ingested` | A/B | sim | inclui sha256, mime, size |
| `ai_output_used` | C/D | sim | provenance, confidence, traceId |
| `update_applied` | D | sim | version, signature_verified |
| `report_generated` | A | sim | inputs_digest |
| `failed_validation` | C → A | sim (WARN) | motivo da rejeição |
| `backup_created` | B | sim | integrity_hash |

## 3. Telemetria (futuro, opt-in)

- `telemetry.enabled` default `false`.
- Se ativado: apenas contagens e eventos sem PII (nada de nomes de ficheiros/valores).
- Qualquer coleta é coberta por consentimento separado (GDPR) — fora do MVP.

## 4. Diagnóstico offline

- `Help → Export diagnostics` produz um `.zip` de logs + manifest de versão + rule
  package meta (`trace_only=true` — nada de PII).
- Não inclui o master key ou ficheiros de evidência.

## 5. Verificações de saúde (health checks)

- Boot: verifica integridade do store (`PRAGMA integrity_check`), chave do vault e versão
  do rule package.
- Runtime: heartbeat de `Domain Engine` (evento `engine_heartbeat`).
- Report: `report_generator_health` (tempo de geração, input size).

## 6. Acessibilidade

- Eventos de acessibilidade são expostos como atributos ARIA no Renderer; não são
  telemetrizados. Veja `14-desktop-packaging.md`.

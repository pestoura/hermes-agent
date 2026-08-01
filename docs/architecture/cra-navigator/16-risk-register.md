# 16 — Registo de Riscos

## 1. Princípio

Todo risco arquitetónico material é registado com: identidade, severidade, probabilidade,
tratamento, proprietário, estado e prova de verificação. Nenhum risco é "aceite" sem
tratamento documentado.

## 2. Matriz resumida

| ID | Risco | Zona | Sev | Prob | Tratamento | Owner | Estado |
|---|---|---|---|---|---|---|---|
| RSK-01 | Contaminação de decisões pela IA | TZ-A | Crit | Low | Separar hard (ADR-003) | SA | Controlado |
| RSK-02 | Integridade de pacote de regras | TZ-A | Crit | Low | Signed manifest (ADR-006) | SA | Controlado |
| RSK-03 | Atualização insegura | TZ-D | Crit | Low | SHA-256 + signature (ADR-006) | DevOps | Controlado |
| RSK-04 | Exposição de dados locais | TZ-B | High | Med | SQLCipher + DPAPI (ADR-005) | SA | Controlado |
| RSK-05 | Vazamento de segredos | TZ-A/B | Crit | Med | secret_scan + build check | DevOps | Controlado |
| RSK-06 | Ficheiros carregados maliciosos | TZ-C | High | Med | validateSafety (ADR-009) | Backend | Definido |
| RSK-07 | Path traversal / archive | TZ-B | High | Med | content-addressing | Backend | Definido |
| RSK-08 | Compromisso de dependências | TZ-D | High | Med | npm audit + SBOM | DevOps | Definido |
| RSK-09 | Injeção em relatórios | TZ-A | Med | Low | template escaping | Rules | Definido |
| RSK-10 | Fronteira de privilégio Windows | TZ-OS | Med | Low | standard user + ACL | Desktop | Definido |
| RSK-11 | Backup corrupto/roubado | TZ-B | High | Low | integridade + cifra | Backend | Definido |
| RSK-12 | Drift de schema sem migração | TZ-B | Med | Med | motor de migration | Backend | Reversível |
| RSK-13 | Não-degrada offline | TZ-D | Med | Low | modo degrade (IA opt-in) | SA | Definido |

## 3. Detalhe dos riscos críticos (MVP-blocking)

### RSK-01 — T-AI (AI contamination)
- **Critério de aceitação**: `ai_output_never_reaches_rule_decision` passa.
- **Verificação**: contract test + golden test do Rules Engine.
- **Estado**: controlado pela arquitetura (separation hard); implementação vaga 2.

### RSK-02 — T-RULEPKG (rule package integrity)
- **Critério de aceitação**: `rule_package_tamper_detected` passa.
- **Verificação**: test tamper + unsigned-package-rejected.
- **Estado**: controlado pelo ADR-006; implementação vaga 2.

### RSK-03 — T-UPDATE (unsafe update)
- **Critério de aceitação**: `update_rejected_without_signature` passa.
- **Verificação**: test mock-release sem assinatura.
- **Estado**: controlado pelo ADR-006/008.

## 4. Riscos reversíveis / adiados

| ID | Risco | Por que é reversível | Review gate |
|---|---|---|---|
| RSK-DEF-01 | Stack Electron vs Tauri | boundary-independent | ADR-001 v2 |
| RSK-DEF-02 | SBOM tool choice | tooling-level | v1.1 |
| RSK-DEF-03 | Cloud sync design | plugin boundary (B2) | ADR-010 v2 |

## 5. Métrica de saúde (para supervisão ChatGPT)

- `critical_findings_open = 0` no escopo da baseline.
- `mvp_blocking_risks_controlled = 2/2` (RSK-01, RSK-02).
- Todos os controles têm `verification` mapeada (nenhum "declarado sem verificação").

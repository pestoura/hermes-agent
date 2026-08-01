# 09 — Geração de Relatórios

## 1. Princípio

Os relatórios do CRA Navigator são **determinísticos** e **reprodutíveis**. Não são
gerados a partir de texto de IA; apenas dados validados do Local Store e Evidence Vault são
incorporados. Texto de IA, se incluído, é sanitizado e marcado com proveniância.

> A arquitetura deste documento não constitui garantia de conformidade legal.
> (Ver `README.md` §5.)

## 2. Entradas do relatório

| Input | Fonte | Confiança |
|---|---|---|
| `ScopeDecision` | Rules Engine | Alta (determinístico) |
| `ObligationCheck[]` | Rules Engine | Alta |
| `Gap[]` | Rules Engine | Alta |
| Metadados de evidência | Evidence Vault + store | Alta (integridade verificada) |
| Texto de IA (sumário opcional) | AI Assistant | Baixa (provenance=ai, confidence) |
| Metadados de processo | store (trace, timestamps) | Média |

## 3. Pipeline

```
Domain.reporting.generateReport(scopeId)
  → Rules Engine (scope + obligations + gaps)
  → Local Store (evidence meta, decisions log)
  → Evidence Vault (sha256 dos ficheiros referenciados)
  → Report Generator (template + dados)
  → ReportBundle { markdown, manifest }
  → manifest { inputs_digest, template_id, rulePackage, generated_at, provenance[] }
```

- **Template**: estático, versionado (`rules/report-templates/`), assinado juntamente
  com o Rule Package. Não aceita IA.
- **`inputs_digest`**: hash (SHA-256) de todos os inputs serializados. Qualquer alteração
  de input invalida o digest → report é regenerado.
- **`provenance[]`**: lista de `EvidenceRef` incluídas, cada uma com `source` (rules |
  evidence | ai) e `confidence` (quando AI).

## 4. Formatos de saída (MVP)

| Formato | Descrição |
|---|---|
| Markdown | fonte canónica, versionável, ligado do GitHub |
| PDF | export estático (header/footer fixos, sem JS) |
| HTML self-contained | preview offline (sem JS externo) |

**Proibido**: HTML com JS, embedded objects, ou links externos não-sanitizados.
(Sanitize via allowlist: apenas `<a href="...">` e imagens do próprio vault.)

## 5. Referência a evidências

- Relatório referencia cada evidência pelo `EvidenceRecord.id` (SHA-256).
- O binário **nunca** é embutido no report (apenas referência + metadados).
- O utilizador anexa o vault como complemento (zip assinado).

## 6. Integridade e não-repúdio

- Cada report carrega `manifest.inputs_digest` e `rulePackage.version.sha256`.
- O report é **append-only logado**: `report_manifests` regista `generated_at`,
  `inputs_digest`, `user_id`, `template_version`. Não há update — regeneração cria novo.
- Hash do report publicável no footer (Markdown + PDF) para verificação offline.

## 7. Injeção (report injection)

- Nenhum input do utilizador (nome do produto, descrição, tags de IA) é inserido no
  template sem escaping. Template engine usa escaping por defeito (ex.: `{{var}}` e
  `{{{html}}}` diferenciados; por defeito `{{var}}` escapa HTML).
- Texto de IA passa pelo `frontend-sanitizer` e é re-parsed como Markdown seguro.
- Ver threat model `T-REPORT-INJECTION`.

## 8. Reprodutibilidade

- Mesmo `scopeId` + mesmo `rulePackage` + mesmos inputs → report idêntico (excepto
  `generated_at`). Teste golden: `report_is_deterministic_excluding_timestamp`.

## 9. Exportação e boundary futuro

Exportação para "Regulated body" (veja `13-future-integration-boundaries.md`) exige:
- assinatura do manifest;
- selo de timestamp (definir no ADR futuro).
Não é parte do MVP.

# 07 — Decisões Determinísticas vs. Assistência por IA

Contrato de separação exigido pela Issue #5 e pelo Princípio do Produto
(`docs/product/vision.md` § "Princípios do produto").

## 1. Fonte de verdade vs. assistência

| Dimensão | Determinístico (Rules Engine) | AI-Assisted |
|---|---|---|
| Autoridade | **Sim** — única fonte de verdade regulamentar | **Não** — nunca autoritativo |
| Input | Schema-validado, do Domain Engine | Texto/ficheiro sanitizado pela Zona C |
| Output | `ScopeDecision`, `ObligationCheck`, `Gap[]` | resumo, tag, sugestão de texto |
| Determinismo | Sim (pure function, seed-test) | Não (probabilístico) |
| Proveniência | `rules-engine` + `rulePackage.version.sha256` | `ai-assistant` + `confidence` + `traceId` |
| Revisão humana | Implícita (input do utilizador) | **Sempre** quando confidence < 0.8 ou output afeta UI |

## 2. Onde a IA pode influenciar uma conclusão (e como)

A IA **nunca** escreve diretamente numa conclusão do Rules Engine. Se uma sugestão de IA
poderia alterar uma conclusão, o caminho obrigatório é:

```
AI output
  → frontend-sanitizer (provenance=ai)
  → UI (confirmação humana)
  → Domain Engine (validado)
  → Rules Engine (re-decide com base em factos, não em texto de IA)
  → Decision
```

### 2.1 Exemplo: "estende a cobertura"
- IA propõe: "Este produto parece também abranger [obrigação X]".
- UI exibe a sugestão marcada `provenance=ai confidence=0.62`.
- O utilizador revisa e aceita.
- O Domain Engine envia o caso ao **Rules Engine**, que re-evalúa com os mesmos factos.
- A decisão final é do Rules Engine; a sugestão de IA é apenas evidência de processo
  (`EvidenceRef.provenance = "ai-assistant"`).

## 3. Proveniência mínima exigida

Todo output da IA que atinja uma decisão deve incluir, **antes** da confirmação:

| Campo | Obrigatório? | Verificação |
|---|---|---|
| `provenance` | Sim | sempre `"ai-assistant"` |
| `confidence` | Sim | `0.0–1.0`; < 0.8 = revisão obrigatória |
| `traceId` | Sim | ligação ao input que originou |
| `grounding` | Sim (quando houver) | lista de `EvidenceRef` que a IA consultou |
| `expires_at` | Sim | para propostas; expira em 24h de inatividade (não se stale |

## 4. Uncertainties expostas

- **Unknown facts**: quando o Rules Engine não tem regra para um caso, devolve
  `Decision.unknown = { articles: [], open_questions: [...] }` — **nunca** uma
  suposição da IA.
- **Confidence display**: a UI mostra `confidence` colorido (verde ≥ 0.8, amarelo
  0.5–0.8, vermelho < 0.5) e exige ação explícita para < 0.8.
- **Audit trail**: todo output de IA e decisão do Rules Engine são append-only no
  `decisions_log` do store (não mutáveis).

## 5. Comportamento offline / sem IA

Quando o local LLM runtime não está disponível ou o utilizador desativa a IA:

- A aplicação continua funcional (determinístico sempre disponível).
- Blocos de UI "assistente" são desativados/grisados; tooltips explicam o modo degrade.
- A feature flag `ai.enabled` defaulta a `false` até o utilizador optar.
- Nenhum output de IA é cacheado como decisão.

## 6. Verificação (contrato de teste)

- Teste: `ai_output_never_reaches_rule_decision` — falha se `Decision.provenance` inclui
  `"ai-assistant"`.
- Teste: `deterministic_decision_stable` — golden test do Rules Engine.
- Teste: `confidence_below_threshold_requires_human` — simula AI output confidence=0.4.

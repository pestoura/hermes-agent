# 06 — Motor de Regras e Fronteira de Confiança Regulamentar

## 1. Princípio geral

> O **Rules Engine** é a **única fonte de verdade regulamentar**. Ele não consome IA,
> não lê ficheiros do utilizador e não toma decisões com base em input não-validado.

Qualquer conclusão do CRA Navigator ("inside scope", "obrigação X aplicável",
"gap Y") **deve** provenir exclusivamente do Rules Engine. A IA pode sugerir texto ou
classificar, mas **nunca** afeta uma conclusão sem passar pelo Rules Engine e sem
confirmação registada.

## 2. Estrutura do motor de regras

```
Rule Package (trusted, versioned, signed)      <-- Issue #3/#4
        |
        | loads (hash + signature verified)
        v
Rules Engine (pure functions, no I/O)
        |
        | evaluate(product, scope, artefact, ...)
        v
Rule Decision { articles, obligations, gaps, evidence_refs, provenance }
```

### 2.1 Rule Package
- **Formato**: bundle versionado (`rules/v1.0.0/cra-rules.yaml` + `manifest.json`).
- **Versão**: semantic version derivada da data da fonte oficial (Ex.: `2024.2847.1`).
- **Integridade**: `manifest.json.sha256` assinado pelo maintainer; verificado no boot
  (ADR-006). Atualiza automaticamente via Update Service (Fluxo 8) — nunca pelo utilizador.
- **Conteúdo**: apenas factos oficiais (artigos, anexos) + tabelas de decisão
  (lookup determinísticas). Nenhum texto interpretativo da IA.

### 2.2 Rules Engine (biblioteca pura)
- **Linguagem-sugestão**: TypeScript pura (compilada e testada isoladamente). [reversível, ADR-007]
- **Entradas**: apenas objetos schema-validados do Domain Engine.
- **Saídas**: `RuleDecision` tipado, imutável, serializável.
- **Determinismo**: `evaluate(x)` é uma função pura — identico input → identico output
  (verificado por golden-test com seeds fixas).
- **Sem efeitos colaterais**: não escreve no store nem vault; o Domain Engine persiste.

## 3. Interface com o Domain Engine

Via `contracts/03-rules-engine.yaml`:
```
ScopeDecision {
  inScope: boolean,
  articles: Article[],          // Artigo + secção de origem
  rationale: EvidenceRef[],     // referências às secções validadas (Issue #3)
  rulePackage: { id, version, sha256, signature },  // proveniância
}
```

## 4. Onde a IA pode atuar (e onde não)

| Capacidade | IA? | Controlo |
|---|---|---|
| Determinar âmbito do produto | **NÃO** | Rules Engine |
| Listar artigos aplicáveis | **NÃO** | Rules Engine |
| Verificar obrigações | **NÃO** | Rules Engine |
| Apontar gaps | **NÃO** | Rules Engine |
| Sugerir texto de relatório | SIM | `provenance: ai`, confidence, revisão humana |
| Sumarizar evidência carregada | SIM | `provenance: ai`, confidence < 0.8 = revisão obrigatória |
| Classificar tipo de ficheiro | SIM (preliminar) | validado de raiz pelo `vault.validateSafety` (magic bytes) |
| Traduzir conteúdo | SIM | output sanitizado, marcado |

## 5. Proveniência e incerteza (contrato)

Todo output da IA carrega:
- `provenance: "ai-assistant"`;
- `confidence: 0.0–1.0`;
- `traceId` que o originou;
- `grounding: EvidenceRef[]` (quais evidências a IA consultou).

Todo output do Rules Engine carrega:
- `provenance: "rules-engine"`;
- `rulePackage: { version, sha256 }`;
- `sources: SourceRef[]` (citações a Issue #3).

## 6. Comportamento quando a IA está indisponível

- **Modo degrade total**: a aplicação funciona 100% sem IA. Nenhuma funcionalidade
  determinística depende de IA.
- UI desativa blocos de "sugestão de IA"; o utilizador preenche manualmente.
- Nenhum output da IA é considerado "perdido": se um chunk de IA estiver em rascunho
  não submetido, é só UI state (não regulamentar).

## 7. Separar factos de interpretações (ligado ao Issue #3/#4)

O Rules Engine consome exclusivamente **factos** e **tabelas de decisão** validados pelo
Regulatory Research Engineer (#3) e pelo Requirements Traceability Engineer (#4).
Interpretações, recomendações e pontos em aberto permanecem em documentos auxiliares
(`docs/regulatory/`) e são **referenciados** pelo Rule Package, nunca absorvidos como
decisão automática.

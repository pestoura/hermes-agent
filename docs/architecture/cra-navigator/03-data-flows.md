# 03 — Fluxos de Dados & Fronteiras de Confiança

Fonte de dados: [`diagrams/03-data-flow-trust-boundaries.drawio`](diagrams/03-data-flow-trust-boundaries.drawio).

## 1. Zonas de confiança (revisão)

| Zona | Componente | Classificação de input | Nota |
|---|---|---|---|
| C | UI Renderer + frontend-sanitizer | **Untrusted** (utilizador, IA, ficheiros) | tudo entra aqui primeiro |
| A | Domain Engine + Rules Engine | **Trusted** (após sanitização) | fonte de verdade regulamentar |
| B | Local Store + Evidence Vault | **Protected at rest** | cifrado; chave do OS |
| D | Update Service + AI Assistant | **Untrusted/optional** | integridade verificada ou provenimento auditado |

A fronteira C→A é a **crítica**: nenhum byte do utilizador ou da IA atinge a Zona A sem
passar por `frontend-sanitizer.validateSchema` e re-validação no Domain Engine.

## 2. Fluxos numerados

### Fluxo 1 — Input bruto do utilizador → UI (untrusted)
- Fonte: SME / fabricante.
- Tipo: texto livre, upload de ficheiro, interação.
- Risco: XSS, path traversal via nome, template injection, MIME spoofing.
- Controlo: `frontend-sanitizer` aplica escaping, validação de MIME por magic bytes,
  limite de tamanho. Veja `08-evidence-ingestion.md` e `15-threat-model.md`.

### Fluxo 2 — Dados sanitizados UI → Domain (C → A)
- Tipo: objetos JSON schema-validados.
- Controlo: schema versionado (`contracts/00-common-types.yaml`); a Zona A **revalida**
  o schema (defense in depth). IPC usa Serialização estruturada (não eval).
- Proveniência: cada mensagem carrega `traceId` e `provenance.source = "user|ai"`.
- Garantia: nenhuma string do utilizador chega ao Rules Engine sem serialização
  determinística.

### Fluxo 3 — Domínio → Rules Engine (A interna)
- Tipo: chamada síncrona (in-process).
- Controlo: pureza imposta — o Rules Engine não faz I/O, não tem efeitos laterais.
- Garantia de determinismo: saída idêntica para mesmo input (testada com seeds fixas).
- Proveniência: o `ScopeDecision` carrega referências a articles + evidence_refs.

### Fluxo 4 — Rules Engine → Rule Package (leitura confiável)
- Tipo: leitura de package versionado, assinado.
- Controlo: verificação de hash + assinatura antes de carregar (ADR-006).
- Package atualiza-se via mesmo mecanismo de atualização (Fluxo 8), nunca pelo utilizador.

### Fluxo 5a — Domain → Local Store (persistência estruturada)
- Tipo: escrita SQLCipher com schema versionado.
- Controlo: migração automática na abertura (veja `04-persistence-and-data-lifecycle.md`).
- Cifra: chave derivada do OS keychain (Windows DPAPI), nunca persistida em texto.

### Fluxo 5b — Domain → Evidence Vault (ficheiros binários)
- Tipo: escrita sandboxed via Domain Engine.
- Controlo:
  - Nome sanitizado a leaf apenas (`Vault.ingest`).
  - Content-addressing SHA-256; path traversal proibido.
  - Magic-bytes verificados (ADR-009).
  - Extensão/MIME forçados e alinhados com o policy.
- Proveniência: `EvidenceRecord.file_name_hash` preserva o nome original apenas como
  metadado não-executável.

### Fluxo 6 — Domain → Report Generator
- Tipo: síncrono; template estático + dados do store.
- Controlo: o AI Assistant **nunca** escreve diretamente no Report Generator. Texto de IA,
  se incluído, passa pelo `frontend-sanitizer` e é marcado `provenance: ai` no report.
- Garantia: o relatório carrega `inputs_digest` (hash imutável dos inputs).

### Fluxo 7 — AI Assistant → UI (untrusted/optional)
- Tipo: assíncrono via local LLM.
- Controlo: output sempre marcado `provenance: ai-assistant`, `confidence`.
- Nível de confiança: **0.0–1.0**; < 0.8 exige confirmação humana.
- Proveniência: cada chunk de output referencia o `traceId` que originou.

### Fluxo 8 — Update Service → Domain (externo, signed)
- Tipo: verificação de release no GitHub Releases.
- Controlo: assinatura verificada antes de download; payload em temp dir; verificação de
  integridade na aplicação.
- Garantia: sem verificação de assinatura, update é rejeitado.

## 3. Diagrama de fronteira (resumo textual)

```
        SME                AI(optional)        Update Service
         |                    |                    |
         v                    v                    v
   [ UI Renderer ]  <----  [ AI output (sanitized) ]
         |  (validação de schema + revalidação)
         |  TRUST BOUNDARY C -> A  (frontend-sanitizer)
         v
   [ Domain Engine ]
         |  (pure call)
         v
   [ Rules Engine ]  <--[read]-- [ Rule Package (trusted, signed) ]
         |
         |----(metadata)----> [ Local Store (SQLCipher) ]
         |----(evidence)----> [ Evidence Vault (sandbox) ]
         |
         v
   [ Report Generator ]  --(export)--> SME / Regulated body (future)
```

## 4. Inovação vs segurança

Nenhum fluxo do utilizador ou da IA pode:
- executar código (sem eval/exec);
- escrever fora do vault;
- alterar o rule package;
- decidir sobre âmbito/obrigações (isso é exclusividade do Rules Engine).

Estas restrições são verificáveis por testes de contrato (contract tests) — veja
`18-implementation-sequence.md`.

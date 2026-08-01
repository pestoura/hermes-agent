# 01 — System Context & C4 Overview

## 1. Propósito

Estabelece o contexto do sistema (C4 Nível 1) e a decomposição em contentores (C4 Nível 2)
do **BlitzHub CRA Navigator**, identificando as fronteiras de confiança (trust boundaries)
que se aplicam à arquitetura local-first do MVP.

Ver também o diagrama versionável: [`diagrams/01-c4-context.drawio`](diagrams/01-c4-context.drawio)
e a sua exportação `.svg`.

## 2. Atores e sistemas externos (C4 Nível 1)

| Elemento | Tipo | Descrição | Confiança |
|---|---|---|---|
| **SME / fabricante** | Ator humano | Utilizador final da PME sem conhecimento de Docker. | Não confiável (conteúdo) |
| **BlitzHub CRA Navigator** | Sistema (local) | Aplicação desktop Windows que orienta a preparação para o CRA. | Sistema primário |
| **Regulatory Research source catalog** | Dados internos | Catálogo de fontes primárias (Issue #3): EUR-Lex, Comissão Europeia, ENISA, autoridades nacionais. | Fonte de regra (alta) |
| **Requirements & traceability schema** | Dados internos | Schema versionado de requisitos CRA (Issue #4). | Fonte de regra (alta) |
| **AI Assistant (local LLM)** | Assistente opcional | Resume, classifica e propõe — nunca decide. | Baixa (proveniância auditável) |
| **Update Service (GitHub Releases)** | Serviço externo | Verificação e download de atualizações assinadas. | Externo (integridade verificada) |
| **Regulated body / market surveillance** | Sistema externo (futuro) | Consumidor opcional de relatórios exportados. | Externo (futuro) |

> **Princípio**: no MVP, a aplicação **não** envia dados para o exterior. O "Regulated body"
> é um limite de integração futura (veja `13-future-integration-boundaries.md`), mantido
> fora do contentor de confiança da aplicação.

## 3. Contentores do MVP (C4 Nível 2)

Dentro do contentor da aplicação desktop Windows:

1. **Application Shell** — processo principal Electron. Gestão de janelas, gate de IPC,
   ciclo de vida, atualizações. É o **guardião do privilégio** entre o OS e os restantes
   contentores. Não contém lógica de domínio.
2. **UI Renderer** — processo Chromium isolado. Renderiza a interface React e comunica-se
   com o domínio exclusivamente via IPC. **Fronteira de confiança**: todo conteúdo
   proveniente do utilizador ou de IA é renderizado neste contentor com sanitização.
3. **Domain Engine** — serviço Node (IPC). Orquestra casos de uso, validações de domínio
   e delegação para o Rules Engine. É a camada de orquestração da lógica de negócio.
4. **Rules Engine** — **fonte de verdade regulamentar**. Contém apenas regras determinísticas
   derivadas do catálogo validado (Issues #3/#4). Não consome IA.
5. **Local Store** — armazenamento estruturado local (SQLCipher) com schema versionado,
   cifra em repouso e migrações.
6. **Evidence Vault** — sistema de ficheiros sandboxed para evidências carregadas, com
   sanitização de caminos e content-addressing.
7. **Report Generator** — produz relatórios Markdown/PDF deterministicamente a partir do
   store e do vault. Não aceita inputs de IA diretamente.

## 4. Fronteiras de confiança (trust boundaries)

```
[Utilizador / IA]  --(entrada não confiável)-->  [UI Renderer | frontend-sanitizer]
                                                       | IPC (validado, schema)
                                                       v
                                          [Domain Engine | input-validator]
                                                       |
                          +-------------------+-------------------+-------------------+
                          v                   v                   v                   v
                  [Rules Engine]      [Local Store]      [Evidence Vault]      [Report Generator]
                  (determinístico)      (cifrado)         (sandboxed)            (determinístico)
                          ^                   ^                   ^                   ^
                          |                   |                   |                   |
                  [trusted rules pkg]    [at-rest crypto]    [sanitized upload]   [static generation]
                          |                   |                   |                   |
                          +-------------------+-------------------+-------------------+
                                                       |
                                                       v
                                          [Application Shell | OS boundary]
                                                       |
                                                       v
                              [Windows OS (privilegio limitado, sandbox)]
                                                       ^
                          [Update Service]  --(signed release)-->
                          [Regulated body]  --(export, futuro)-->
```

### 4.1 Zonas de confiança

- **Zona A — Trusted core (Domain Engine + Rules Engine)**: contém a lógica determinística.
  Acesso restrito a content-addressing e a validação de schema. Não processa ficheiros
  do utilizador sem passar pelo validator.
- **Zona B — Storage (Local Store + Evidence Vault)**: cifrado em repouso; a chave de
  utilização não é armazenada no processo Node (veja `11-configuration-and-secrets.md`).
- **Zona C — Untrusted input (UI Renderer)**: tudo o que o utilizador ou a IA produzem
  entra aqui e é sanitizado antes de atingir a Zona A.
- **Zona D — External boundary (Shell + OS + Update Service)**: o Shell é o único contentor
  com acesso direto ao OS para atualizações e I/O de ficheiros; delega operações de
  ficheiro ao Evidence Vault com caminos sanitizados.

## 5. Princípio de separação determinístico-vs-IA

Ver detalhe em `07-deterministic-vs-ai.md`. Resumo aqui:

- **Determinístico (fonte de verdade)**: âmbito, obrigações, critérios de aceitação,
  geração de relatório. Alimentado exclusivamente pelo Rules Engine.
- **AI-assisted (nunca autoritativo)**: sugestões de texto, classificação preliminar de
  evidências, sumários. Requer confirmação humana e é sempre marcado com proveniância
  e nível de confiança.

## 6. Não-cobertura desta baseline

- Implementação do Domain Engine / Rules Engine (vaga 2).
- Decisão final de framework de embalagem (veja ADR-004, reversível).
- Normas pagas ou conteúdo sem redistribuição.

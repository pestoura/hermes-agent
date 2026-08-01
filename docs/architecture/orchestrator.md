# BlitzHub CRA Product Orchestrator

## Função

O orquestrador é o plano de controlo do projeto. Mantém o estado coerente entre GitHub, Kanban Hermes, agentes técnicos e resultados de supervisão do ChatGPT.

## Responsabilidades

- ler Issues, Pull Requests, comentários, commits e checks;
- normalizar o estado do projeto;
- reconciliar GitHub e Kanban;
- verificar dependências e critérios de entrada;
- respeitar o estado das vagas de agentes;
- selecionar trabalho pronto;
- atribuir trabalho ao agente adequado;
- aplicar transições de estado;
- evitar duplicação e conflitos;
- publicar relatórios de reconciliação.

## Separação de responsabilidades

O orquestrador não substitui agentes especializados. Não deve interpretar profundamente legislação, rever código, criar design ou gerar ativos visuais. Essas decisões são produzidas por agentes e pelo ChatGPT Supervisor; o orquestrador valida a estrutura e materializa o workflow.

## Fluxo

```text
GitHub
  ↓
Normalização de eventos e estado
  ↓
Validação de políticas, vagas e dependências
  ↓
Reconciliação com Kanban Hermes
  ↓
Dispatch para agentes ativos
  ↓
Pull Request e checks
  ↓
Supervisão ChatGPT
  ↓
Merge, rework ou novo trabalho
```

## Princípios

- GitHub é canónico.
- O Kanban é uma vista operacional.
- Não existe trabalho relevante sem Issue GitHub.
- Alterações passam por Pull Request.
- Ações devem ser idempotentes.
- Operações destrutivas são proibidas no bootstrap.
- Findings `REQUIRED` do ChatGPT têm prioridade sobre novo desenvolvimento.

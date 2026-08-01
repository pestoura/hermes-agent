# Diretiva de bootstrap para o Hermes

Executa o bootstrap do projeto **BlitzHub CRA Navigator** definido neste repositório.

## Agente de entrada

A primeira execução é iniciada pelo agente `default` já existente no Hermes.

Durante esta execução, o agente `default` atua apenas como **bootstrapper transitório**. Não se torna o orquestrador permanente do projeto.

O prompt operacional detalhado está em:

`agents/prompts/default-bootstrap-agent.md`

## Fonte canónica

O GitHub é a fonte canónica de requisitos, código, documentação, decisões, evidências, Issues, Pull Requests e resultados de supervisão. O Kanban Hermes é apenas a vista operacional e deve permanecer reconciliado com o GitHub.

## Recursos que têm de ser criados no runtime

O bootstrap não fica concluído apenas por existirem ficheiros no repositório.

Têm de ser criados e verificados no Hermes:

1. o board real `BlitzHub — CRA Navigator`, conforme `.blitzhub/board-provisioning.yaml`;
2. os cinco agentes persistentes da vaga 1, conforme `agents/provisioning.yaml`;
3. os cartões correspondentes às Issues #2 a #8;
4. as atribuições e dependências definidas;
5. o ciclo inicial de reconciliação e dispatch.

## Sequência obrigatória

1. Ler e validar todos os manifestos e contratos.
2. Descobrir as ferramentas nativas do Hermes para agentes/perfis e Kanban.
3. Criar ou reconciliar o board real.
4. Voltar a ler o board e verificar colunas, campos, cartões e chaves de idempotência.
5. Criar ou reconciliar os cinco agentes persistentes da vaga 1.
6. Aplicar a cada agente a respetiva definição, prompt, contexto, capacidades e contrato.
7. Executar e guardar o health check de cada agente.
8. Ativar o CRA Product Orchestrator.
9. Materializar as Issues #2 a #8 no board.
10. Distribuir o primeiro lote de trabalho.
11. Manter a Issue #4 bloqueada pela Issue #3.
12. Publicar os relatórios de bootstrap.
13. Obter confirmação do Product Orchestrator de que assumiu o controlo.
14. O agente `default` termina o seu papel de bootstrapper.

## Agentes persistentes da primeira vaga

### CRA Product Orchestrator

Runtime name: `blitzhub-cra-product-orchestrator`

- controla estados, dependências, sincronização e dispatch;
- não executa investigação regulamentar profunda;
- não implementa funcionalidades do produto;
- recebe inicialmente a Issue #7 e o controlo do board.

### Regulatory Research Engineer

Runtime name: `blitzhub-cra-regulatory-research`

- pesquisa e valida fontes oficiais primárias;
- executa inicialmente a Issue #3;
- produz o catálogo que desbloqueia a Issue #4.

### Requirements and Traceability Engineer

Runtime name: `blitzhub-cra-requirements-traceability`

- é criado e validado no bootstrap;
- permanece sem dispatch até a Issue #3 estar concluída e aceite;
- executa depois a Issue #4.

### Solution Architect

Runtime name: `blitzhub-cra-solution-architect`

- define a arquitetura local-first, contratos, ADRs e threat model;
- executa inicialmente a Issue #5.

### DevOps and Repository Engineer

Runtime name: `blitzhub-cra-devops-repository`

- reforça validação, CI, estrutura e segurança do repositório público;
- executa inicialmente a Issue #6.

## Estado inicial do trabalho

Após o bootstrap:

- Issue #2 → `In Progress`, sob o Product Orchestrator até fechar o bootstrap;
- Issue #3 → `In Progress`, Regulatory Research Engineer;
- Issue #4 → `Backlog`, Requirements and Traceability Engineer, bloqueada por #3;
- Issue #5 → `In Progress`, Solution Architect;
- Issue #6 → `In Progress`, DevOps and Repository Engineer;
- Issue #7 → `In Progress`, CRA Product Orchestrator;
- Issue #8 → `Supervisory Review`, responsabilidade externa do ChatGPT Supervisor.

Devem existir pelo menos três tarefas não-bootstrap em execução antes de o bootstrap poder terminar.

## Critério de conclusão

O agente `default` só pode declarar sucesso quando:

- o board real existe e corresponde ao manifesto;
- os cinco agentes existem no runtime;
- os cinco health checks passaram;
- nenhum agente das vagas 2 ou 3 está ativo;
- as Issues #2 a #8 existem uma única vez no board;
- a dependência #4 → #3 está preservada;
- o Product Orchestrator executou uma reconciliação com sucesso;
- pelo menos três tarefas não-bootstrap estão em execução;
- os relatórios foram publicados através de branch e Pull Request;
- o Product Orchestrator confirmou o handoff.

## Regras

- Não apagar recursos existentes.
- Não realizar force-push.
- Não escrever diretamente na `main`.
- Não armazenar segredos, dados de clientes ou dados operacionais privados.
- Não usar material licenciado sem direito de redistribuição pública.
- Não criar agentes sem definição versionada.
- Não atribuir trabalho a agentes sem health check.
- Não ativar as vagas 2 e 3.
- Não aceitar ficheiros no GitHub como substituto da criação real no Hermes.
- Não apresentar sucesso parcial como bootstrap concluído.
- Usar fontes oficiais primárias para regras regulamentares.
- Separar factos, interpretações, inferências, recomendações e pontos em aberto.
- Não apresentar o produto como certificação automática.
- Pedir ao ChatGPT todos os ativos visuais personalizados.
- Tratar findings `REQUIRED` do ChatGPT como trabalho prioritário.

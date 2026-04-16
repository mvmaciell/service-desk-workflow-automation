# SDWA — Service Desk Workflow Automation

## Contexto do projeto (atualizado 2026-04-15)

Sistema de automacao de fila do MegaHub (ITSM da Megawork).
Monitora filas via headless browser (Playwright), detecta chamados novos/finalizados/retornados,
sugere alocacao inteligente e notifica via Microsoft Teams.

## Acesso real validado

- URL da fila: `https://megahub.megawork.com/Chamado/Index`
- Tipo: fila geral (`kind = "fila"`)
- Source configurada: `fila-geral` em `config/local/contexts.toml`
- Sessao do browser persistida em `data/browser-profile/megawork`
- Paginacao implementada e funcional (captura todas as paginas)
- Snapshot testado: 1803 chamados capturados com sucesso em CSV

## Snapshot da fila (2026-04-15)

### Numeros-chave
- Total: 1803 chamados (incluindo atribuidos)
- Novos: 133 (58 sem consultor)
- Status mais comum: Acao do cliente (504), Em Homologacao (325), Em Processamento (189)
- Urgentes/Imediatos abertos: 67
- Chamados com 90+ dias: 428 (24% da fila)

### Frentes ativas (25+)
AMS ABAP, AMS FI, AMS HR, AMS MM, AMS GRC AC, AMS SAP Business One,
AMS SD, AMS PM, AMS PS, AMS CO, AMS QM, AMS EWM, AMS CCS FI/CA,
AMS CCS DM, AMS CCS BILLING, AMS SOLMAN, AMS BASIS, BASIS,
CSG HR, CSG MM, CSG ABAP, CSG SD, CSG FI, CSG PS, CSG PM,
MULTIPLATAFORMA, INTEGRATION & DF-e, PORTAL, INFRA, MEGALABS - IA,
Inf. Gerenciais - BI, PRE-VENDA, Alocacao, Implantation, MEGADUTY, ABAP

### Status reais encontrados (20)
Novo, Em Processamento, Em Estimativa, Acao do cliente, Em Homologacao,
Aguardando Aprovacao, Processamento Interno, Solucao Proposta, Em Execucao,
Programado, Agendado, Aguardando Programacao, Homologado, Aguardando Estimativa,
Encaminhado a Terceiro, Transporte de Request, Nao Homologado, Atribuido, Revisao

### Empresas (top 5)
CEMIG (249), MEGAWORK (170), ELETRONUCLEAR (132), MPES (118), GASMIG (116)

## Plano de evolucao — Fluxo do Coordenador

### P0 — Corrigir o que esta quebrado (pre-requisito pra ligar allocation)
- [x] P0.1 — Mapear frentes reais como skills no teams.toml (11 devs placeholder por frente)
- [x] P0.2 — Corrigir return_to_developer_labels → ["Nao Homologado", "Revisao"]
- [x] P0.3 — max_new_tickets_per_cycle=10 (limita sugestoes por ciclo)
- [x] P0.4 — managed_fronts no coordenador (filtra frentes que gerencia)

### P1 — Melhorar experiencia do coordenador
- [x] P1.1 — Card consolidado (send_batch_allocation_suggestion) em vez de N individuais
- [x] P1.2 — Priorizacao: Imediata > Urgente > Normal > Baixa + cores no card
- [x] P1.3 — Timeout de aprovacao com lembrete
- [x] P1.4 — Garantir notificacao ao dev apos aprovacao (webhook do dev)

### P2 — Robustez operacional
- [x] P2.1 — Reconciliacao de carga (consultant do MegaHub vs alocacao interna)
- [x] P2.2 — Dashboard/CLI do coordenador com visao consolidada
- [x] P2.3 — Bulk approve

### P3 — Evolucao futura
- [ ] P3.1 — Aprovacao via botoes no Teams (Power Automate callback)
- [ ] P3.2 — Dashboard web

## Regras tecnicas

- Hexagonal architecture: ports/ (interfaces) + adapters/ (implementacoes)
- Testes: pytest, cobertura >= 65%, CI via GitHub Actions
- Config: TOML (contexts, profiles, teams) + .env
- Dominio: domain/models.py, domain/enums.py
- Persistencia: SQLite em data/megahub-monitor.db

# SDWA — Service Desk Workflow Automation

Monitor local de chamados do MegaHub com automação de alocação de desenvolvedores e notificação via Microsoft Teams.

## O que faz

- Coleta chamados do MegaHub via browser headless (Playwright)
- Detecta novos chamados (incluindo os que já estavam com status NOVO na primeira execução)
- Sugere os melhores desenvolvedores com base em habilidades, carga atual e histórico
- Notifica o coordenador no Teams com o ranking de sugestões e o quadro de carga
- Permite que o coordenador aprove a alocação via linha de comando
- Notifica o desenvolvedor atribuído no Teams
- Detecta conclusão de chamados e notifica o coordenador
- Mantém trilha de auditoria completa de todas as ações

## Ciclo de workflow

```
Novo chamado detectado
       ↓
Sugestão de alocação gerada (ranking: habilidade > carga > histórico > alfabético)
       ↓
Coordenador recebe card no Teams com sugestões e quadro de carga
       ↓
Coordenador aprova: python main.py approve --ticket X --member Y
       ↓
Desenvolvedor recebe card de atribuição no Teams
       ↓
Chamado concluído → coordenador recebe notificação de conclusão
```

## Pré-requisitos

- Python 3.11+
- Acesso ao MegaHub com sessão de navegador configurada
- Webhooks no Microsoft Teams via Power Automate (opcional para modo legado)

## Instalação

```powershell
# Instalar dependências Python
pip install -e .

# Instalar navegadores do Playwright
playwright install chromium

# Copiar configurações de exemplo
cp config/example/contexts.toml config/local/contexts.toml
cp config/example/profiles.toml config/local/profiles.toml
```

## Configuração

### Arquivos de configuração

| Arquivo | Descrição |
|---|---|
| `.env` | Variáveis de ambiente (caminhos, flags, timeouts) |
| `config/local/contexts.toml` | Sessões de browser por usuário/sistema |
| `config/local/profiles.toml` | Fontes de dados e subscrições de notificação |
| `config/teams.toml` | Catálogo de equipe e configurações de alocação |

### Exemplo `config/teams.toml`

```toml
[[members]]
id = "dev-marcus"
name = "Marcus Vinicius"
role = "developer"
skills = ["abap", "fiori"]
active = true
webhook_url = ""        # URL Teams do desenvolvedor (opcional)
max_concurrent_tickets = 5

[[members]]
id = "coord-joao"
name = "Joao Silva"
role = "coordinator"
skills = []
active = true
webhook_url = "https://prod.outlook.com/webhooks/..."  # obrigatório para receber sugestões

[allocation]
enabled = true
max_suggestions = 3
novo_status_labels = ["NOVO"]
completion_status_labels = ["Fechado", "Resolvido", "Cancelado"]
```

### Variável `.env` para ativar alocação

```ini
ALLOCATION_ENABLED=true
```

## Primeiro uso

```bash
# 1. Fazer login no MegaHub (salva sessão do browser)
python main.py login --source minha_fila

# 2. Verificar coleta
python main.py snapshot --source minha_fila

# 3. Executar ciclo completo
python main.py run-once
```

## Comandos

| Comando | Descrição |
|---|---|
| `python main.py run-once` | Executa um ciclo de detecção e notificação (usar no agendador) |
| `python main.py monitor` | Loop contínuo de monitoramento |
| `python main.py login [--source S]` | Abre browser para login manual |
| `python main.py snapshot [--source S]` | Captura e imprime resumo dos chamados |
| `python main.py approve --ticket X --member Y` | Registra aprovação de alocação e notifica desenvolvedor |
| `python main.py audit-trail [--ticket X] [--limit N]` | Exibe trilha de auditoria |
| `python main.py notify-test [--profile P]` | Envia card de teste para perfis configurados |
| `python main.py forget-ticket N [--source S]` | Remove chamado da base para reprocessamento |

## Agendador do Windows

```powershell
# Registrar tarefa agendada (executa run-once a cada 2 minutos)
powershell -File scripts\register-task.ps1 -IntervalMinutes 2

# Verificar status
powershell -File scripts\check-status.ps1
```

## Arquitetura

O projeto segue arquitetura hexagonal (ports/adapters):

```
domain/          → modelos e regras de negócio (sem dependências externas)
ports/           → interfaces abstratas (ITSMReader, Notifier, StateRepository, TeamCatalog)
application/     → casos de uso e serviços de aplicação
adapters/        → implementações concretas (MegaHub, SQLite, Teams, TOML)
infrastructure/  → configuração, logging, clock
```

Os módulos legados (`browser/`, `collectors/`, `services/`, `repository/`) são shims de re-export
que apontam para os novos caminhos em `adapters/`.

## Banco de dados

SQLite local em `data/monitor.db`. Todas as migrações são incrementais e idempotentes:

- `source_states` — estado de baseline por fonte
- `source_seen_tickets` — deduplicação de chamados
- `source_snapshots` — histórico de capturas
- `load_snapshots` — histórico de carga
- `notification_deliveries` — registro de entregas (modo legado)
- `workflow_items` — estado do workflow por chamado
- `audit_events` — trilha de auditoria imutável
- `pending_approvals` — aprovações pendentes de coordenação

## Limitações v1

- Coleta apenas a primeira página de cada fila
- Aprovação somente via CLI (card Teams é informativo; Action.Submit é evolução futura)
- Matching de carga por nome do consultor (case-insensitive) — pode divergir se nomes diferirem entre fontes
- Sem atribuição automática no ITSM (apenas notificação)
- Sem suporte a múltiplas páginas de fila

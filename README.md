# MegaHub Queue Monitor

Motor local de monitoramento para o MegaHub com suporte a:

- multiplas fontes (`Minha Fila` e `Fila`)
- multiplos destinatarios
- regras de roteamento por perfil
- notificacao no Teams via Power Automate
- baseline por fonte
- execucao `run-once` para Agendador do Windows

## Escopo atual

- `Minha Fila` operacional e validada
- `Fila` preparada no codigo, mas desabilitada ate a liberacao de acesso
- primeira pagina apenas
- carga atual por consultor calculada a partir da snapshot da fonte

## Stack

- Python 3.11+
- Playwright
- SQLite
- requests
- python-dotenv

## Estrutura

- `main.py`: entrada da CLI
- `config/contexts.toml`: contextos autenticados e fontes
- `config/routing.toml`: destinatarios e regras
- `src/megahub_monitor/browser/`: sessoes persistentes do navegador
- `src/megahub_monitor/collectors/`: coleta da grade por fonte
- `src/megahub_monitor/notifiers/`: envio de cards para o Teams
- `src/megahub_monitor/repository/`: persistencia local
- `src/megahub_monitor/services/`: detecao, roteamento, carga e execucao
- `data/`: banco, logs, lock e perfis de navegador

## Instalacao

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install
Copy-Item .env.example .env
```

Preencha no `.env`:

- `TEAMS_WEBHOOK_URL`
- opcionalmente caminhos de banco/log/configs

## Configuracao

### `.env`

- `MONITOR_INTERVAL_SECONDS`: intervalo do loop continuo
- `LOCK_FILE_PATH`: lock do `run-once`
- `BROWSER_HEADLESS`: `true` ou `false`
- `PLAYWRIGHT_CHANNEL`: `msedge` por padrao
- `DATABASE_PATH`
- `LOG_FILE_PATH`
- `CONTEXTS_CONFIG_PATH`
- `ROUTING_CONFIG_PATH`
- `TEAMS_WEBHOOK_URL`

### `config/contexts.toml`

Define contextos autenticados e fontes monitoradas.

Exemplo atual:

- `marcus-session`: contexto ativo usando `data/browser-profile`
- `gestor-session`: contexto preparado para a conta gerencial
- `minha_fila_marcus`: fonte ativa
- `fila_gerencial`: fonte preparada e desabilitada

### `config/routing.toml`

Define destinatarios e regras de roteamento.

Exemplo atual:

- `marcus`: recebe alertas da `Minha Fila`
- `augusto`: preparado para receber alertas da `Fila`
- ambos usam o mesmo webhook nesta fase

## Comandos

### Login manual

```powershell
python main.py login
python main.py login --source minha_fila_marcus
python main.py login --context gestor-session
```

### Teste de notificacao

```powershell
python main.py notify-test
python main.py notify-test --recipient marcus
```

### Snapshot de uma fonte

```powershell
python main.py snapshot --source minha_fila_marcus
```

### Execucao unica

```powershell
python main.py run-once
```

Comportamento:

- percorre todas as fontes habilitadas
- cria baseline inicial por fonte sem notificar
- detecta novos chamados nas execucoes seguintes
- roteia alertas conforme `routing.toml`

### Loop continuo

```powershell
python main.py monitor
```

### Forcar reprocessamento em demo

```powershell
python main.py forget-ticket 41487 --source minha_fila_marcus
python main.py run-once
```

## Agendador do Windows

Forma recomendada para background:

1. registrar a tarefa com o script abaixo
2. manter intervalo de `2 minutos`
3. o script cria uma tarefa para executar `run-once` com lockfile

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register-task.ps1
```

Parametros opcionais:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register-task.ps1 -TaskName "MegaHub Queue Monitor" -IntervalMinutes 2
```

Se preferir criar manualmente, o comando alvo e:

```powershell
C:\Users\mvmac\OneDrive\Documentos\New project\.venv\Scripts\python.exe C:\Users\mvmac\OneDrive\Documentos\New project\main.py run-once
```

O lockfile evita execucao concorrente se uma rodada ainda estiver em andamento.

## Persistencia local

Banco SQLite em `data/megahub-monitor.db`:

- `source_states`: baseline e ultimo sucesso por fonte
- `source_seen_tickets`: chamados vistos por fonte
- `source_snapshots`: snapshots completos por fonte
- `load_snapshots`: carga atual por consultor
- `notification_deliveries`: entregas por regra/destinatario

## Validacao realizada

Validado localmente nesta fase:

- `notify-test` com Adaptive Card
- `snapshot` da fonte `minha_fila_marcus`
- `run-once` com baseline por fonte
- alerta segmentado do consultor com ticket forzado

## Limitacoes

- primeira pagina apenas
- depende do HTML/DOM atual do MegaHub
- a fonte `Fila` ainda nao foi validada porque o acesso nao esta liberado
- o mesmo webhook esta sendo usado por mais de um perfil nesta fase
- ainda nao existe dashboard nem distribuicao automatica

## Proximos passos

- habilitar e validar a fonte `fila_gerencial`
- confirmar filtros reais da tela `Fila`
- validar carga por consultor com dados gerenciais reais
- separar webhooks por perfil/canal
- evoluir para multiplas filas e paginacao completa

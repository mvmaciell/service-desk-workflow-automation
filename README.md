# MegaHub Queue Monitor

Motor local de monitoramento para o MegaHub com suporte a:

- multiplas fontes (`Minha Fila` e `Fila`)
- perfis de notificacao configuraveis por instalacao
- subscricoes com filtros por fonte, tipo, prioridade, empresa e consultor
- notificacao no Teams via Power Automate
- baseline por fonte
- execucao `run-once` para Agendador do Windows

## Escopo atual

- `Minha Fila` operacional e validada
- `Fila` preparada no codigo, mas pendente de validacao real quando houver acesso
- primeira pagina apenas
- carga atual por consultor calculada a partir da snapshot da fonte
- configuracao local por maquina via `config/local`

## Stack

- Python 3.11+
- Playwright
- SQLite
- requests
- python-dotenv

## Estrutura

- `main.py`: entrada da CLI
- `config/local/`: configuracao local gerada pelo instalador
- `config/contexts.toml`: fallback versionado para desenvolvimento
- `config/routing.toml`: fallback legado para desenvolvimento
- `scripts/install-monitor.ps1`: instalador interativo por maquina
- `scripts/install-augusto.ps1`: instalador pre-configurado para o Augusto
- `scripts/register-task.ps1`: registro da tarefa no Agendador do Windows
- `scripts/run-background.ps1`: wrapper silencioso para execucao em background
- `src/megahub_monitor/browser/`: sessoes persistentes do navegador
- `src/megahub_monitor/collectors/`: coleta da grade por fonte
- `src/megahub_monitor/notifiers/`: envio de cards para o Teams
- `src/megahub_monitor/repository/`: persistencia local
- `src/megahub_monitor/services/`: detecao, roteamento, carga e execucao
- `data/`: banco, logs, lock e perfis de navegador

## Modelo de configuracao

Cada instalacao da ferramenta passa a ter:

- `contexts`: sessoes autenticadas e fontes monitoradas naquela maquina
- `profiles`: pessoas ou canais que recebem notificacoes
- `subscriptions`: regras do que cada perfil recebe

Isso permite que cada usuario ou gestor tenha sua propria configuracao local sem hardcode de nomes no codigo.

## Instalacao recomendada

Use o instalador PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-monitor.ps1
```

O instalador:

- cria `.venv` se necessario
- instala dependencias
- instala os navegadores do Playwright
- cria `.env` se nao existir
- gera `config/local/contexts.toml`
- gera `config/local/profiles.toml`
- opcionalmente registra a tarefa automatica no Windows
- opcionalmente abre a tela de login no final

### Instalador pre-configurado do Augusto

Para a maquina do Augusto, existe um instalador pronto:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-augusto.ps1
```

Ou, de forma mais simples, basta executar:

```cmd
Instalar-Augusto.cmd
```

Depois da instalacao, o Augusto pode verificar rapidamente se esta tudo funcionando com:

```cmd
Verificar-Status-Augusto.cmd
```

Para validar o comportamento basico em modo visivel, ele pode executar:

```cmd
Iniciar-Validacao-Augusto.cmd
```

Fluxo desse instalador:

1. prepara o ambiente local
2. configura o perfil do Augusto e ativa a `Fila`
3. faz teste de notificacao no Teams
4. abre o login visivel para ele autenticar a conta
5. testa a leitura real da `Fila`
6. mantem `BROWSER_HEADLESS=false` para validacao basica
7. inicia automaticamente o monitor visivel ao final da instalacao

Observacao importante para o teste:

- a primeira rodada do monitor cria o baseline
- chamados que ja estavam na fila antes do monitor comecar nao serao notificados
- para validar o Teams, o ticket de teste precisa ser criado depois que o monitor estiver rodando

Se quiser forcar background depois da validacao, use:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-augusto.ps1 -EnableBackgroundAfterValidation
```

### O que o instalador pergunta

- nome do perfil principal
- papel do perfil principal (`consultor`, `coordenador`, `gestor`)
- webhook do Teams do perfil principal
- se deve adicionar um segundo perfil
- se deve ativar `Minha Fila`
- se deve ativar `Fila`
- nome do consultor para a fonte `Minha Fila`
- se deve registrar a tarefa automatica
- se deve abrir o login no final

### Limite atual do instalador

O instalador gera uma configuracao simples com **uma sessao principal**.

Se uma mesma maquina precisar monitorar `Minha Fila` e `Fila` com **contas diferentes**, o motor suporta isso, mas a configuracao avancada ainda precisa ser ajustada manualmente no `config/local/contexts.toml`.

## Configuracao local

### `.env`

- `MONITOR_INTERVAL_SECONDS`: intervalo do loop continuo
- `LOCK_FILE_PATH`: lock do `run-once`
- `BROWSER_HEADLESS`: `true` ou `false`
- `PLAYWRIGHT_CHANNEL`: `msedge` por padrao
- `PLAYWRIGHT_TIMEOUT_MS`
- `DATABASE_PATH`
- `LOG_FILE_PATH`
- `CONTEXTS_CONFIG_PATH`
- `PROFILES_CONFIG_PATH`
- `TEAMS_REQUEST_TIMEOUT_SECONDS`

### `config/local/contexts.toml`

Define:

- sessoes persistentes do navegador
- fontes habilitadas naquela instalacao

### `config/local/profiles.toml`

Define:

- `profiles`: quem recebe notificacao
- `subscriptions`: o que cada perfil recebe

Filtros suportados por subscricao:

- `ticket_types`
- `priorities`
- `companies`
- `consultants`

## Comandos

### Login manual

```powershell
python main.py login
python main.py login --source minha_fila_principal
python main.py login --context main-session
```

### Teste de notificacao

```powershell
python main.py notify-test
python main.py notify-test --profile marcus-vinicius-maciel-vieira
```

### Snapshot de uma fonte

```powershell
python main.py snapshot --source minha_fila_principal
```

### Execucao unica

```powershell
python main.py run-once
```

Comportamento:

- percorre todas as fontes habilitadas
- cria baseline inicial por fonte sem notificar
- detecta novos chamados nas execucoes seguintes
- roteia alertas conforme `profiles.toml`

### Loop continuo

```powershell
python main.py monitor
```

### Forcar reprocessamento em demo

```powershell
python main.py forget-ticket 41487 --source minha_fila_principal
python main.py run-once
```

## Agendador do Windows

Forma recomendada para background:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register-task.ps1
```

A tarefa chama `scripts/run-background.ps1`, que executa `run-once` sem abrir janela de console. Com `BROWSER_HEADLESS=true`, o navegador tambem nao fica visivel.

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
- `notification_deliveries`: entregas por subscricao/perfil

## Validacao realizada

Validado localmente nesta fase:

- `notify-test` com Adaptive Card
- `snapshot` da fonte ativa da `Minha Fila`
- `run-once` com baseline por fonte
- alerta segmentado do consultor com ticket forcado
- registro e execucao automatica via Agendador do Windows

## Limitacoes

- primeira pagina apenas
- depende do HTML/DOM atual do MegaHub
- a fonte `Fila` ainda nao foi validada porque o acesso real nao esta liberado
- o instalador ainda cobre o caso simples de uma sessao principal por maquina
- ainda nao existe dashboard nem distribuicao automatica

## Proximos passos

- validar a fonte `Fila` na maquina do gestor
- separar webhooks por perfil/canal quando necessario
- evoluir o instalador para mais de uma sessao autenticada por maquina
- adicionar suporte a paginacao completa
- preparar empacotamento distribuivel quando o formato operacional estabilizar

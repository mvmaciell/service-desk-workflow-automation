param(
    [switch]$Force,
    [switch]$SkipTeamsTest,
    [switch]$SkipLogin,
    [switch]$SkipQueueTest,
    [switch]$SkipTaskRegistration,
    [switch]$EnableBackgroundAfterValidation
)

$ErrorActionPreference = "Stop"

function Set-OrReplaceEnvValue {
    param(
        [string]$FilePath,
        [string]$Key,
        [string]$Value
    )

    $escapedKey = [Regex]::Escape($Key)
    $lines = @()
    if (Test-Path -LiteralPath $FilePath) {
        $lines = Get-Content -LiteralPath $FilePath
    }

    $matched = $false
    for ($index = 0; $index -lt $lines.Count; $index++) {
        if ($lines[$index] -match "^$escapedKey=") {
            $lines[$index] = "$Key=$Value"
            $matched = $true
        }
    }

    if (-not $matched) {
        $lines += "$Key=$Value"
    }

    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($FilePath, ($lines -join [Environment]::NewLine), $utf8NoBom)
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
$envPath = Join-Path $projectRoot ".env"
$installScript = Join-Path $projectRoot "scripts\install-monitor.ps1"
$registerTaskScript = Join-Path $projectRoot "scripts\register-task.ps1"
$visibleLauncher = Join-Path $projectRoot "Iniciar-Validacao-Augusto.cmd"
$visibleRunnerScript = Join-Path $projectRoot "scripts\run-visible-monitor.ps1"

Write-Host "Preparando instalacao direcionada para Augusto Bellucio Ker..." -ForegroundColor Cyan

& $installScript `
    -PrimaryName "Augusto Bellucio Ker" `
    -PrimaryRole "coordenador" `
    -PrimaryWebhookUrl "https://defaultba1a026c162c4efcb18f41d35c67f2.fb.environment.api.powerplatform.com:443/powerautomate/automations/direct/workflows/dd96edc5637a45c682b953d4add11d9c/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=RyNCu1IF6R2Hhxvel7svmqLqCQKxQDSr0dCG6Db2n88" `
    -EnableMinhaFila:$false `
    -EnableFila `
    -RegisterTask:$false `
    -OpenLogin:$false `
    -Force:$Force

Set-OrReplaceEnvValue -FilePath $envPath -Key "BROWSER_HEADLESS" -Value "false"

if (-not $SkipTeamsTest) {
    Write-Host "Executando teste de notificacao no Teams..." -ForegroundColor Cyan
    & $pythonExe (Join-Path $projectRoot "main.py") notify-test --profile augusto-bellucio-ker
}

if (-not $SkipLogin) {
    Write-Host "Abrindo login visivel para a conta do Augusto..." -ForegroundColor Cyan
    & $pythonExe (Join-Path $projectRoot "main.py") login --source fila_principal
}

if (-not $SkipQueueTest) {
    Write-Host "Executando teste de leitura da Fila..." -ForegroundColor Cyan
    & $pythonExe (Join-Path $projectRoot "main.py") snapshot --source fila_principal
}

if ($EnableBackgroundAfterValidation) {
    Write-Host "Ativando modo silencioso em background..." -ForegroundColor Cyan
    Set-OrReplaceEnvValue -FilePath $envPath -Key "BROWSER_HEADLESS" -Value "true"

    Write-Host "Validando execucao headless..." -ForegroundColor Cyan
    & $pythonExe (Join-Path $projectRoot "main.py") run-once

    if (-not $SkipTaskRegistration) {
        & $registerTaskScript -TaskName "MegaHub Queue Monitor - Augusto"
    }
} else {
    Write-Host "Modo de validacao basica mantido em tela visivel." -ForegroundColor Yellow
    Set-OrReplaceEnvValue -FilePath $envPath -Key "BROWSER_HEADLESS" -Value "false"

    $existingTask = Get-ScheduledTask -TaskName "MegaHub Queue Monitor - Augusto" -ErrorAction SilentlyContinue
    if ($existingTask) {
        Disable-ScheduledTask -TaskName "MegaHub Queue Monitor - Augusto" | Out-Null
        Write-Host "Tarefa em background desabilitada para evitar conflito com a validacao visivel." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Instalacao do Augusto concluida." -ForegroundColor Green
if ($EnableBackgroundAfterValidation) {
    Write-Host "A partir deste ponto, o monitor fica configurado para rodar em background a cada 2 minutos."
} else {
    Write-Host "O monitor visivel sera iniciado agora nesta mesma janela." -ForegroundColor Cyan
    Write-Host "Importante: a primeira leitura cria o baseline e nao notifica tickets que ja existiam na fila." -ForegroundColor Yellow
    Write-Host "Para validar o Teams, crie um chamado novo depois que o monitor estiver rodando." -ForegroundColor Yellow
    Write-Host ""
    & (Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0\powershell.exe") -NoProfile -ExecutionPolicy Bypass -File $visibleRunnerScript
}

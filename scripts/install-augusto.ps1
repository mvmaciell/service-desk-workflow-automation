param(
    [switch]$Force,
    [switch]$SkipTeamsTest,
    [switch]$SkipLogin,
    [switch]$SkipQueueTest,
    [switch]$SkipTaskRegistration
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

Write-Host "Ativando modo silencioso em background..." -ForegroundColor Cyan
Set-OrReplaceEnvValue -FilePath $envPath -Key "BROWSER_HEADLESS" -Value "true"

Write-Host "Validando execucao headless..." -ForegroundColor Cyan
& $pythonExe (Join-Path $projectRoot "main.py") run-once

if (-not $SkipTaskRegistration) {
    & $registerTaskScript -TaskName "MegaHub Queue Monitor - Augusto"
}

Write-Host ""
Write-Host "Instalacao do Augusto concluida." -ForegroundColor Green
Write-Host "A partir deste ponto, o monitor fica configurado para rodar em background a cada 2 minutos."

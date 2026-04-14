param(
    [string]$TaskName = "MegaHub Queue Monitor",
    [int]$LogTail = 8
)

$ErrorActionPreference = "Stop"

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "== $Title ==" -ForegroundColor Cyan
}

function Write-StatusLine {
    param(
        [string]$Label,
        [string]$Value,
        [string]$Level = "Info"
    )

    $color = switch ($Level) {
        "Ok" { "Green" }
        "Warn" { "Yellow" }
        "Error" { "Red" }
        default { "Gray" }
    }

    Write-Host ("{0,-22} {1}" -f "${Label}:", $Value) -ForegroundColor $color
}

function Format-TaskResult {
    param([int]$Code)

    switch ($Code) {
        0 { return "0 (OK)" }
        267009 { return "267009 (Em execucao ou ainda finalizando)" }
        267011 { return "267011 (Ainda nao executou)" }
        default { return "$Code (Verificar log)" }
    }
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $projectRoot ".env"
$contextsPath = Join-Path $projectRoot "config\local\contexts.toml"
$profilesPath = Join-Path $projectRoot "config\local\profiles.toml"
$logPath = Join-Path $projectRoot "data\logs\monitor.log"

Write-Host "MegaHub Monitor - Verificacao rapida" -ForegroundColor White
Write-Host "Projeto: $projectRoot" -ForegroundColor DarkGray

Write-Section "Arquivos"
Write-StatusLine -Label ".env" -Value ($(if (Test-Path -LiteralPath $envPath) { "Encontrado" } else { "Nao encontrado" })) -Level ($(if (Test-Path -LiteralPath $envPath) { "Ok" } else { "Error" }))
Write-StatusLine -Label "contexts.toml" -Value ($(if (Test-Path -LiteralPath $contextsPath) { "Encontrado" } else { "Nao encontrado" })) -Level ($(if (Test-Path -LiteralPath $contextsPath) { "Ok" } else { "Error" }))
Write-StatusLine -Label "profiles.toml" -Value ($(if (Test-Path -LiteralPath $profilesPath) { "Encontrado" } else { "Nao encontrado" })) -Level ($(if (Test-Path -LiteralPath $profilesPath) { "Ok" } else { "Error" }))

Write-Section "Agendador"
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
    Write-StatusLine -Label "Tarefa" -Value "Nao encontrada: $TaskName" -Level "Error"
} else {
    $taskInfo = $task | Get-ScheduledTaskInfo
    Write-StatusLine -Label "Tarefa" -Value $TaskName -Level "Ok"
    Write-StatusLine -Label "Ultima execucao" -Value ([string]$taskInfo.LastRunTime) -Level "Info"
    Write-StatusLine -Label "Proxima execucao" -Value ([string]$taskInfo.NextRunTime) -Level "Info"
    $taskLevel = if ($taskInfo.LastTaskResult -eq 0) { "Ok" } elseif ($taskInfo.LastTaskResult -eq 267011) { "Warn" } else { "Warn" }
    Write-StatusLine -Label "Resultado" -Value (Format-TaskResult -Code $taskInfo.LastTaskResult) -Level $taskLevel
}

Write-Section "Log"
if (-not (Test-Path -LiteralPath $logPath)) {
    Write-StatusLine -Label "monitor.log" -Value "Nao encontrado" -Level "Error"
} else {
    $logItem = Get-Item -LiteralPath $logPath
    $minutesAgo = [math]::Round(((Get-Date) - $logItem.LastWriteTime).TotalMinutes, 1)
    $logLevel = if ($minutesAgo -le 5) { "Ok" } elseif ($minutesAgo -le 15) { "Warn" } else { "Warn" }
    Write-StatusLine -Label "monitor.log" -Value "Atualizado ha $minutesAgo minuto(s)" -Level $logLevel
    Write-Host ""
    Write-Host "Ultimas linhas:" -ForegroundColor White
    Get-Content -LiteralPath $logPath -Tail $LogTail | ForEach-Object { Write-Host $_ }
}

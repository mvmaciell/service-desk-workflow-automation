param(
    [string]$TaskName = "MegaHub Queue Monitor",
    [int]$IntervalMinutes = 2
)

$ErrorActionPreference = "Stop"

if ($IntervalMinutes -lt 1) {
    throw "IntervalMinutes deve ser maior ou igual a 1."
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$powershellPath = Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0\powershell.exe"
$runnerPath = Join-Path $projectRoot "scripts\run-background.ps1"

if (-not (Test-Path -LiteralPath $powershellPath)) {
    throw "PowerShell nao encontrado em '$powershellPath'."
}

if (-not (Test-Path -LiteralPath $runnerPath)) {
    throw "Arquivo run-background.ps1 nao encontrado em '$runnerPath'."
}

$action = New-ScheduledTaskAction `
    -Execute $powershellPath `
    -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$runnerPath`"" `
    -WorkingDirectory $projectRoot

$trigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -StartWhenAvailable

$principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Limited

$task = New-ScheduledTask `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal

Register-ScheduledTask `
    -TaskName $TaskName `
    -InputObject $task `
    -Force | Out-Null

Write-Output "Tarefa '$TaskName' registrada com intervalo de $IntervalMinutes minuto(s)."

param(
    [string]$TaskName = "MegaHub Queue Monitor",
    [int]$IntervalMinutes = 2
)

$ErrorActionPreference = "Stop"

if ($IntervalMinutes -lt 1) {
    throw "IntervalMinutes deve ser maior ou igual a 1."
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$mainPath = Join-Path $projectRoot "main.py"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Python nao encontrado em '$pythonPath'."
}

if (-not (Test-Path -LiteralPath $mainPath)) {
    throw "Arquivo main.py nao encontrado em '$mainPath'."
}

$action = New-ScheduledTaskAction `
    -Execute $pythonPath `
    -Argument "`"$mainPath`" run-once" `
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

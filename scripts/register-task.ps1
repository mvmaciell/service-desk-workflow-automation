param(
    [string]$TaskName      = "SDWA Monitor",
    [int]$IntervalMinutes  = 2,
    [switch]$RegisterTray
)

$ErrorActionPreference = "Stop"

if ($IntervalMinutes -lt 1) {
    throw "IntervalMinutes deve ser maior ou igual a 1."
}

$projectRoot  = Split-Path -Parent $PSScriptRoot
$wscriptPath  = Join-Path $env:WINDIR "System32\wscript.exe"
$runnerVbs    = Join-Path $projectRoot "scripts\run-silent.vbs"
$trayVbs      = Join-Path $projectRoot "scripts\start-tray.vbs"

if (-not (Test-Path -LiteralPath $wscriptPath)) {
    throw "wscript.exe nao encontrado em '$wscriptPath'."
}

if (-not (Test-Path -LiteralPath $runnerVbs)) {
    throw "Arquivo run-silent.vbs nao encontrado em '$runnerVbs'. Execute a instalacao novamente."
}

# -----------------------------------------------------------------------
# Tarefa principal: run-once a cada N minutos
# Usa wscript.exe (subsystem GUI) -> sem flash de janela de console
# -----------------------------------------------------------------------
$action = New-ScheduledTaskAction `
    -Execute $wscriptPath `
    -Argument """$runnerVbs""" `
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

# -----------------------------------------------------------------------
# Tarefa do tray (opcional): inicia o icone da bandeja no logon
# -----------------------------------------------------------------------
if ($RegisterTray) {
    if (-not (Test-Path -LiteralPath $trayVbs)) {
        throw "Arquivo start-tray.vbs nao encontrado em '$trayVbs'."
    }

    $trayTaskName = "$TaskName (Tray)"

    $trayAction = New-ScheduledTaskAction `
        -Execute $wscriptPath `
        -Argument """$trayVbs""" `
        -WorkingDirectory $projectRoot

    $trayTrigger = New-ScheduledTaskTrigger -AtLogOn

    $traySettings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit (New-TimeSpan -Hours 24)

    $trayTask = New-ScheduledTask `
        -Action $trayAction `
        -Trigger $trayTrigger `
        -Settings $traySettings `
        -Principal $principal

    Register-ScheduledTask `
        -TaskName $trayTaskName `
        -InputObject $trayTask `
        -Force | Out-Null

    Write-Output "Tarefa '$trayTaskName' registrada para iniciar no logon."
}

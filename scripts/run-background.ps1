# AVISO: Este script e usado apenas para debug e execucao manual.
# Em producao, o Task Scheduler usa scripts\run-silent.vbs via wscript.exe
# (totalmente silencioso, sem flash de janela de console).
# Para re-registrar a tarefa: .\scripts\register-task.ps1

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonwPath = Join-Path $projectRoot ".venv\Scripts\pythonw.exe"
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$mainPath = Join-Path $projectRoot "main.py"

if (Test-Path -LiteralPath $pythonwPath) {
    $pythonExecutable = $pythonwPath
} elseif (Test-Path -LiteralPath $pythonPath) {
    $pythonExecutable = $pythonPath
} else {
    throw "Python nao encontrado na pasta .venv\Scripts."
}

if (-not (Test-Path -LiteralPath $mainPath)) {
    throw "Arquivo main.py nao encontrado em '$mainPath'."
}

& $pythonExecutable $mainPath run-once

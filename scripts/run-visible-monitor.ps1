$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$mainPath = Join-Path $projectRoot "main.py"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Python nao encontrado em '$pythonPath'."
}

if (-not (Test-Path -LiteralPath $mainPath)) {
    throw "Arquivo main.py nao encontrado em '$mainPath'."
}

$env:BROWSER_HEADLESS = "false"

Write-Host "Iniciando monitor visivel do MegaHub..." -ForegroundColor Cyan
Write-Host "O navegador sera aberto durante as leituras e os logs ficarao nesta janela." -ForegroundColor Gray
Write-Host "Para encerrar, feche esta janela ou pressione CTRL+C." -ForegroundColor Gray
Write-Host ""

& $pythonPath $mainPath monitor

param(
    [string]$PrimaryName,
    [ValidateSet("consultor", "coordenador", "gestor")]
    [string]$PrimaryRole,
    [string]$PrimaryWebhookUrl,
    [string]$SecondaryName,
    [ValidateSet("consultor", "coordenador", "gestor")]
    [string]$SecondaryRole,
    [string]$SecondaryWebhookUrl,
    [switch]$EnableMinhaFila,
    [switch]$EnableFila,
    [string]$ConsultantName,
    [switch]$RegisterTask,
    [switch]$OpenLogin,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

function Read-RequiredInput {
    param(
        [string]$Prompt,
        [string]$DefaultValue = ""
    )

    while ($true) {
        $suffix = if ($DefaultValue) { " [$DefaultValue]" } else { "" }
        $value = Read-Host "$Prompt$suffix"
        if (-not $value -and $DefaultValue) {
            return $DefaultValue
        }
        if ($value -and $value.Trim()) {
            return $value.Trim()
        }
    }
}

function Read-YesNo {
    param(
        [string]$Prompt,
        [bool]$DefaultValue
    )

    $defaultLabel = if ($DefaultValue) { "S" } else { "N" }

    while ($true) {
        $value = Read-Host "$Prompt [S/N] ($defaultLabel)"
        if (-not $value) {
            return $DefaultValue
        }

        switch ($value.Trim().ToUpperInvariant()) {
            "S" { return $true }
            "SIM" { return $true }
            "Y" { return $true }
            "YES" { return $true }
            "N" { return $false }
            "NAO" { return $false }
            "NÃO" { return $false }
            "NO" { return $false }
        }
    }
}

function Read-Role {
    param(
        [string]$Prompt,
        [string]$DefaultValue
    )

    while ($true) {
        $value = Read-RequiredInput -Prompt $Prompt -DefaultValue $DefaultValue
        $normalized = $value.Trim().ToLowerInvariant()
        if ($normalized -in @("consultor", "coordenador", "gestor")) {
            return $normalized
        }
        Write-Host "Informe um papel valido: consultor, coordenador ou gestor." -ForegroundColor Yellow
    }
}

function Convert-ToId {
    param([string]$Value)

    if (-not $Value) {
        return "perfil"
    }

    $normalized = $Value.Normalize([Text.NormalizationForm]::FormD)
    $builder = New-Object System.Text.StringBuilder
    foreach ($char in $normalized.ToCharArray()) {
        $unicodeCategory = [Globalization.CharUnicodeInfo]::GetUnicodeCategory($char)
        if ($unicodeCategory -ne [Globalization.UnicodeCategory]::NonSpacingMark) {
            [void]$builder.Append($char)
        }
    }

    $ascii = $builder.ToString().ToLowerInvariant()
    $ascii = [Regex]::Replace($ascii, "[^a-z0-9]+", "-")
    $ascii = $ascii.Trim("-")
    if (-not $ascii) {
        return "perfil"
    }
    return $ascii
}

function Resolve-PythonCommand {
    param([string]$ProjectRoot)

    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython) {
        return @{
            CreateExe = $null
            CreateArgs = @()
            Python = $venvPython
        }
    }

    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @{
            CreateExe = "py"
            CreateArgs = @("-3")
            Python = $venvPython
        }
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @{
            CreateExe = "python"
            CreateArgs = @()
            Python = $venvPython
        }
    }

    throw "Python nao encontrado. Instale Python 3.11+ antes de continuar."
}

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

    Write-Utf8NoBom -FilePath $FilePath -Content ($lines -join [Environment]::NewLine)
}

function Write-Utf8NoBom {
    param(
        [string]$FilePath,
        [string]$Content
    )

    $directory = Split-Path -Parent $FilePath
    if ($directory) {
        New-Item -ItemType Directory -Force -Path $directory | Out-Null
    }

    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($FilePath, $Content, $utf8NoBom)
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonInfo = Resolve-PythonCommand -ProjectRoot $projectRoot

if (-not (Test-Path -LiteralPath $pythonInfo.Python)) {
    Write-Host "Criando ambiente virtual..." -ForegroundColor Cyan
    & $pythonInfo.CreateExe @($pythonInfo.CreateArgs + @("-m", "venv", "$projectRoot\.venv"))
}

$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pipExe = Join-Path $projectRoot ".venv\Scripts\pip.exe"

Write-Host "Instalando dependencias..." -ForegroundColor Cyan
& $pipExe install -r (Join-Path $projectRoot "requirements.txt") | Out-Host

Write-Host "Instalando navegadores do Playwright..." -ForegroundColor Cyan
& $pythonExe -m playwright install | Out-Host

$envPath = Join-Path $projectRoot ".env"
if (-not (Test-Path -LiteralPath $envPath)) {
    Copy-Item -LiteralPath (Join-Path $projectRoot ".env.example") -Destination $envPath
}

Set-OrReplaceEnvValue -FilePath $envPath -Key "CONTEXTS_CONFIG_PATH" -Value "config/local/contexts.toml"
Set-OrReplaceEnvValue -FilePath $envPath -Key "PROFILES_CONFIG_PATH" -Value "config/local/profiles.toml"

$localConfigDir = Join-Path $projectRoot "config\local"
New-Item -ItemType Directory -Force -Path $localConfigDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $projectRoot "data\browser-profile-main") | Out-Null

$contextsPath = Join-Path $localConfigDir "contexts.toml"
$profilesPath = Join-Path $localConfigDir "profiles.toml"

if ((Test-Path -LiteralPath $contextsPath -or Test-Path -LiteralPath $profilesPath) -and -not $Force) {
    $overwrite = Read-YesNo -Prompt "Ja existe configuracao local. Deseja sobrescrever?" -DefaultValue $false
    if (-not $overwrite) {
        throw "Instalacao cancelada para evitar sobrescrever a configuracao atual."
    }
}

if (-not $PrimaryName) {
    $PrimaryName = Read-RequiredInput -Prompt "Nome do perfil principal"
}
if (-not $PrimaryRole) {
    $PrimaryRole = Read-Role -Prompt "Papel do perfil principal" -DefaultValue "consultor"
}
if (-not $PrimaryWebhookUrl) {
    $PrimaryWebhookUrl = Read-RequiredInput -Prompt "Webhook do Teams do perfil principal"
}

if (-not $PSBoundParameters.ContainsKey("EnableMinhaFila")) {
    $EnableMinhaFila = Read-YesNo -Prompt "Ativar monitoramento da Minha Fila?" -DefaultValue $true
}
if (-not $PSBoundParameters.ContainsKey("EnableFila")) {
    $EnableFila = Read-YesNo -Prompt "Ativar monitoramento da Fila?" -DefaultValue $false
}
if (-not $EnableMinhaFila -and -not $EnableFila) {
    throw "Ative pelo menos uma fonte para concluir a instalacao."
}
if ($EnableMinhaFila -and -not $ConsultantName) {
    $ConsultantName = Read-RequiredInput -Prompt "Nome do consultor visivel na Minha Fila" -DefaultValue $PrimaryName
}

$addSecondaryProfile = $false
if (-not $SecondaryName -and -not $SecondaryWebhookUrl) {
    $addSecondaryProfile = Read-YesNo -Prompt "Deseja adicionar um segundo perfil de notificacao?" -DefaultValue $false
} else {
    $addSecondaryProfile = $true
}

if ($addSecondaryProfile) {
    if (-not $SecondaryName) {
        $SecondaryName = Read-RequiredInput -Prompt "Nome do segundo perfil"
    }
    if (-not $SecondaryRole) {
        $SecondaryRole = Read-Role -Prompt "Papel do segundo perfil" -DefaultValue "coordenador"
    }
    if (-not $SecondaryWebhookUrl) {
        $SecondaryWebhookUrl = Read-RequiredInput -Prompt "Webhook do Teams do segundo perfil"
    }
}

if (-not $PSBoundParameters.ContainsKey("RegisterTask")) {
    $RegisterTask = Read-YesNo -Prompt "Registrar tarefa automatica de 2 em 2 minutos?" -DefaultValue $true
}
if (-not $PSBoundParameters.ContainsKey("OpenLogin")) {
    $OpenLogin = Read-YesNo -Prompt "Abrir a tela de login ao final da instalacao?" -DefaultValue $true
}

$primaryId = Convert-ToId -Value $PrimaryName
$secondaryId = if ($SecondaryName) { Convert-ToId -Value $SecondaryName } else { $null }
$allProfileIds = @($primaryId)
if ($secondaryId) {
    $allProfileIds += $secondaryId
}

$contextsContent = @"
[[contexts]]
id = "main-session"
name = "Sessao Principal"
enabled = true
profile_dir = "data/browser-profile-main"
"@

if ($EnableMinhaFila) {
    $consultantEscaped = $ConsultantName.Replace('"', '\"')
    $contextsContent += @"

[[sources]]
id = "minha_fila_principal"
name = "Minha Fila Principal"
kind = "minha_fila"
context_id = "main-session"
url = "https://megahub.megawork.com/Chamado/MinhaFila"
enabled = true
first_page_only = true
consultant_name = "$consultantEscaped"
only_open = true
only_assigned_to_me = true
"@
}

if ($EnableFila) {
    $contextsContent += @"

[[sources]]
id = "fila_principal"
name = "Fila Principal"
kind = "fila"
context_id = "main-session"
url = "https://megahub.megawork.com/Chamado/Index"
enabled = true
first_page_only = true
include_closed = false
include_assigned = true
"@
}

$profilesContent = @"
# Perfis e subscricoes desta instalacao local.
# Edite ticket_types, priorities, companies e consultants para filtrar notificacoes.

[[profiles]]
id = "$primaryId"
name = "$($PrimaryName.Replace('"', '\"'))"
role = "$PrimaryRole"
enabled = true
webhook_url = "$($PrimaryWebhookUrl.Replace('"', '\"'))"
"@

if ($secondaryId) {
    $profilesContent += @"

[[profiles]]
id = "$secondaryId"
name = "$($SecondaryName.Replace('"', '\"'))"
role = "$SecondaryRole"
enabled = true
webhook_url = "$($SecondaryWebhookUrl.Replace('"', '\"'))"
"@
}

if ($EnableMinhaFila) {
    $profilesContent += @"

[[subscriptions]]
id = "alerta-minha-fila-principal"
name = "Alerta Minha Fila"
enabled = true
source_ids = ["minha_fila_principal"]
profile_ids = ["$primaryId"]
title_prefix = "Alerta da Minha Fila"
include_load = false
ticket_types = []
priorities = []
companies = []
consultants = []
"@
}

if ($EnableFila) {
    $filaProfileIds = ($allProfileIds | ForEach-Object { "`"$_`"" }) -join ", "
    $profilesContent += @"

[[subscriptions]]
id = "alerta-fila-principal"
name = "Alerta Fila"
enabled = true
source_ids = ["fila_principal"]
profile_ids = [$filaProfileIds]
title_prefix = "Novo chamado na Fila"
include_load = true
ticket_types = []
priorities = []
companies = []
consultants = []
"@
}

Write-Utf8NoBom -FilePath $contextsPath -Content $contextsContent.TrimStart()
Write-Utf8NoBom -FilePath $profilesPath -Content $profilesContent.TrimStart()

if ($RegisterTask) {
    & (Join-Path $projectRoot "scripts\register-task.ps1")
}

$firstSource = if ($EnableFila) { "fila_principal" } elseif ($EnableMinhaFila) { "minha_fila_principal" } else { $null }

if ($OpenLogin -and $firstSource) {
    & $pythonExe (Join-Path $projectRoot "main.py") login --source $firstSource
}

Write-Host ""
Write-Host "Instalacao concluida." -ForegroundColor Green
Write-Host "Configuracao local gerada em:"
Write-Host " - $contextsPath"
Write-Host " - $profilesPath"
Write-Host ""
if (-not $OpenLogin -and $firstSource) {
    Write-Host "Proximo passo recomendado:"
    Write-Host "  $pythonExe `"$projectRoot\main.py`" login --source $firstSource"
}

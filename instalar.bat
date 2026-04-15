@echo off
chcp 65001 > nul
title SDWA — Instalador

echo.
echo  ============================================
echo   SDWA — Service Desk Workflow Automation
echo   Instalador automatico
echo  ============================================
echo.

REM ── 1. Verifica Python ───────────────────────────────────────────────────
echo [1/4] Verificando Python...
python --version > nul 2>&1
if errorlevel 1 (
    echo.
    echo  ERRO: Python nao encontrado.
    echo  Instale o Python 3.11 ou superior em:
    echo  https://www.python.org/downloads/
    echo.
    echo  ATENCAO: Durante a instalacao do Python, marque a opcao
    echo  "Add Python to PATH" antes de clicar em Install Now.
    echo.
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo     Python %PYVER% encontrado. OK

REM ── 2. Cria ambiente virtual ──────────────────────────────────────────────
echo.
echo [2/4] Criando ambiente virtual...
if exist ".venv" (
    echo     Ambiente virtual ja existe. Pulando criacao.
) else (
    python -m venv .venv
    if errorlevel 1 (
        echo  ERRO: Falha ao criar ambiente virtual.
        pause
        exit /b 1
    )
    echo     Ambiente virtual criado. OK
)

REM ── 3. Instala dependencias ───────────────────────────────────────────────
echo.
echo [3/4] Instalando dependencias ^(pode demorar alguns minutos^)...
call .venv\Scripts\pip install --upgrade pip --quiet
call .venv\Scripts\pip install playwright python-dotenv requests pystray Pillow --quiet
if errorlevel 1 (
    echo  ERRO: Falha ao instalar dependencias. Verifique sua conexao com a internet.
    pause
    exit /b 1
)
echo     Dependencias instaladas. OK

REM ── 4. Instala navegador Playwright ──────────────────────────────────────
echo.
echo [4/4] Instalando navegador ^(pode demorar^)...
call .venv\Scripts\playwright install chromium
if errorlevel 1 (
    echo  ERRO: Falha ao instalar o navegador.
    pause
    exit /b 1
)
echo     Navegador instalado. OK

REM ── Sucesso ───────────────────────────────────────────────────────────────
echo.
echo  ============================================
echo   Instalacao concluida com sucesso!
echo  ============================================
echo.
echo  Proximos passos:
echo.
echo   1. Importe o arquivo de configuracao recebido pelo painel
echo      (duplo-clique em "Iniciar SDWA.vbs", depois va em
echo       Configuracoes ^> Configuracao Completa ^> Importar)
echo.
echo   2. Faca o login no MegaHub:
echo      Abra o CMD nesta pasta e execute:
echo         python main.py login
echo.
echo   3. Inicie o monitor:
echo      Duplo-clique em "Iniciar SDWA.vbs"
echo.
pause

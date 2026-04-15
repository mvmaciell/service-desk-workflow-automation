@echo off
chcp 65001 > nul
title SDWA — Login MegaHub

echo.
echo  ============================================
echo   SDWA — Login no MegaHub
echo  ============================================
echo.
echo  O navegador vai abrir automaticamente.
echo  Faca o login normalmente com seu usuario e senha.
echo  Quando terminar, FECHE O NAVEGADOR.
echo  Esta janela vai fechar sozinha em seguida.
echo.
echo  Aguarde...
echo.

call .venv\Scripts\python.exe main.py login

if errorlevel 1 (
    echo.
    echo  ERRO: Falha no login. Verifique sua conexao e tente novamente.
    echo.
    pause
    exit /b 1
)

echo.
echo  Login realizado com sucesso!
echo  Voce ja pode fechar esta janela e iniciar o monitor.
echo.
pause

' start-tray.vbs
' Inicia o icone da bandeja do sistema (tray app) sem abrir janela de console.
' Usar wscript.exe (subsystem GUI) — totalmente silencioso.
'
' Uso manual:   wscript.exe scripts\start-tray.vbs
' Automatico:   register-task.ps1 -RegisterTray  (cria tarefa AtLogon)
' Startup:      Criar atalho para este arquivo em
'               %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup

Set FSO    = CreateObject("Scripting.FileSystemObject")
Set oShell = CreateObject("WScript.Shell")

Dim scriptDir, projectRoot
scriptDir   = FSO.GetParentFolderName(WScript.ScriptFullName)
projectRoot = FSO.GetParentFolderName(scriptDir)

Dim pythonw, python, mainPy
pythonw = projectRoot & "\.venv\Scripts\pythonw.exe"
python  = projectRoot & "\.venv\Scripts\python.exe"
mainPy  = projectRoot & "\main.py"

Dim exe
If FSO.FileExists(pythonw) Then
    exe = pythonw
ElseIf FSO.FileExists(python) Then
    exe = python
Else
    WScript.Quit 1
End If

If Not FSO.FileExists(mainPy) Then
    WScript.Quit 1
End If

Dim cmd
cmd = """" & exe & """ """ & mainPy & """ tray"
oShell.Run cmd, 0, False

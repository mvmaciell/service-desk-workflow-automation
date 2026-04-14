' run-silent.vbs
' Launcher completamente silencioso para o Task Scheduler.
' Usa wscript.exe (subsystem GUI) — nunca abre janela de console.
'
' Uso: wscript.exe scripts\run-silent.vbs
' (configurado automaticamente por register-task.ps1)

Set FSO    = CreateObject("Scripting.FileSystemObject")
Set oShell = CreateObject("WScript.Shell")

' Sobe dois niveis a partir de scripts\ para chegar ao projectRoot
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
    ' Python nao encontrado — encerra silenciosamente
    WScript.Quit 1
End If

If Not FSO.FileExists(mainPy) Then
    WScript.Quit 1
End If

' Parametro 0 = SW_HIDE (janela oculta), False = nao aguardar conclusao
Dim cmd
cmd = """" & exe & """ """ & mainPy & """ run-once"
oShell.Run cmd, 0, False

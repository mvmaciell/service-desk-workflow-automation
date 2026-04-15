' SDWA — Iniciador silencioso
' Duplo-clique neste arquivo para iniciar o monitor sem janela alguma.

Dim oShell, sRoot, sPythonw, sMain, sCmd

Set oShell = CreateObject("WScript.Shell")

' Resolve a pasta raiz do projeto (pai da pasta onde este .vbs esta)
sRoot = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\") - 1)

sPythonw = sRoot & "\.venv\Scripts\pythonw.exe"
sMain    = sRoot & "\main.py"

' Verifica se pythonw.exe existe; se nao, usa python.exe com janela oculta
If Not CreateObject("Scripting.FileSystemObject").FileExists(sPythonw) Then
    sPythonw = sRoot & "\.venv\Scripts\python.exe"
End If

sCmd = Chr(34) & sPythonw & Chr(34) & " " & Chr(34) & sMain & Chr(34) & " tray"

' Executa sem janela (0 = oculto, False = nao aguarda)
oShell.Run sCmd, 0, False

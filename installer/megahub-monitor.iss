; Inno Setup Script para MegaHub Monitor
;
; Pre-requisitos:
;   1. Build com PyInstaller: pyinstaller megahub-monitor.spec
;   2. Output em dist/megahub-monitor/
;   3. Compilar este .iss com Inno Setup 6+
;
; O instalador:
;   - Copia os arquivos para %LOCALAPPDATA%\Programs\MegaHub Monitor
;   - Cria atalho no Menu Iniciar
;   - Opcionalmente adiciona ao Startup do Windows
;   - Roda install-browsers no pos-instalacao

[Setup]
AppName=MegaHub Monitor
AppVersion=0.2.0
AppPublisher=Megawork
DefaultDirName={localappdata}\Programs\MegaHub Monitor
DefaultGroupName=MegaHub Monitor
OutputDir=output
OutputBaseFilename=MegaHub-Monitor-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
WizardStyle=modern
SetupIconFile=
UninstallDisplayName=MegaHub Monitor

[Files]
Source: "..\dist\megahub-monitor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{app}\config\local"
Name: "{app}\data"
Name: "{app}\data\logs"

[Icons]
Name: "{group}\MegaHub Monitor"; Filename: "{app}\megahub-monitor.exe"
Name: "{autodesktop}\MegaHub Monitor"; Filename: "{app}\megahub-monitor.exe"; Tasks: desktopicon
Name: "{userstartup}\MegaHub Monitor"; Filename: "{app}\megahub-monitor.exe"; Tasks: autostart

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Area de Trabalho"; GroupDescription: "Atalhos:"; Flags: unchecked
Name: "autostart"; Description: "Iniciar automaticamente com o Windows"; GroupDescription: "Opcoes:"

[Run]
Filename: "{app}\megahub-monitor.exe"; Parameters: "install-browsers"; StatusMsg: "Instalando navegador (Chromium)..."; Flags: runhidden waituntilterminated
Filename: "{app}\megahub-monitor.exe"; Description: "Iniciar MegaHub Monitor"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\data"
Type: filesandordirs; Name: "{app}\config\local"

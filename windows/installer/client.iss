; Inno Setup 6 – Installer „KP Lager Client“ (Fenster zum Server + D30-PC-Bridge)
#define AppName "KP Lager"
#define AppVersion "0.1.0"

[Setup]
AppId={{6F0C3C2E-7B7A-4B0E-9A53-2D6F6E8C1A02}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\KP Lager Client
DefaultGroupName=KP Lager
OutputDir=..\..\dist\installer
OutputBaseFilename=KP-Lager-Client-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
DisableProgramGroupPage=yes

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "Verknüpfung auf dem Desktop"; Flags: unchecked
Name: "autostart"; Description: "Bei der Anmeldung nur die D30-Bridge im Hintergrund starten"; Flags: unchecked

[Files]
Source: "..\..\dist\lager-client\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\KP Lager"; Filename: "{app}\lager-client.exe"
Name: "{autodesktop}\KP Lager"; Filename: "{app}\lager-client.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "KPLagerBridge"; ValueData: """{app}\lager-client.exe"" --bridge-only"; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\lager-client.exe"; Description: "KP Lager jetzt starten"; Flags: nowait postinstall skipifsilent

; Inno Setup 6 – Installer „KP Lager Server“ (Debug/Entwicklung auf dem PC)
#define AppName "KP Lager Server"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6F0C3C2E-7B7A-4B0E-9A53-2D6F6E8C1A01}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\KP Lager Server
DefaultGroupName=KP Lager
OutputDir=..\..\dist\installer
OutputBaseFilename=KP-Lager-Server-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
DisableProgramGroupPage=yes

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "Verknüpfung auf dem Desktop"; Flags: unchecked
Name: "lan"; Description: "Im LAN erreichbar machen (--host 0.0.0.0, Windows fragt nach der Firewall)"; Flags: unchecked

[Files]
Source: "..\..\dist\lager-server\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\KP Lager Server (Debug-Konsole)"; Filename: "{app}\lager-server.exe"; Parameters: "{code:Args}"
Name: "{group}\KP Lager Datenordner"; Filename: "{localappdata}\KP Lager Server\data"
Name: "{autodesktop}\KP Lager Server"; Filename: "{app}\lager-server.exe"; Parameters: "{code:Args}"; Tasks: desktopicon

[Code]
function Args(Param: String): String;
begin
  if WizardIsTaskSelected('lan') then Result := '--host 0.0.0.0' else Result := '';
end;

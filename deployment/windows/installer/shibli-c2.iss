#define MyAppName "SHIBLI C2"
#define MyAppVersion "1.0"
#define MyAppPublisher "SHIBLI"
#define MyAppExeName "ShibliC2.exe"

[Setup]
AppId={{8F3C2A91-4B6E-4E1A-9C7D-A1B2C3D4E5F6}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v1.0
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\ShibliC2
DefaultGroupName=SHIBLI C2
DisableProgramGroupPage=no
OutputDir=..\..\..\release\v1.0
OutputBaseFilename=ShibliC2-Setup-v1.0
SetupIconFile=..\..\assets\logo\shibli.ico
UninstallDisplayIcon={app}\shibli.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel1=Welcome to the SHIBLI C2 Setup Wizard
WelcomeLabel2=This installs SHIBLI C2 on your computer.%n%nNo additional downloads are required.

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "..\..\..\dist\ShibliC2\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\assets\logo\shibli.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\..\config.example.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\..\.env.example"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\..\go2rtc.example.yaml"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\runtime\windows\go2rtc.exe"; DestDir: "{app}\bin"; Flags: ignoreversion
Source: "..\..\runtime\windows\ffmpeg.exe"; DestDir: "{app}\bin"; Flags: ignoreversion
Source: "..\..\..\dist\ShibliControls\*"; DestDir: "{app}\controls"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\runtime\windows\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall skipifsourcedoesntexist
Source: "..\..\runtime\windows\vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall skipifsourcedoesntexist
; Persistent data is created under {commonappdata}\ShibliC2 — never overwrite it.

[Dirs]
Name: "{commonappdata}\ShibliC2\config"
Name: "{commonappdata}\ShibliC2\data"
Name: "{commonappdata}\ShibliC2\logs"
Name: "{commonappdata}\ShibliC2\recordings"
Name: "{commonappdata}\ShibliC2\snapshots"
Name: "{commonappdata}\ShibliC2\exports"
Name: "{commonappdata}\ShibliC2\backups"

[Icons]
Name: "{group}\SHIBLI C2"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\shibli.ico"
Name: "{autodesktop}\SHIBLI C2"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\shibli.ico"; Tasks: desktopicon

[Run]
Filename: "{tmp}\vc_redist.x64.exe"; Parameters: "/install /quiet /norestart"; StatusMsg: "Installing bundled Visual C++ runtime..."; Flags: skipifdoesntexist waituntilterminated
Filename: "{tmp}\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"; Parameters: "/silent /install"; StatusMsg: "Installing bundled desktop display runtime..."; Flags: skipifdoesntexist waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Description: "Launch SHIBLI C2"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\*.log"
; Do not delete {commonappdata}\ShibliC2 — recordings, users, and cameras stay.

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  Cfg: String;
  EnvFile: String;
  Example: String;
begin
  if CurStep = ssPostInstall then
  begin
    Cfg := ExpandConstant('{commonappdata}\ShibliC2\config\go2rtc.yaml');
    if not FileExists(Cfg) then
      FileCopy(ExpandConstant('{app}\go2rtc.example.yaml'), Cfg, False);
    EnvFile := ExpandConstant('{commonappdata}\ShibliC2\data\.env');
    Example := ExpandConstant('{app}\.env.example');
    if (not FileExists(EnvFile)) and FileExists(Example) then
      FileCopy(Example, EnvFile, False);
  end;
end;

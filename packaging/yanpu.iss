; ELO-NVH desktop application installer
; Build with: ISCC.exe /DMyAppVersion=0.1.0 packaging\yanpu.iss

#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif

#define MyAppName "ELO-NVH 振动质检系统"
#define MyAppExeName "ELO-NVH.exe"

[Setup]
AppId={{E1D4DF93-4EA1-4A1E-9A9C-6B019A0E8E28}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=ELO-NVH
DefaultDirName={localappdata}\Programs\ELO-NVH
DefaultGroupName=ELO-NVH
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=ELO-NVH-Setup-{#MyAppVersion}
SetupIconFile=..\qianduan\elo_nvh.ico
; The CPU-only lightweight build is below GitHub's 2 GB per-file limit, so
; keep the complete installer in one executable without .bin split files.
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
WizardStyle=modern
SetupLogging=yes
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\{#MyAppExeName}
Uninstallable=yes
UsePreviousAppDir=yes
VersionInfoVersion={#MyAppVersion}
VersionInfoDescription=ELO-NVH 振动质检系统安装程序
VersionInfoProductName=ELO-NVH 振动质检系统

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加快捷方式："; Flags: unchecked

[Files]
; The complete PyInstaller onedir output is required at runtime.
Source: "..\dist\ELO-NVH\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; DestName: "README.md"; Flags: ignoreversion
Source: "..\软件说明书.md"; DestDir: "{app}"; DestName: "软件说明书.md"; Flags: ignoreversion

[Dirs]
; These folders match the first-run defaults in app_config.py.
Name: "{app}\logs"
Name: "{app}\logs\models"
Name: "{app}\logs\saved_data"
Name: "{app}\data"

[Icons]
Name: "{group}\ELO-NVH 振动质检系统"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\软件说明书"; Filename: "{app}\软件说明书.md"; WorkingDir: "{app}"
Name: "{autodesktop}\ELO-NVH 振动质检系统"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 ELO-NVH 振动质检系统"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

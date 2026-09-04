; ─────────────────────────────────────────────────────────────────────────────
; CNC NEXORA GCS - COMMERCIAL INNO SETUP SCRIPT
; ─────────────────────────────────────────────────────────────────────────────
#define MyAppName "CNC NExora GCS"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "CNC NExora Technologies"
#define MyAppURL "https://cncnexora.vn"
#define MyAppExeName "GCS_ROV.exe"

[Setup]
AppId={{8B49B0E1-831C-4B9A-99F2-4F17A91D3C08}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\CNC NExora GCS
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=D:\python\GCS_ROV\LICENSE.txt
OutputDir=D:\python\GCS_ROV\Output
OutputBaseFilename=Setup_CNC_NExora_GCS_v1.0
SetupIconFile=D:\python\GCS_ROV\GUI\img\iconapp.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoVersion=1.0.0.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=CNC NExora Subsea ROV Ground Control Station
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion=1.0.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "D:\python\GCS_ROV\dist\GCS_ROV\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "D:\python\GCS_ROV\yolov8n.pt"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\python\GCS_ROV\3DC.obj"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\python\GCS_ROV\3DC.mtl"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\python\GCS_ROV\6DC.obj"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\python\GCS_ROV\6DC.mtl"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\python\GCS_ROV\LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\python\GCS_ROV\HUONG_DAN_SU_DUNG_CNC_NEXORA_GCS.pdf"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\python\GCS_ROV\assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\GUI\img\iconapp.ico"
Name: "{autoprograms}\{#MyAppName} - Sổ Tay Hướng Dẫn Sử Dụng"; Filename: "{app}\HUONG_DAN_SU_DUNG_CNC_NEXORA_GCS.pdf"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\GUI\img\iconapp.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
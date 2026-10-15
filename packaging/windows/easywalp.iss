; Inno Setup script for EasyWalp (per-user install, no admin rights).
; Build:  ISCC /DAppVersion=0.1.0 /DSourceDir=<repo>\dist\EasyWalp packaging\windows\easywalp.iss
; Bilingual installer (English + Persian messages), .easywalp file association,
; Start Menu + desktop shortcuts, clean uninstaller.

#define AppName "EasyWalp"
#define AppPublisher "Wallify"
#define AppURL "https://t.me/WallifyChannel"
#define AppExe "EasyWalp.exe"

#ifndef AppVersion
#define AppVersion "0.0.0"
#endif
#ifndef SourceDir
#define SourceDir "..\dist\EasyWalp"
#endif

[Setup]
AppId={{576C2A49-3B17-44A4-8648-EA9A65512AA4}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
; Per-user install: no admin rights needed, installed under %LOCALAPPDATA%\Programs
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\installer-out
OutputBaseFilename=EasyWalp-Setup-{#AppVersion}
SetupIconFile=..\assets\icons\easywalp.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=yes
CloseApplications=yes
ChangesAssociations=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "farsi"; MessagesFile: "Farsi.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "Farsi.isl"; DestDir: "{app}\languages"; Flags: skipifsourcedoesntexist

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; user presets/settings are intentionally kept on uninstall

[Registry]
; .easywalp preset packages open with EasyWalp
Root: HKA; Subkey: "Software\Classes\.easywalp"; ValueType: string; ValueName: ""; ValueData: "EasyWalpPreset"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\EasyWalpPreset"; ValueType: string; ValueName: ""; ValueData: "EasyWalp Preset"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\EasyWalpPreset\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe},0"
Root: HKA; Subkey: "Software\Classes\EasyWalpPreset\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""

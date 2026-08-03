; Inno Setup script for the STANDARD (installer) Drawing2CAD build.
; Packages the one-dir PyInstaller output (dist\Drawing2CAD\) into a single
; setup executable named "03 - Drawing2CAD.exe".
;
; Build:  ISCC.exe installer\Drawing2CAD.iss
; (ISCC ships with Inno Setup 6, preinstalled on GitHub windows-latest runners.)

#define AppName    "Drawing2CAD"
#define AppVersion "1.0.0"
#define AppExeName "Drawing2CAD.exe"
; numeric prefix of the project folder, per the build convention
#define Prefix     "03"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Drawing2CAD
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; per-user install needs no admin rights
PrivilegesRequired=lowest
OutputDir=..\installer_out
OutputBaseFilename={#Prefix} - {#AppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
; the whole one-dir payload
Source: "..\dist\Drawing2CAD\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

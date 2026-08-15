; NetConneXion v2.0 — Inno Setup installer script
; Сборка: iscc NetConneXion.iss
; Результат: installer\NetConneXion_Setup_v2.0.1.exe

#define MyAppName        "NetConneXion"
#define MyAppVersion     "2.0.1"
#define MyAppDescription "Network Profile Manager"
#define MyAppExeName     "NetConneXion.exe"
#define MyAppSourceDir   "dist\NetConneXion"
#define MyAppIcoFile     "data\app.ico"

; ── Setup ────────────────────────────────────────────────────────────────────

[Setup]
; AppId MUST remain unchanged across updates so Windows recognises upgrades
AppId={{3C7A2F89-D146-4E8B-A052-7F1B6C3D9E40}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppName}

; Installation directory
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; Output
OutputDir=installer
OutputBaseFilename=NetConneXion_Setup_v{#MyAppVersion}

; Compression (lzma2/ultra64 — максимальное сжатие)
Compression=lzma2/ultra64
SolidCompression=yes

; UAC — приложению нужен admin для netsh
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=

; Visuals
SetupIconFile={#MyAppIcoFile}
UninstallDisplayIcon={app}\{#MyAppExeName}
WizardStyle=modern
WizardSmallImageFile=

; Misc
MinVersion=10.0
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableWelcomePage=no
AllowNoIcons=yes

; ── Languages ────────────────────────────────────────────────────────────────

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

; ── Custom messages ──────────────────────────────────────────────────────────

[CustomMessages]
russian.AppDescription={#MyAppDescription}
english.AppDescription={#MyAppDescription}

; ── Tasks (options shown to user during install) ─────────────────────────────

[Tasks]
Name: "desktopicon";  \
  Description: "{cm:CreateDesktopIcon}"; \
  GroupDescription: "{cm:AdditionalIcons}"

; ── Directories (explicit ACL so non-admin users can launch the exe) ─────────

[Dirs]
Name: "{app}"; Permissions: users-readexec
Name: "{commonappdata}\NetConneXion"; Permissions: users-modify

; ── Files ────────────────────────────────────────────────────────────────────

[Files]
; All PyInstaller output — recursive
Source: "{#MyAppSourceDir}\*"; \
  DestDir: "{app}"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

; ── Shortcuts ────────────────────────────────────────────────────────────────

[Icons]
; Start Menu
Name: "{autoprograms}\{#MyAppName}"; \
  Filename: "{app}\{#MyAppExeName}"; \
  Comment: "{#MyAppDescription}"

; Desktop (only if task selected)
Name: "{autodesktop}\{#MyAppName}"; \
  Filename: "{app}\{#MyAppExeName}"; \
  Comment: "{#MyAppDescription}"; \
  Tasks: desktopicon

; ── Post-install run ─────────────────────────────────────────────────────────

[Run]
Filename: "{app}\{#MyAppExeName}"; \
  Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; \
  Flags: nowait postinstall skipifsilent shellexec

; ── Uninstall ────────────────────────────────────────────────────────────────

[UninstallRun]
; Завершаем процесс если запущен
Filename: "taskkill.exe"; \
  Parameters: "/f /im {#MyAppExeName}"; \
  Flags: runhidden skipifdoesntexist; \
  RunOnceId: "KillApp"

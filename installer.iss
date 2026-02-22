#define MyAppName "Quick IP Change"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Quick IP Change"
#define MyAppExeName "QuickIPChange.exe"

#if FileExists("dist\QuickIPChange.exe")
  #define MyBuildExe "dist\QuickIPChange.exe"
  #define BuildOneFile 1
#elif FileExists("dist\QuickIPChange\QuickIPChange.exe")
  #define BuildOneDir 1
#else
  #error "Не найден QuickIPChange.exe. Сначала выполните: pyinstaller build.spec"
#endif

[Setup]
AppId={{A1E7B2A8-6B51-4E19-9C4B-6F0F0A7D4E11}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=installer_output
OutputBaseFilename=QuickIPChangeSetup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительные задачи:"; Flags: unchecked

[Files]
#ifdef BuildOneDir
Source: "dist\QuickIPChange\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
#else
Source: "{#MyBuildExe}"; DestDir: "{app}"; DestName: "{#MyAppExeName}"; Flags: ignoreversion
#endif

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить {#MyAppName}"; Flags: nowait postinstall skipifsilent

; Inno Setup 6 script. Save as UTF-8 with BOM.
; Official Windows installer for 字幕去除与繁体转换.
#ifndef AppVersion
  #define AppVersion "1.4.3"
#endif

#define AppName "字幕去除与繁体转换"
#define AppExe "启动程序.exe"
#define AppPublisher "LuYiYan"
#define AppURL "https://github.com/LuYiYan/subtitle-extractor"

[Setup]
AppId={{8F4E2C1A-6B7D-4E9F-A1C3-5D8E7F0A2B64}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=no
AllowNoIcons=no
OutputDir=..\vsr_out\installer
OutputBaseFilename=subtitle-extractor-v{#AppVersion}-windows-cpu-setup
SetupIconFile=..\design\vsr.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2
SolidCompression=yes
LZMAUseSeparateProcess=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
MinVersion=10.0
VersionInfoVersion={#AppVersion}.0
VersionInfoProductName={#AppName}
VersionInfoDescription={#AppName} Windows 正式版
CloseApplications=force
RestartApplications=no

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Dirs]
; First launch unpacks the runtime into this folder, so normal users must be able to write here.
Name: "{app}"; Permissions: users-modify

[Files]
Source: "..\vsr_out\Release\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "*.7z,*.7z.*,*.sha256"

[Icons]
Name: "{group}\字幕去除器"; Filename: "{app}\{#AppExe}"; Comment: "{#AppName}"
Name: "{autodesktop}\字幕去除器"; Filename: "{app}\{#AppExe}"; Comment: "{#AppName}"; Tasks: desktopicon
Name: "{group}\卸载 {#AppName}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#AppExe}"; Description: "立即打开字幕去除器"; Flags: nowait postinstall skipifsilent

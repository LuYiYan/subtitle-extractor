; Inno Setup 6 script. Save as UTF-8 with BOM.
; Official Windows installer for 字幕去除与繁体转换.
#ifndef AppVersion
  #define AppVersion "1.4.4"
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
; QPT refuses to install packages when this folder contains Chinese, spaces, or
; characters outside its ASCII allow-list. The Start Menu name stays Chinese.
DefaultDirName=C:\SubtitleExtractor
UsePreviousAppDir=no
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
; Inno Setup 6 does not ship this translation. The file next to this script is the
; upstream unofficial translation, plus the five 6.4 extraction messages it lacked.
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"

[Messages]
SelectDirDesc=请选择一个纯英文、没有空格的安装目录。
SelectDirLabel3=安装程序会把 [name] 安装到下面的文件夹。目录不能包含中文、空格或特殊字符，否则第一次打开无法安装组件。
SelectDirBrowseLabel=例如 C:\SubtitleExtractor 或 E:\SubtitleExtractor。要换盘符，点“浏览”。

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

[Code]
function IsAllowedInstallChar(C: Char): Boolean;
var
  Code: Integer;
begin
  { Same ranges QPT uses in check_warning_char, which also rejects spaces. }
  Code := Ord(C);
  Result := ((Code >= 45) and (Code <= 58)) or
            ((Code >= 64) and (Code <= 95)) or
            ((Code >= 97) and (Code <= 122));
end;

function IsSafeInstallDir(const Path: String): Boolean;
var
  I: Integer;
begin
  Result := Length(Path) >= 3;
  if not Result then
    Exit;
  for I := 1 to Length(Path) do
  begin
    if not IsAllowedInstallChar(Path[I]) then
    begin
      Result := False;
      Exit;
    end;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = wpSelectDir then
  begin
    if not IsSafeInstallDir(WizardDirValue) then
    begin
      MsgBox('安装目录只能使用英文字母、数字，以及 \ _ - . : 这些符号。' + #13#10 +
             '不能包含中文、空格或其他特殊字符。' + #13#10 +
             '否则第一次打开时，运行环境无法安装完成。' + #13#10#13#10 +
             '例如：C:\SubtitleExtractor' + #13#10 +
             '或：E:\SubtitleExtractor',
             mbError, MB_OK);
      Result := False;
    end;
  end;
end;

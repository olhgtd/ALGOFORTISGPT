#ifndef MyAppName
  #error "MyAppName is required"
#endif
#ifndef MyAppVersion
  #define MyAppVersion "9.0.0"
#endif
#ifndef MyAppPublisher
  #define MyAppPublisher "AlgoFortis"
#endif
#ifndef MyAppURL
  #define MyAppURL "https://example.invalid/algofortis"
#endif
#ifndef MyAppId
  #error "MyAppId is required"
#endif
#ifndef MyAppExeName
  #error "MyAppExeName is required"
#endif
#ifndef MyInstallSubdir
  #error "MyInstallSubdir is required"
#endif
#ifndef MyOutputBaseFilename
  #error "MyOutputBaseFilename is required"
#endif
#ifndef MyStageDir
  #error "MyStageDir is required"
#endif
#ifndef MySetupIconFile
  #error "MySetupIconFile is required"
#endif

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\AlgoFortis\{#MyInstallSubdir}
DefaultGroupName=AlgoFortis\{#MyInstallSubdir}
AllowNoIcons=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
OutputDir=..\installer
OutputBaseFilename={#MyOutputBaseFilename}
SetupIconFile={#MySetupIconFile}
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
DisableWelcomePage=no
DisableProgramGroupPage=yes
CloseApplications=force
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#MyStageDir}\*"; DestDir: "{app}"; Excludes: "AlgoFortis.exe"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\AlgoFortis\{#MyInstallSubdir}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\algofortis.ico"
Name: "{autoprograms}\AlgoFortis\{#MyInstallSubdir}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\algofortis.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
function IsWebView2Installed: Boolean;
var
  pv: String;
begin
  Result := RegQueryStringValue(HKEY_LOCAL_MACHINE, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', pv) or
            RegQueryStringValue(HKEY_LOCAL_MACHINE, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', pv) or
            RegQueryStringValue(HKEY_CURRENT_USER, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', pv);
  if Result and (pv = '') then Result := False;
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  if not IsWebView2Installed then
  begin
    MsgBox('Microsoft Edge WebView2 Runtime is required.', mbError, MB_OK);
    Result := False;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  if FileExists(ExpandConstant('{app}\runtime\python\python.exe')) then
    Exec(ExpandConstant('{app}\runtime\python\python.exe'), '-m dashboard.runtime.controller stop --mode LOCAL_PRIVATE', ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function PrepareToUninstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  if FileExists(ExpandConstant('{app}\runtime\python\python.exe')) then
    Exec(ExpandConstant('{app}\runtime\python\python.exe'), '-m dashboard.runtime.controller stop --mode LOCAL_PRIVATE', ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

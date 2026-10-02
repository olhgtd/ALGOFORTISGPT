#define MyAppName "AlgoFortis"
#ifndef MyAppVersion
  #define MyAppVersion "9.0.0"
#endif
#ifndef MyAppPublisher
  #define MyAppPublisher "AlgoFortis"
#endif
#ifndef MyAppURL
  #define MyAppURL "https://app.algofortis.com"
#endif
#define MyAppExeName "AlgoFortis.exe"

[Setup]
AppId={{8B58E97E-9CE0-4C3D-B27D-5EB0E66AF5F0}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
OutputDir=..\installer
OutputBaseFilename=AlgoFortis-Setup
SetupIconFile=..\..\algofortis.ico
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
Source: "..\stage\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
#ifdef WebViewBootstrapperPath
Source: "{#WebViewBootstrapperPath}"; DestDir: "{tmp}"; DestName: "MicrosoftEdgeWebview2Setup.exe"; Flags: deleteafterinstall
#endif

[Icons]
Name: "{autoprograms}\{#MyAppName}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\algofortis.ico"
Name: "{autoprograms}\{#MyAppName}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
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
  if Result and (pv = '') then
    Result := False;
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
#ifndef WebViewBootstrapperPath
  if not IsWebView2Installed then
  begin
    MsgBox('Microsoft Edge WebView2 Runtime is required. This qualification package does not bundle the runtime bootstrapper.', mbError, MB_OK);
    Result := False;
  end;
#endif
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  if FileExists(ExpandConstant('{app}\runtime\python\python.exe')) then
  begin
    Exec(ExpandConstant('{app}\runtime\python\python.exe'), '-m dashboard.runtime.controller stop --mode LOCAL_PRIVATE', ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec(ExpandConstant('{app}\runtime\python\python.exe'), '-m dashboard.runtime.controller stop --mode PRODUCTION', ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    if not IsWebView2Installed then
    begin
#ifdef WebViewBootstrapperPath
      if not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'), '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
        RaiseException('WebView2 Runtime bootstrapper could not be started.');
      if ResultCode <> 0 then
        RaiseException(Format('WebView2 Runtime bootstrapper failed with code %d.', [ResultCode]));
      if not IsWebView2Installed then
        RaiseException('WebView2 Runtime is still unavailable after bootstrapper execution.');
#else
      RaiseException('WebView2 Runtime is unavailable.');
#endif
    end;
  end;
end;

function PrepareToUninstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  if FileExists(ExpandConstant('{app}\runtime\python\python.exe')) then
  begin
    Exec(ExpandConstant('{app}\runtime\python\python.exe'), '-m dashboard.runtime.controller stop --mode LOCAL_PRIVATE', ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec(ExpandConstant('{app}\runtime\python\python.exe'), '-m dashboard.runtime.controller stop --mode PRODUCTION', ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;

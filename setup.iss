; setup.iss — ReelMaker Pro — Installateur professionnel
#define AppName      "ReelMaker Pro"
#define AppVersion   "1.0.0"
#define AppPublisher "Code No Senpaï"
#define AppURL       "https://github.com/codenosenpai/ReelMakerPro"
#define AppExeName   "ReelMakerPro.exe"
#define AppID        "{{B7A2F1C3-4D8E-4F92-BC1A-6E3D9F20A517}"

[Setup]
AppId={#AppID}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
; Dossier d'installation : C:\Program Files\ReelMaker Pro
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
; Icône de l'installateur
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\icon.ico
UninstallDisplayName={#AppName}
; Sortie
OutputDir=dist_installer
OutputBaseFilename=ReelMakerPro_Setup_{#AppVersion}
; Compression maximale
Compression=lzma2/ultra64
SolidCompression=yes
; Style moderne Windows
WizardStyle=modern
WizardResizable=no
; Demande les droits admin (UAC)
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
; Windows 64-bit uniquement
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Langue française
ShowLanguageDialog=no
; Pages de l'installateur
DisableWelcomePage=no
DisableDirPage=no
DisableProgramGroupPage=yes
DisableReadyPage=no
DisableFinishedPage=no
; Fermer l'app si déjà ouverte
CloseApplications=yes
; Infos exe
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription=Installation de {#AppName}
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
; Raccourci Bureau coché par défaut
Name: "desktopicon"; \
  Description: "Créer un raccourci sur le Bureau"; \
  GroupDescription: "Options supplémentaires :"; \
  Flags: checked

[Files]
; Tous les fichiers de l'app
Source: "dist\ReelMakerPro\*"; \
  DestDir: "{app}"; \
  Flags: ignoreversion recursesubdirs createallsubdirs
; Icône séparée pour raccourcis
Source: "icon.ico"; \
  DestDir: "{app}"; \
  Flags: ignoreversion

[Icons]
; Raccourci menu Démarrer
Name: "{group}\{#AppName}"; \
  Filename: "{app}\{#AppExeName}"; \
  IconFilename: "{app}\icon.ico"; \
  WorkingDir: "{app}"
; Désinstallation dans menu Démarrer
Name: "{group}\Désinstaller {#AppName}"; \
  Filename: "{uninstallexe}"; \
  IconFilename: "{app}\icon.ico"
; Raccourci Bureau (si coché)
Name: "{autodesktop}\{#AppName}"; \
  Filename: "{app}\{#AppExeName}"; \
  IconFilename: "{app}\icon.ico"; \
  WorkingDir: "{app}"; \
  Tasks: desktopicon

[Run]
; Proposer de lancer l'app après installation
Filename: "{app}\{#AppExeName}"; \
  Description: "Lancer {#AppName} maintenant"; \
  Flags: nowait postinstall skipifsilent unchecked; \
  WorkingDir: "{app}"

[UninstallDelete]
; Supprimer les fichiers temporaires au désinstall
Type: filesandordirs; Name: "{app}"
Type: filesandordirs; Name: "{localappdata}\ReelMakerPro"

[Registry]
; Ajouter dans Programmes et fonctionnalités Windows
Root: HKLM; \
  Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppID}_is1"; \
  ValueType: string; ValueName: "DisplayName"; \
  ValueData: "{#AppName}"; Flags: uninsdeletekey
Root: HKLM; \
  Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppID}_is1"; \
  ValueType: string; ValueName: "Publisher"; \
  ValueData: "{#AppPublisher}"
Root: HKLM; \
  Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppID}_is1"; \
  ValueType: string; ValueName: "DisplayVersion"; \
  ValueData: "{#AppVersion}"
Root: HKLM; \
  Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppID}_is1"; \
  ValueType: string; ValueName: "DisplayIcon"; \
  ValueData: "{app}\icon.ico"
Root: HKLM; \
  Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppID}_is1"; \
  ValueType: string; ValueName: "URLInfoAbout"; \
  ValueData: "{#AppURL}"

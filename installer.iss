; YouTube Downloader Installer Script
[Setup]
AppName=YouTube Downloader
AppVersion=1.0
DefaultDirName={pf}\YouTube Downloader
DefaultGroupName=YouTube Downloader
UninstallDisplayIcon={app}\run_app.exe
OutputBaseFilename=YouTubeDownloaderInstaller
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
SetupIconFile=icon.ico ; optional – only if you have one

[Files]
Source: "dist\run_app.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "tasks.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "templates\*"; DestDir: "{app}\templates"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "static\*"; DestDir: "{app}\static"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "thumbnails\*"; DestDir: "{app}\thumbnails"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\YouTube Downloader"; Filename: "{app}\run_app.exe"
Name: "{commondesktop}\YouTube Downloader"; Filename: "{app}\run_app.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

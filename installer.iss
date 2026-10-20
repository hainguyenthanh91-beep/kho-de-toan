; Bộ cài Kho Đề Toán (Inno Setup 6)
#define AppVer GetEnv("APP_VERSION")
#if AppVer == ""
  #define AppVer "1.5"
#endif

[Setup]
AppId={{9C125368-72EF-4929-AF4A-90079E2BA0D4}
AppName=Kho Đề Toán
AppVersion={#AppVer}
AppPublisher=Hai Nguyen
DefaultDirName={localappdata}\Programs\KhoDeToan
DefaultGroupName=Kho Đề Toán
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=KhoDeToan_Setup_{#AppVer}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\KhoDeToan.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Tạo biểu tượng trên màn hình (Desktop)"; GroupDescription: "Lối tắt:"

[Files]
Source: "dist\KhoDeToan\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\Kho Đề Toán"; Filename: "{app}\KhoDeToan.exe"
Name: "{autodesktop}\Kho Đề Toán"; Filename: "{app}\KhoDeToan.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\KhoDeToan.exe"; Description: "Mở Kho Đề Toán ngay"; Flags: nowait postinstall skipifsilent

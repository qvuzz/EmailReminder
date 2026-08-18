Write-Host "====================================================" -ForegroundColor Cyan
Write-Host " DANG DONG GOI UNG DUNG THANH FILE .EXE (ONE-FILE) " -ForegroundColor Yellow
Write-Host "====================================================" -ForegroundColor Cyan

# 1. Đóng ứng dụng nếu đang chạy ngầm để tránh bị khóa file (Access Denied)
Write-Host "[1/4] Dong cac tien trinh cu..." -ForegroundColor Gray
Get-Process -Name "Email_Reminder", "OutlookNotifierApp" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2

# Xóa file .exe cũ trực tiếp để tránh PermissionError
if (Test-Path "dist\Email_Reminder.exe") {
    try {
        Remove-Item -Force "dist\Email_Reminder.exe" -ErrorAction Stop
        Write-Host "  Da xoa file .exe cu." -ForegroundColor Gray
    } catch {
        Write-Host "[!] CANH BAO: Khong the xoa file .exe cu. Vui long dong ung dung truoc!" -ForegroundColor Red
        Read-Host "Nhan Enter de thu lai hoac Ctrl+C de thoat"
        Remove-Item -Force "dist\Email_Reminder.exe" -ErrorAction SilentlyContinue
    }
}

# 2. Xóa sạch thư mục build cũ
Write-Host "[2/4] Don dep thu muc build..." -ForegroundColor Gray
Remove-Item -Recurse -Force "build" -ErrorAction SilentlyContinue

# 3. Chạy PyInstaller
Write-Host "[3/4] Dang bien dich PyInstaller..." -ForegroundColor Cyan
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pyinstaller = Join-Path $scriptDir ".venv\Scripts\pyinstaller.exe"

& $pyinstaller --noconsole --onefile --clean `
    --workpath "$env:TEMP\build_email_reminder" `
    --icon="app_icon.ico" `
    --name="Email_Reminder" `
    --collect-all customtkinter `
    --collect-all llama_cpp `
    --collect-all pystray `
    --hidden-import win32timezone `
    --hidden-import win32com `
    --hidden-import pywintypes `
    --hidden-import PIL `
    --hidden-import PIL.Image `
    --add-data "app_icon.ico;." `
    --add-data "app_icon.png;." `
    app.py

if ($LASTEXITCODE -eq 0) {
    # 4. Tự động chuẩn bị thư mục models và data trong dist\
    Write-Host "[4/4] Dong bo thu muc models va data sang dist\..." -ForegroundColor Gray
    if (Test-Path "models") {
        if (-not (Test-Path "dist\models")) { New-Item -ItemType Directory -Path "dist\models" | Out-Null }
        Copy-Item -Path "models\*" -Destination "dist\models" -Recurse -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path "data\config.json") {
        if (-not (Test-Path "dist\data")) { New-Item -ItemType Directory -Path "dist\data" | Out-Null }
        Copy-Item -Path "data\config.json" -Destination "dist\data\config.json" -Force -ErrorAction SilentlyContinue
    }

    Write-Host ""
    Write-Host "====================================================" -ForegroundColor Green
    Write-Host " [SUCCESS] BUILD THANH CONG! File tai: dist\Email_Reminder.exe " -ForegroundColor Green
    Write-Host " (Da tu dong sao chep models\ va data\ sang dist\)" -ForegroundColor Green
    Write-Host "====================================================" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "====================================================" -ForegroundColor Red
    Write-Host " [ERROR] BUILD THAT BAI! Vui long kiem tra loi tren. " -ForegroundColor Red
    Write-Host "====================================================" -ForegroundColor Red
}

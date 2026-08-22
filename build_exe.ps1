Write-Host "====================================================" -ForegroundColor Cyan
Write-Host " DANG DONG GOI UNG DUNG THANH FILE .EXE (ONE-FILE) " -ForegroundColor Yellow
Write-Host "====================================================" -ForegroundColor Cyan

# 1. Đóng ứng dụng nếu đang chạy ngầm để tránh bị khóa file (Access Denied)
Write-Host "[1/4] Dong cac tien trinh cu..." -ForegroundColor Gray
Get-Process -Name "eMail_Assistant", "eMail_Smart_Assistant", "Email_Reminder", "OutlookNotifierApp" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2

# Xóa file .exe cũ trực tiếp để tránh PermissionError
@("dist\eMail_Assistant.exe", "dist\eMail_Smart_Assistant.exe", "dist\Email_Reminder.exe") | ForEach-Object {
    if (Test-Path $_) {
        Remove-Item -Force $_ -ErrorAction SilentlyContinue
    }
}

# 2. Xóa sạch thư mục build cũ
Write-Host "[2/4] Don dep thu muc build..." -ForegroundColor Gray
Remove-Item -Recurse -Force "build" -ErrorAction SilentlyContinue

# 3. Chạy PyInstaller
Write-Host "[3/4] Dang bien dich PyInstaller..." -ForegroundColor Cyan
$scriptDir = if ($MyInvocation.MyCommand.Path) { Split-Path -Parent $MyInvocation.MyCommand.Path } else { (Get-Location).Path }
$pyinstaller = Join-Path $scriptDir ".venv\Scripts\pyinstaller.exe"

& $pyinstaller --noconsole --onefile --clean `
    --workpath "$env:TEMP\build_email_assistant" `
    --icon="app_icon.ico" `
    --name="eMail_Assistant" `
    --collect-all customtkinter `
    --collect-all llama_cpp `
    --collect-all pystray `
    --hidden-import win32timezone `
    --hidden-import win32com `
    --hidden-import win32com.client `
    --hidden-import pythoncom `
    --hidden-import pywintypes `
    --hidden-import PIL `
    --hidden-import PIL.Image `
    --hidden-import imaplib `
    --hidden-import email `
    --hidden-import email.header `
    --hidden-import email.utils `
    --hidden-import security `
    --hidden-import ctypes `
    --hidden-import thread_logic `
    --hidden-import icon_assets `
    --hidden-import sqlite3 `
    --add-data "app_icon.ico;." `
    --add-data "app_icon.png;." `
    app.py

if ($LASTEXITCODE -eq 0) {
    # 4. Tự động chuẩn bị thư mục models và bảo toàn dữ liệu data trong dist\
    Write-Host "[4/4] Kiem tra va bao toan thu muc models & data trong dist\..." -ForegroundColor Gray
    if (Test-Path "models") {
        if (-not (Test-Path "dist\models")) { New-Item -ItemType Directory -Path "dist\models" | Out-Null }
        Get-ChildItem -Path "models" | ForEach-Object {
            $dest = Join-Path "dist\models" $_.Name
            if (-not (Test-Path $dest)) {
                Copy-Item -Path $_.FullName -Destination $dest -Force -ErrorAction SilentlyContinue
            }
        }
    }
    
    # Đảm bảo thư mục dist\data tồn tại và KHÔNG bao giờ ghi đè file cấu hình / CSDL của người dùng
    if (-not (Test-Path "dist\data")) { New-Item -ItemType Directory -Path "dist\data" | Out-Null }
    if (Test-Path "data") {
        Get-ChildItem -Path "data" | ForEach-Object {
            $dest = Join-Path "dist\data" $_.Name
            # Chỉ copy sang dist nếu file đó chưa tồn tại trong dist\data\
            if (-not (Test-Path $dest)) {
                Copy-Item -Path $_.FullName -Destination $dest -Force -ErrorAction SilentlyContinue
            }
        }
    }

    Write-Host ""
    Write-Host "====================================================" -ForegroundColor Green
    Write-Host " [SUCCESS] BUILD THANH CONG! File tai: dist\eMail_Assistant.exe " -ForegroundColor Green
    Write-Host " (Da tu dong sao chep models\ va data\ sang dist\)" -ForegroundColor Green
    Write-Host "====================================================" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "====================================================" -ForegroundColor Red
    Write-Host " [ERROR] BUILD THAT BAI! Vui long kiem tra loi tren. " -ForegroundColor Red
    Write-Host "====================================================" -ForegroundColor Red
}

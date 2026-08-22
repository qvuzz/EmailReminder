@echo off
echo ====================================================
echo  DANG DONG GOI UNG DUNG THANH FILE .EXE (ONE-FILE)
echo ====================================================

taskkill /F /IM Email_Reminder.exe 2>nul
taskkill /F /IM OutlookNotifierApp.exe 2>nul
timeout /t 1 /nobreak >nul

rmdir /s /q build 2>nul

call "%~dp0.venv\Scripts\activate.bat"

"%~dp0.venv\Scripts\pyinstaller.exe" --noconsole --onefile --clean ^
    --icon="app_icon.ico" ^
    --name="eMail_Assistant" ^
    --collect-all customtkinter ^
    --collect-all llama_cpp ^
    --collect-all pystray ^
    --hidden-import win32timezone ^
    --hidden-import win32com ^
    --hidden-import win32com.client ^
    --hidden-import pywintypes ^
    --hidden-import pythoncom ^
    --hidden-import PIL ^
    --hidden-import PIL.Image ^
    --hidden-import imaplib ^
    --hidden-import email ^
    --hidden-import email.header ^
    --hidden-import email.utils ^
    --hidden-import security ^
    --hidden-import ctypes ^
    --hidden-import thread_logic ^
    --hidden-import icon_assets ^
    --hidden-import sqlite3 ^
    --add-data "app_icon.ico;." ^
    --add-data "app_icon.png;." ^
    app.py

if %ERRORLEVEL% EQU 0 (
    if exist models (
        if not exist dist\models mkdir dist\models
        xcopy /s /y /q models\* dist\models\ >nul 2>nul
    )
    if exist data\config.json (
        if not exist dist\data mkdir dist\data
        copy /y data\config.json dist\data\config.json >nul 2>nul
    )
    echo.
    echo ====================================================
    echo  [SUCCESS] BUILD THANH CONG! File tai: dist\Email_Reminder.exe
    echo ====================================================
) else (
    echo.
    echo ====================================================
    echo  [ERROR] BUILD THAT BAI!
    echo ====================================================
)
pause

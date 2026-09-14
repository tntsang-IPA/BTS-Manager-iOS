@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title BTS Manager V85.60.46 - INSTALL PC
set "APP=%LOCALAPPDATA%\BTS Manager"
set "OUT=%~dp0RELEASE"
set "SRC=%OUT%\BTS_Manager_V85_60_46.exe"
set "DST=%APP%\BTS_Manager.exe"
set "TPL=%OUT%\BTS_Manager_Import_Template_V85_60_46_EMAIL.xlsx"
if not exist "%SRC%" echo [ERROR] Missing PC EXE & pause & exit /b 1
if not exist "%TPL%" echo [ERROR] Missing Email template & pause & exit /b 1
taskkill /f /im BTS_Manager.exe >nul 2>&1
if not exist "%APP%" mkdir "%APP%"
if exist "%DST%" copy /y "%DST%" "%DST%.bak_v85_60" >nul
copy /y "%SRC%" "%DST%" >nul || (echo [ERROR] Cannot update EXE & pause & exit /b 1)
copy /y "%TPL%" "%APP%\BTS_Manager_Import_Template.xlsx" >nul || (echo [ERROR] Cannot update template & pause & exit /b 1)
for /f "tokens=*" %%H in ('certutil -hashfile "%SRC%" SHA256 ^| findstr /R /V "hash CertUtil"') do if not defined H1 set "H1=%%H"
for /f "tokens=*" %%H in ('certutil -hashfile "%DST%" SHA256 ^| findstr /R /V "hash CertUtil"') do if not defined H2 set "H2=%%H"
if /I not "%H1%"=="%H2%" echo [ERROR] SHA256 mismatch & pause & exit /b 1
set "SHORTCUT_PS=%TEMP%\BTS_Manager_CreateShortcut_%RANDOM%.ps1"
>"%SHORTCUT_PS%" echo $ErrorActionPreference='Stop'
>>"%SHORTCUT_PS%" echo $desktop=[Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
>>"%SHORTCUT_PS%" echo if([string]::IsNullOrWhiteSpace($desktop)){ $desktop=Join-Path $env:USERPROFILE 'Desktop' }
>>"%SHORTCUT_PS%" echo New-Item -ItemType Directory -Force -Path $desktop ^| Out-Null
>>"%SHORTCUT_PS%" echo $lnk=Join-Path $desktop 'BTS Manager.lnk'
>>"%SHORTCUT_PS%" echo $ws=New-Object -ComObject WScript.Shell
>>"%SHORTCUT_PS%" echo $s=$ws.CreateShortcut($lnk)
>>"%SHORTCUT_PS%" echo $s.TargetPath='%DST%'
>>"%SHORTCUT_PS%" echo $s.WorkingDirectory='%APP%'
>>"%SHORTCUT_PS%" echo $s.IconLocation='%DST%,0'
>>"%SHORTCUT_PS%" echo $s.Description='BTS Manager V85.60.46'
>>"%SHORTCUT_PS%" echo $s.Save()
>>"%SHORTCUT_PS%" echo if(-not (Test-Path -LiteralPath $lnk)){ throw 'Desktop shortcut was not created' }
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SHORTCUT_PS%"
set "SHORTCUT_RC=%ERRORLEVEL%"
del /q "%SHORTCUT_PS%" >nul 2>&1
if not "%SHORTCUT_RC%"=="0" echo [WARNING] Khong tao duoc Desktop shortcut
if "%SHORTCUT_RC%"=="0" echo [OK] Desktop shortcut: BTS Manager.lnk
echo.
echo ================================================
echo CAI PC V85.60.46 THANH CONG
echo EXE: %DST%
echo TEMPLATE: %APP%\BTS_Manager_Import_Template.xlsx
echo ICON: Desktop\BTS Manager.lnk
echo ================================================
start "" "%DST%"
pause
exit /b 0

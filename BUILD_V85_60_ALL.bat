@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title BTS Manager V85.60.46 - BUILD PC + APK
set "ROOT=%CD%"
set "OUT=%ROOT%\RELEASE"
set "LOG=%OUT%\BUILD_V85_60_ALL.log"
if not exist "%OUT%" mkdir "%OUT%"
>"%LOG%" echo BTS Manager V85.60.46 - BUILD PC + APK
>>"%LOG%" echo Start: %date% %time%

echo.
echo [1/5 CHECK PYTHON]
>>"%LOG%" echo [1/5 CHECK PYTHON]
set "PY="
py -3 --version >>"%LOG%" 2>&1
if not errorlevel 1 set "PY=py -3"
if not defined PY (
  python --version >>"%LOG%" 2>&1
  if not errorlevel 1 set "PY=python"
)
if not defined PY (
  echo [ERROR] Python not available.
  >>"%LOG%" echo [ERROR] Python not available.
  goto BUILD_FAIL
)
for /f "delims=" %%V in ('%PY% --version 2^>^&1') do if not defined PYVER set "PYVER=%%V"
echo [OK] %PY% - %PYVER%
>>"%LOG%" echo [OK] %PY% - %PYVER%

echo.
echo [2/5 PREPARE PC DEPENDENCIES]
>>"%LOG%" echo [2/5 PREPARE PC DEPENDENCIES]
%PY% -m pip install --disable-pip-version-check PySide6 openpyxl pyinstaller >>"%LOG%" 2>&1
if errorlevel 1 goto BUILD_FAIL
if not exist "%ROOT%\PC\main.py" goto BUILD_FAIL

echo.
echo [2.25/5 CHECK MOBILE BUILD CONFIG]
>>"%LOG%" echo [2.25/5 CHECK MOBILE BUILD CONFIG]
set "CFG=%USERPROFILE%\.bts_manager_v85\supabase_build.env"
if exist "%CFG%" (
  for /f "usebackq tokens=1,* delims==" %%A in ("%CFG%") do (
    if /I "%%A"=="SUPABASE_URL" set "SUPABASE_URL=%%B"
    if /I "%%A"=="SUPABASE_PUBLISHABLE_KEY" set "SUPABASE_PUBLISHABLE_KEY=%%B"
  )
)
if not defined SUPABASE_URL set /p "SUPABASE_URL=Nhap SUPABASE_URL: "
if not defined SUPABASE_PUBLISHABLE_KEY set /p "SUPABASE_PUBLISHABLE_KEY=Nhap SUPABASE_PUBLISHABLE_KEY: "
if not defined SUPABASE_URL goto BUILD_FAIL
if not defined SUPABASE_PUBLISHABLE_KEY goto BUILD_FAIL
>>"%LOG%" echo [OK] Supabase build config available (values not logged).

echo.
echo [2.5/5 CHECK PC TEMPLATE EMAIL]
>>"%LOG%" echo [2.5/5 CHECK PC TEMPLATE EMAIL]
%PY% -c "from openpyxl import load_workbook; import unicodedata,re; p=r'%ROOT%\PC\BTS_Manager_Import_Template_V85_60_5_EMAIL.xlsx'; w=load_workbook(p,read_only=True,data_only=False); norm=lambda x: re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',str(x)).encode('ascii','ignore').decode().lower()); n=[x for x in w.sheetnames if norm(x)=='trambts']; assert n, 'Missing Tram BTS sheet'; s=w[n[0]]; h=[s.cell(1,c).value for c in range(1,s.max_column+1)]; assert any(norm(x)=='email' for x in h), 'Missing Email column'; w.close(); print('PC TEMPLATE EMAIL=OK | SHEET=TRAM_BTS')" >>"%LOG%" 2>&1
if errorlevel 1 goto BUILD_FAIL

echo.
echo [3/5 BUILD PC EXE]
>>"%LOG%" echo [3/5 BUILD PC EXE]
if exist "%ROOT%\build" rmdir /s /q "%ROOT%\build"
if exist "%ROOT%\dist" rmdir /s /q "%ROOT%\dist"
if exist "%ROOT%\BTS_Manager.spec" del /q "%ROOT%\BTS_Manager.spec"
%PY% -m PyInstaller --noconfirm --clean --onefile --windowed --name BTS_Manager --icon "%ROOT%\PC\BTS_Manager_Icon.ico" --collect-all PySide6 --add-data "%ROOT%\PC\BTS_Manager_Icon.ico;." --add-data "%ROOT%\PC\phat_trien_moi.png;." --add-data "%ROOT%\PC\BTS_Manager_Import_Template_V85_60_5_EMAIL.xlsx;." --add-data "%ROOT%\PC\BTS_Manager_MLL_Template.xlsx;." --add-data "%ROOT%\PC\BTS_Manager_KPI_Import_Template.xlsx;." "%ROOT%\PC\main.py" >>"%LOG%" 2>&1
if errorlevel 1 goto BUILD_FAIL
if not exist "%ROOT%\dist\BTS_Manager.exe" goto BUILD_FAIL
copy /y "%ROOT%\dist\BTS_Manager.exe" "%OUT%\BTS_Manager_V85_60_46.exe" >nul
if errorlevel 1 goto BUILD_FAIL
if not exist "%ROOT%\PC\BTS_Manager_Icon.ico" goto BUILD_FAIL
>>"%LOG%" echo [OK] PC icon bundled: BTS_Manager_Icon.ico
set "DESKTOP_PS=%TEMP%\BTS_Manager_CreateShortcut_Build_%RANDOM%.ps1"
>"%DESKTOP_PS%" echo $ErrorActionPreference='Stop'
>>"%DESKTOP_PS%" echo $desktop=[Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
>>"%DESKTOP_PS%" echo if([string]::IsNullOrWhiteSpace($desktop)){ $desktop=Join-Path $env:USERPROFILE 'Desktop' }
>>"%DESKTOP_PS%" echo New-Item -ItemType Directory -Force -Path $desktop ^| Out-Null
>>"%DESKTOP_PS%" echo $target=(Resolve-Path '%OUT%\BTS_Manager_V85_60_46.exe').Path
>>"%DESKTOP_PS%" echo $lnk=Join-Path $desktop 'BTS Manager.lnk'
>>"%DESKTOP_PS%" echo $ws=New-Object -ComObject WScript.Shell
>>"%DESKTOP_PS%" echo $s=$ws.CreateShortcut($lnk)
>>"%DESKTOP_PS%" echo $s.TargetPath=$target
>>"%DESKTOP_PS%" echo $s.WorkingDirectory=(Split-Path $target)
>>"%DESKTOP_PS%" echo $s.IconLocation=$target+',0'
>>"%DESKTOP_PS%" echo $s.Description='BTS Manager V85.60.46'
>>"%DESKTOP_PS%" echo $s.Save()
>>"%DESKTOP_PS%" echo if(-not (Test-Path -LiteralPath $lnk)){ throw 'Desktop shortcut was not created' }
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%DESKTOP_PS%" >>"%LOG%" 2>&1
if errorlevel 1 goto BUILD_FAIL
del /q "%DESKTOP_PS%" >nul 2>&1
>>"%LOG%" echo [OK] Desktop shortcut created: BTS Manager.lnk


echo.
echo [4/5 BUILD MOBILE APK]
>>"%LOG%" echo [4/5 BUILD MOBILE APK]
echo [INFO] Flutter output will be shown live below.
if not exist "%ROOT%\Mobile\build_apk.bat" goto BUILD_FAIL
rem SIGNER PRECHECK: only verify that the EXISTING signer files are present.
rem Do not require keytool.exe here; some Android Studio JBR installations provide java.exe without keytool.exe.
set "SIGN_DIR=%USERPROFILE%\.bts_manager_v83"
set "SIGN_KEY=%SIGN_DIR%\release-key.jks"
set "SIGN_PASSFILE=%SIGN_DIR%\signing_password.txt"
if not exist "%SIGN_KEY%" (
  >>"%LOG%" echo [SIGNER ERROR] Missing existing release-key.jks: %SIGN_KEY%
  echo [ERROR] Missing existing release signer. Build stopped before Mobile Gradle.
  goto BUILD_FAIL
)
if not exist "%SIGN_PASSFILE%" (
  >>"%LOG%" echo [SIGNER ERROR] Missing signing_password.txt: %SIGN_PASSFILE%
  echo [ERROR] Missing existing signing password. Build stopped before Mobile Gradle.
  goto BUILD_FAIL
)
>>"%LOG%" echo [SIGNER] Existing release-key.jks and signing password file found. Alias is locked in Mobile build script.

del /q "%ROOT%\Mobile\build_apk_log.txt" >nul 2>&1
if exist "%ROOT%\Mobile\build_apk_log.txt" del /q "%ROOT%\Mobile\build_apk_log.txt" >nul 2>&1
call "%ROOT%\Mobile\build_apk.bat"
set "MOBILE_RC=%ERRORLEVEL%"
if exist "%ROOT%\Mobile\build_apk_log.txt" (
  >>"%LOG%" echo.
  >>"%LOG%" echo ================= MOBILE BUILD LOG =================
  type "%ROOT%\Mobile\build_apk_log.txt" >>"%LOG%"
  >>"%LOG%" echo =============== END MOBILE BUILD LOG ===============
) else (
  >>"%LOG%" echo [ERROR] Mobile build did not produce build_apk_log.txt
)
if not "%MOBILE_RC%"=="0" goto BUILD_FAIL
if not exist "%ROOT%\Mobile\build\app\outputs\flutter-apk\app-release.apk" goto BUILD_FAIL
copy /y "%ROOT%\Mobile\build\app\outputs\flutter-apk\app-release.apk" "%OUT%\BTS_Manager_Mobile_V85_60_46.apk" >nul
if errorlevel 1 goto BUILD_FAIL


echo.
echo [5/5 VERIFY + RELEASE PACKAGE]
>>"%LOG%" echo [5/5 VERIFY + RELEASE PACKAGE]
copy /y "%ROOT%\Supabase\SUPABASE_NOTIFICATION_PERMISSION_V85_60.sql" "%OUT%\" >nul
copy /y "%ROOT%\Supabase\REPAIR_MLL_ANALYSIS_SCHEMA_V85_60_13.sql" "%OUT%\" >nul
copy /y "%ROOT%\PC\BTS_Manager_Import_Template_V85_60_5_EMAIL.xlsx" "%OUT%\BTS_Manager_Import_Template_V85_60_46_EMAIL.xlsx" >nul
if not exist "%OUT%\BTS_Manager_V85_60_46.exe" goto BUILD_FAIL
if not exist "%OUT%\BTS_Manager_Mobile_V85_60_46.apk" goto BUILD_FAIL
if not exist "%OUT%\BTS_Manager_Import_Template_V85_60_46_EMAIL.xlsx" goto BUILD_FAIL
>>"%LOG%" echo PC=OK
>>"%LOG%" echo APK=OK
>>"%LOG%" echo TEMPLATE_EMAIL=OK
>>"%LOG%" echo End: %date% %time%
echo.
echo ================================================
echo V85.60.46 BUILD THANH CONG - PC + APK
echo PC : %OUT%\BTS_Manager_V85_60_46.exe
echo APK: %OUT%\BTS_Manager_Mobile_V85_60_46.apk
echo LOG: %LOG%
echo ================================================
pause
exit /b 0

:BUILD_FAIL
echo.
echo BUILD FAILED. See log:
echo %LOG%
if exist "%ROOT%\Mobile\build_apk_log.txt" (
  echo.
  echo -------- MOBILE BUILD FAILURE --------
  type "%ROOT%\Mobile\build_apk_log.txt"
  echo ------ END MOBILE BUILD FAILURE ------
)
>>"%LOG%" echo BUILD FAILED.
pause
exit /b 1

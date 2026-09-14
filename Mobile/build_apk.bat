@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "MOBILE_PHYSICAL=%~dp0"
set "PROJECT_ROOT=%~dp0.."
rem BUILD PATH FIX: force-release any stale B: SUBST mapping before reuse.
rem impellerc/shader outputs otherwise can fail to create nested paths on Windows.
rem A previous failed build may leave B: mapped; do not mistake that for a new subst failure.
subst B: /d >nul 2>&1
subst B: "%PROJECT_ROOT%" >nul 2>&1
if errorlevel 1 (
  >>"%TEMP%\bts_subst_error.txt" echo [%date% %time%] SUBST B: failed for "%PROJECT_ROOT%"
  goto FAIL_PATH
)
cd /d "B:\Mobile"
title BTS Manager Mobile V85.60.46 - ALL IN ONE RELEASE BUILD
set "LOG=B:\Mobile\build_apk_log.txt"
set "TARGET_NDK=28.2.13676358"
set "GRADLE_USER_HOME=D:\BTS_Manager_V84_0_Gradle"
set "PUB_CACHE=D:\BTS_Manager_V84_0_PubCache"

>"%LOG%" echo ==================================================
>>"%LOG%" echo BTS Manager Mobile V85.60.46 - ALL IN ONE RELEASE BUILD
>>"%LOG%" echo Start: %date% %time%
>>"%LOG%" echo ==================================================

echo [1] Checking Flutter...
where flutter >nul 2>&1
if errorlevel 1 goto FAIL_FLUTTER
for /f "tokens=1-5" %%A in ('flutter --version 2^>^&1') do (
  if "%%A"=="Flutter" if not defined FLUTTER_LINE set "FLUTTER_LINE=%%A %%B %%C %%D %%E"
)
if not defined FLUTTER_LINE set "FLUTTER_LINE=Flutter detected"
>>"%LOG%" echo [OK] %FLUTTER_LINE%
echo [OK] Flutter detected.

echo [2] Enter Supabase credentials.
if not defined SUPABASE_URL echo [ERROR] SUPABASE_URL is missing. Set it in the parent build or user config.
if not defined SUPABASE_PUBLISHABLE_KEY echo [ERROR] SUPABASE_PUBLISHABLE_KEY is missing. Set it in the parent build or user config.
if not defined SUPABASE_URL goto FAIL_SUPABASE
if not defined SUPABASE_PUBLISHABLE_KEY goto FAIL_SUPABASE
>>"%LOG%" echo [OK] Supabase credentials supplied.
echo [FLOW] Supabase credentials accepted. Continuing...

echo [3] Checking Android SDK...
if not defined ANDROID_SDK_ROOT if defined ANDROID_HOME set "ANDROID_SDK_ROOT=%ANDROID_HOME%"
if not defined ANDROID_SDK_ROOT set "ANDROID_SDK_ROOT=%LOCALAPPDATA%\Android\Sdk"
if not exist "%ANDROID_SDK_ROOT%\platform-tools" goto FAIL_SDK
>>"%LOG%" echo [OK] Android SDK: %ANDROID_SDK_ROOT%

echo [4] Checking Java 17+...
set "JAVA_EXE="
if defined JAVA_HOME if exist "%JAVA_HOME%\bin\java.exe" set "JAVA_EXE=%JAVA_HOME%\bin\java.exe"
if not defined JAVA_EXE if exist "%PROGRAMFILES%\Android\Android Studio\jbr\bin\java.exe" set "JAVA_EXE=%PROGRAMFILES%\Android\Android Studio\jbr\bin\java.exe"
if not defined JAVA_EXE for /f "delims=" %%J in ('where java 2^>nul') do if not defined JAVA_EXE set "JAVA_EXE=%%J"
if not defined JAVA_EXE goto FAIL_JAVA
set "JV=%TEMP%\bts_java_%RANDOM%.txt"
"%JAVA_EXE%" -version >nul 2>"%JV%"
set "JAVA_VER="
for /f "tokens=3" %%V in ('findstr /i /c:"version" "%JV%"') do if not defined JAVA_VER set "JAVA_VER=%%~V"
del /q "%JV%" >nul 2>&1
if not defined JAVA_VER goto FAIL_JAVA
for /f "tokens=1 delims=." %%M in ("%JAVA_VER%") do set "JAVA_MAJOR=%%M"
if "%JAVA_MAJOR%"=="1" goto FAIL_JAVA
if %JAVA_MAJOR% LSS 17 goto FAIL_JAVA
set "JAVA_HOME=%JAVA_EXE:\bin\java.exe=%"
>>"%LOG%" echo [JAVA] Raw version: %JAVA_VER%
>>"%LOG%" echo [OK] Java %JAVA_MAJOR%: %JAVA_EXE%

echo [5] Checking SDK Platform 36 and NDK...
if not exist "%ANDROID_SDK_ROOT%\platforms\android-36\android.jar" goto FAIL_PLATFORM
if not exist "%ANDROID_SDK_ROOT%\ndk\%TARGET_NDK%\source.properties" goto FAIL_NDK
>>"%LOG%" echo [OK] Android SDK Platform 36 exists.
>>"%LOG%" echo [OK] NDK %TARGET_NDK% is installed and valid.

echo [6] Checking storage...
for /f %%F in ('powershell -NoProfile -Command "[math]::Floor((Get-PSDrive C).Free/1GB)"') do set "CFREE=%%F"
for /f %%F in ('powershell -NoProfile -Command "[math]::Floor((Get-PSDrive D).Free/1GB)"') do set "DFREE=%%F"
>>"%LOG%" echo [STORAGE] C free: %CFREE% GB, D free: %DFREE% GB
if not defined CFREE set "CFREE=0"
if not defined DFREE set "DFREE=0"
if %CFREE% LSS 5 goto FAIL_STORAGE_C
if %DFREE% LSS 10 goto FAIL_STORAGE_D

if not exist "%GRADLE_USER_HOME%" mkdir "%GRADLE_USER_HOME%"
if not exist "%PUB_CACHE%" mkdir "%PUB_CACHE%"
>>"%LOG%" echo [OK] GRADLE_USER_HOME=%GRADLE_USER_HOME%
>>"%LOG%" echo [OK] PUB_CACHE=%PUB_CACHE%
>>"%LOG%" echo [OK] Low-memory Gradle mode: Xmx2G, MaxMetaspace512M, workers=2, daemon=false

echo [7] Checking project...
if not exist "%CD%\pubspec.yaml" goto FAIL_PROJECT
if not exist "%CD%\android\app\build.gradle" goto FAIL_PROJECT
>>"%LOG%" echo [OK] Project preflight passed.

echo [8] Preparing release signing...
set "SIGN_DIR=%USERPROFILE%\.bts_manager_v83"
set "KEYSTORE=%SIGN_DIR%\release-key.jks"
set "PASSFILE=%SIGN_DIR%\signing_password.txt"
set "KEY_PROPS=%CD%\android\key.properties"
if not exist "%KEYSTORE%" goto FAIL_SIGN_MISSING_KEY
if not exist "%PASSFILE%" goto FAIL_SIGN_MISSING_PASS
set /p "SIGN_PASS="<"%PASSFILE%"
if not defined SIGN_PASS goto FAIL_SIGN_MISSING_PASS
rem SIGNER LOCK: preserve the release identity used by the existing installed app.
rem The original project configuration uses alias btsmanager. Never generate a new key.
set "KEYSTORE_GRADLE=%KEYSTORE:\=/%"
>"%KEY_PROPS%" echo storePassword=%SIGN_PASS%
>>"%KEY_PROPS%" echo keyPassword=%SIGN_PASS%
>>"%KEY_PROPS%" echo keyAlias=btsmanager
>>"%KEY_PROPS%" echo storeFile=%KEYSTORE_GRADLE%
if not exist "%KEY_PROPS%" goto FAIL_SIGN
findstr /i /c:"storePassword=" /c:"keyPassword=" /c:"keyAlias=btsmanager" /c:"storeFile=" "%KEY_PROPS%" >nul 2>&1
if errorlevel 1 goto FAIL_SIGN
>>"%LOG%" echo [SIGNER] Keystore exists: %KEYSTORE%
>>"%LOG%" echo [SIGNER] Alias locked to: btsmanager
>>"%LOG%" echo [SIGNER] key.properties generated successfully.
>>"%LOG%" echo [OK] Release signing configuration ready; existing signer preserved.

echo [9/12] flutter pub get...
call flutter pub get >>"%LOG%" 2>&1
if errorlevel 1 goto FAIL_BUILD

echo [10/12] flutter analyze...
call flutter analyze >>"%LOG%" 2>&1
if errorlevel 1 >>"%LOG%" echo [WARNING] flutter analyze returned nonzero; continuing.

echo [11/12] flutter clean...
call flutter clean >>"%LOG%" 2>&1
if errorlevel 1 goto FAIL_BUILD

echo [12/12] Building signed release APK (LOW MEMORY MODE)...
echo [INFO] Build output is live. If Gradle fails, the exact error is saved in build_apk_log.txt.
set "GRADLE_USER_HOME=%GRADLE_USER_HOME%"
set "PUB_CACHE=%PUB_CACHE%"
call flutter build apk --release --dart-define=SUPABASE_URL="%SUPABASE_URL%" --dart-define=SUPABASE_PUBLISHABLE_KEY="%SUPABASE_PUBLISHABLE_KEY%"
set "BUILD_RC=%ERRORLEVEL%"
>>"%LOG%" echo [FLUTTER] Build command exit code: %BUILD_RC%
if not "%BUILD_RC%"=="0" goto FAIL_BUILD
set "APK=%CD%\build\app\outputs\flutter-apk\app-release.apk"
if not exist "%APK%" goto FAIL_APK
set "APKSIGNER="
for /f "delims=" %%T in ('dir /b /ad /o-n "%ANDROID_SDK_ROOT%\build-tools\*" 2^>nul') do if not defined APKSIGNER if exist "%ANDROID_SDK_ROOT%\build-tools\%%T\apksigner.bat" set "APKSIGNER=%ANDROID_SDK_ROOT%\build-tools\%%T\apksigner.bat"
if not defined APKSIGNER goto FAIL_SIGNER
rem Validate ZIP/APK readability before reporting success.
"%JAVA_HOME%\bin\jar.exe" tf "%APK%" >nul 2>&1
if errorlevel 1 goto FAIL_APK_CORRUPT
set "ZIPALIGN="
for /f "delims=" %%T in ('dir /b /ad /o-n "%ANDROID_SDK_ROOT%\build-tools\*" 2^>nul') do if not defined ZIPALIGN if exist "%ANDROID_SDK_ROOT%\build-tools\%%T\zipalign.exe" set "ZIPALIGN=%ANDROID_SDK_ROOT%\build-tools\%%T\zipalign.exe"
if not defined ZIPALIGN goto FAIL_ZIPALIGN
call "%ZIPALIGN%" -c -v 4 "%APK%" >>"%LOG%" 2>&1
if errorlevel 1 goto FAIL_ZIPALIGN_CHECK
call "%APKSIGNER%" verify --verbose "%APK%" >>"%LOG%" 2>&1
if errorlevel 1 goto FAIL_SIGNATURE
>>"%LOG%" echo [VERIFY] APK zip integrity: OK
>>"%LOG%" echo [VERIFY] APK zipalign: OK
>>"%LOG%" echo [VERIFY] APK signature: OK
>>"%LOG%" echo [SUCCESS] APK=%APK%
>>"%LOG%" echo End: %date% %time%
echo.
echo ==================================================
echo BUILD THANH CONG - SIGNED APK
echo APK: %APK%
echo LOG: %LOG%
echo ==================================================
pause
subst B: /d >nul 2>&1
exit /b 0

:FAIL_PATH
call :FAIL "Khong the tao duong dan build ngan B:. Da thu go B: cu va tao lai; xem SUBST/drive B trong Windows neu van loi."
exit /b 1
:FAIL_FLUTTER
call :FAIL "Khong tim thay Flutter trong PATH."
exit /b 1
:FAIL_SUPABASE
call :FAIL "Thieu SUPABASE_URL hoac SUPABASE_PUBLISHABLE_KEY."
exit /b 1
:FAIL_SDK
call :FAIL "Khong tim thay Android SDK."
exit /b 1
:FAIL_JAVA
call :FAIL "Khong tim thay JDK 17+ hoac khong doc duoc Java."
exit /b 1
:FAIL_PLATFORM
call :FAIL "Thieu Android SDK Platform 36."
exit /b 1
:FAIL_NDK
call :FAIL "Thieu NDK 28.2.13676358."
exit /b 1
:FAIL_STORAGE_C
call :FAIL "O C: can it nhat 5 GB trong khi build."
exit /b 1
:FAIL_STORAGE_D
call :FAIL "O D: can it nhat 10 GB trong khi build."
exit /b 1
:FAIL_PROJECT
call :FAIL "Thieu pubspec.yaml hoac android\app\build.gradle."
exit /b 1

:FAIL_SIGN_MISSING_KEY
call :FAIL "Khong tim thay release-key.jks cu. Khong tu tao key moi de tranh loi Android tu choi cap nhat."
exit /b 1
:FAIL_SIGN_MISSING_PASS
call :FAIL "Khong tim thay signing_password cu. Khong the xac minh dung chu ky cua app da cai."
exit /b 1
:FAIL_APK_CORRUPT
call :FAIL "APK tao ra nhung file bi hong/khong doc duoc."
exit /b 1
:FAIL_ZIPALIGN
call :FAIL "Khong tim thay zipalign trong Android SDK."
exit /b 1
:FAIL_ZIPALIGN_CHECK
call :FAIL "APK chua duoc zipalign hop le."
exit /b 1
:FAIL_SIGN
call :FAIL "Khong tao/nap duoc release keystore."
exit /b 1
:FAIL_BUILD
call :FAIL "Flutter build that bai. Xem log de lay loi goc."
exit /b 1
:FAIL_APK
call :FAIL "Khong tim thay app-release.apk."
exit /b 1
:FAIL_SIGNER
call :FAIL "Khong tim thay apksigner."
exit /b 1
:FAIL_SIGNATURE
call :FAIL "APK tao ra nhung chu ky khong hop le."
exit /b 1
:FAIL
echo.
echo ==================================================
echo BUILD FAILED
echo %~1
echo LOG: %LOG%
echo ==================================================
>>"%LOG%" echo [FAILED] %~1
>>"%LOG%" echo End: %date% %time%
pause
subst B: /d >nul 2>&1
exit /b 1

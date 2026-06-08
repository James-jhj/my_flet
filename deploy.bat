@echo off
chcp 65001 >nul

echo ========================================
echo Git Auto Deploy Script with APK Download
echo ========================================
echo.

cd /d D:\my_flet
echo Current directory: %cd%
echo.

if not exist main.py (
    echo ERROR: main.py not found
    pause
    exit /b 1
)

echo Reading version from main.py...
echo.

python -c "import re; f=open('main.py','r',encoding='utf-8'); c=f.read(); f.close(); v_match=re.search(r'APP_VERSION\s*=\s*\"([\d\.]+)\"', c); vc_match=re.search(r'APP_VERSION_CODE\s*=\s*(\d+)', c); v=v_match.group(1); vc=int(vc_match.group(1)); parts=v.split('.'); newv=f\"{parts[0]}.{parts[1]}.{int(parts[2])+1}\"; newvc=vc+1; c=re.sub(r'APP_VERSION\s*=\s*\"[\d\.]+\"', f'APP_VERSION = \"{newv}\"', c); c=re.sub(r'APP_VERSION_CODE\s*=\s*\d+', f'APP_VERSION_CODE = {newvc}', c); f=open('main.py','w',encoding='utf-8'); f.write(c); f.close(); print(f'CURRENT_VERSION={v}'); print(f'NEW_VERSION={newv}'); print(f'NEW_VERSION_CODE={newvc}')" > version.txt

if errorlevel 1 (
    echo ERROR: Failed to update version
    type version.txt
    pause
    exit /b 1
)

for /f "tokens=2 delims==" %%i in ('findstr "CURRENT_VERSION" version.txt') do set CURRENT_VERSION=%%i
REM 方法3：直接用 set 命令读取
for /f "delims=" %%i in ('findstr "NEW_VERSION" version.txt') do set "%%i"
for /f "tokens=2 delims==" %%i in ('findstr "NEW_VERSION_CODE" version.txt') do set NEW_VERSION_CODE=%%i

del version.txt

echo Current version: %CURRENT_VERSION%
echo New version: %NEW_VERSION%
echo New version code: %NEW_VERSION_CODE%
echo.

echo Start add file at time: %date% %time%
git add .
echo End add file at time: %date% %time%

echo Start commit file to github at time: %date% %time%
git commit -m "release: v%NEW_VERSION%"
echo End commit file to github at time: %date% %time%

echo.
echo Pushing to remote...

set MAX_RETRIES=1000
set RETRY_COUNT=0

:retry_push
set /a RETRY_COUNT+=1
echo Attempt %RETRY_COUNT% of %MAX_RETRIES%...

echo Start push file to github at time: %date% %time%
git push -f origin main
echo End push file to github at time: %date% %time%
if errorlevel 1 (
    if %RETRY_COUNT% lss %MAX_RETRIES% (
        echo Push failed Waiting 1 minute before retry...
        timeout /t 60 /nobreak
        goto retry_push
    ) else (
        echo ERROR: Git push failed
        pause
        exit /b 1
    )
)


REM 等待 APK 构建
echo Waiting 12 minutes for GitHub Actions to build APK...
echo Start build apk file at time: %date% %time%
timeout /t 720 /nobreak
echo End build apk file at time: %date% %time%
echo.

REM 下载 APK
set DOWNLOAD_DIR=D:\apk_download
if not exist "%DOWNLOAD_DIR%" mkdir "%DOWNLOAD_DIR%"

set APK_NAME=event_reminder_v%NEW_VERSION%
echo Looking for APK: %APK_NAME%
echo.

set MAX_RETRIES=1000
set RETRY_COUNT=0

:retry_download
set /a RETRY_COUNT+=1
echo Attempt %RETRY_COUNT% of %MAX_RETRIES%...

REM 获取运行 ID
gh run list --limit 30 --json databaseId,displayTitle > runs.json 2>nul

REM 使用 PowerShell 解析并抑制错误信息
for /f "delims=" %%i in ('powershell -Command "$ErrorActionPreference='SilentlyContinue'; $json = Get-Content runs.json -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json -ErrorAction SilentlyContinue; $run = $json | Where-Object { $_.displayTitle -eq 'release: v%NEW_VERSION%' }; if ($run) { $run.databaseId }" 2^>nul') do (
    set RUN_ID=%%i
)

del runs.json 2>nul

if defined RUN_ID (
    goto :found_run
)

echo No run found for release: v%NEW_VERSION%
if %RETRY_COUNT% lss %MAX_RETRIES% (
    echo Waiting 20 seconds before retry...
    timeout /t 20 /nobreak >nul
    goto retry_download
) else (
    echo ERROR: No matching GitHub Action run found after %MAX_RETRIES% attempts
    pause
    exit /b 1
)

:found_run
echo Found run ID: %RUN_ID%
echo Downloading %APK_NAME% to %DOWNLOAD_DIR%

echo Start download %APK_NAME% at time: %date% %time%
gh run download %RUN_ID% --name %APK_NAME% --dir "%DOWNLOAD_DIR%"
echo End download %APK_NAME% at time: %date% %time%

REM ========== 重命名 APK 文件 ==========
echo.
echo Renaming APK file...

set OLD_APK=%DOWNLOAD_DIR%\event_reminder.apk
set NEW_APK=%DOWNLOAD_DIR%\event_reminder_v%NEW_VERSION%.apk

if exist "%OLD_APK%" (
    ren "%OLD_APK%" "event_reminder_v%NEW_VERSION%.apk"
    if errorlevel 1 (
        echo WARNING: Failed to rename
    ) else (
        echo Renamed to: event_reminder_v%NEW_VERSION%.apk
        set APK_NAME=event_reminder_v%NEW_VERSION%.apk
    )
) else (
    echo WARNING: event_reminder.apk not found
    echo Looking for any APK file...
    for /r "%DOWNLOAD_DIR%" %%f in (*.apk) do (
        echo Found: %%f
        ren "%%f" "event_reminder_v%NEW_VERSION%.apk" 2>nul
    )
)

echo.
echo ========================================
echo ALL TASKS COMPLETED SUCCESSFULLY!
echo   Version: v%NEW_VERSION%
echo   Version Code: %NEW_VERSION_CODE%
echo   APK Location: %DOWNLOAD_DIR%\event_reminder_v%NEW_VERSION%.apk
echo ========================================
echo.

REM ========== 打开 APK 所在目录 ==========
echo Opening APK download directory...
start "" "%DOWNLOAD_DIR%"

pause
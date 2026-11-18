@echo off
setlocal EnableExtensions EnableDelayedExpansion
pushd "%~dp0" >nul 2>&1 || exit /b 1
title BioIntel Shiro AI Setup
if not defined LOCALAPPDATA set "LOCALAPPDATA=%USERPROFILE%\AppData\Local"
set "SHIRO_DATA=%LOCALAPPDATA%\BioIntelAI\UserData\shiro"
if not exist "%SHIRO_DATA%" mkdir "%SHIRO_DATA%" >nul 2>&1

:MENU
cls
echo ============================================================
echo                  BIOINTEL SHIRO AI SETUP
echo ============================================================
echo.
echo  1. Install or detect Shiro Local Intelligence runtime
echo  2. Install balanced local chat model (recommended)
echo  3. Install local vision model
echo  4. Install local deep-reasoning model
echo  5. Install local embedding model
echo  6. Install all recommended local models
echo  7. Verify Shiro AI readiness
echo  8. Open Shiro AI provider setup guide
echo  9. Exit
echo.
echo Models are optional, free to use locally, and may require several GB.
echo Cloud API keys are entered only inside Shiro AI Setup in the app.
echo.
set /p CHOICE=Choose 1-9: 
if "%CHOICE%"=="1" goto INSTALL_RUNTIME
if "%CHOICE%"=="2" goto CHAT_MODEL
if "%CHOICE%"=="3" goto VISION_MODEL
if "%CHOICE%"=="4" goto REASONING_MODEL
if "%CHOICE%"=="5" goto EMBEDDING_MODEL
if "%CHOICE%"=="6" goto ALL_MODELS
if "%CHOICE%"=="7" goto VERIFY
if "%CHOICE%"=="8" goto GUIDE
if "%CHOICE%"=="9" goto DONE
goto MENU

:INSTALL_RUNTIME
where ollama.exe >nul 2>&1
if not errorlevel 1 (
  echo Shiro Local Intelligence runtime is already installed.
  ollama --version
  pause
  goto MENU
)
where winget.exe >nul 2>&1
if errorlevel 1 (
  echo Automatic runtime installation requires Windows Package Manager.
  echo Install the local runtime from its official Windows installer, then run this setup again.
  pause
  goto MENU
)
echo Installing the local runtime...
winget install --id Ollama.Ollama -e --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
  echo Runtime installation did not complete. Review the winget output above.
  pause
  goto MENU
)
echo Runtime installed. A Windows sign-out or terminal restart may be required.
pause
goto MENU

:ENSURE_RUNTIME
where ollama.exe >nul 2>&1
if errorlevel 1 (
  echo ERROR: Shiro Local Intelligence runtime is not installed.
  echo Choose option 1 first.
  exit /b 1
)
exit /b 0

:CHAT_MODEL
call :ENSURE_RUNTIME || (pause & goto MENU)
ollama pull qwen3:4b
pause
goto MENU

:VISION_MODEL
call :ENSURE_RUNTIME || (pause & goto MENU)
ollama pull gemma3:4b
pause
goto MENU

:REASONING_MODEL
call :ENSURE_RUNTIME || (pause & goto MENU)
ollama pull deepseek-r1:8b
pause
goto MENU

:EMBEDDING_MODEL
call :ENSURE_RUNTIME || (pause & goto MENU)
ollama pull embeddinggemma
pause
goto MENU

:ALL_MODELS
call :ENSURE_RUNTIME || (pause & goto MENU)
call :WRITE_SETTINGS
for %%M in (qwen3:4b gemma3:4b deepseek-r1:8b embeddinggemma) do (
  echo.
  echo Installing %%M...
  ollama pull %%M
  if errorlevel 1 echo WARNING: %%M did not complete.
)
pause
goto MENU

:WRITE_SETTINGS
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p='%SHIRO_DATA%\provider-settings.json'; $o=[ordered]@{mode='auto';cloud_consent_saved=$false;cloud_eligibility_confirmed=$false;local_model='qwen3:4b';local_vision_model='gemma3:4b';local_reasoning_model='deepseek-r1:8b';local_embedding_model='embeddinggemma';gemini_model='gemini-3.1-flash-lite';openrouter_model='openrouter/free';max_history_messages=20;max_output_tokens=2048;temperature=0.2;allow_cloud_fallback=$false;updated_at=(Get-Date).ToUniversalTime().ToString('o')}; $json=$o|ConvertTo-Json; [IO.File]::WriteAllText($p,$json,(New-Object Text.UTF8Encoding($false)))"
exit /b 0

:VERIFY
call :WRITE_SETTINGS
where ollama.exe >nul 2>&1
if errorlevel 1 (
  echo Local runtime: SETUP REQUIRED
) else (
  echo Local runtime: DETECTED
  ollama --version
  echo.
  echo Installed models:
  ollama list
  powershell -NoProfile -Command "try { $r=Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5; Write-Host 'Local API: READY'; Write-Host ('Models detected: ' + $r.models.Count) } catch { Write-Host 'Local API: NOT READY'; Write-Host $_.Exception.Message }"
)
echo.
echo Settings file: %SHIRO_DATA%\provider-settings.json
echo Online and backup keys are checked inside the Shiro AI app.
pause
goto MENU

:GUIDE
if exist "%CD%\SHIRO_AI_SETUP_GUIDE.md" (
  start "" notepad.exe "%CD%\SHIRO_AI_SETUP_GUIDE.md"
) else (
  echo Guide file is missing.
  pause
)
goto MENU

:DONE
popd
exit /b 0

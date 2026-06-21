@echo off
REM ================================================================
REM   CAINE PARTY SERVER  --  double-click THIS on the party laptop
REM   and leave the window open for the whole party.
REM
REM   One app, three modes (opens http://localhost:8765 in your browser):
REM      /guide    Bubble's Party Guide   (your tablet)
REM      /console  Caine's Console        (Nora's iPad)
REM      /studio   Voice Studio           (tune / regenerate voices)
REM
REM   The iPad + tablet connect over WiFi to  http://<this-laptop-ip>:8765/
REM   (the window prints the exact address). For "Talk to Caine" (mic),
REM   open the https://...:8766/console address it also prints.
REM ================================================================
cd /d "%~dp0caine-voice"
set PYTHONIOENCODING=utf-8
echo ============================================================
echo    CAINE PARTY SERVER
echo.
echo    IMPORTANT: if Windows pops a security/firewall dialog,
echo    click  ALLOW ACCESS  and TICK  "Private networks"
echo    (so Nora's iPad + your tablet on the WiFi can connect).
echo.
echo    The lines below show the exact address to open on each
echo    device. Leave this window open during the whole party.
echo ============================================================
echo.
REM One-time, best-effort: deps for "Talk to Caine" (mic STT, HTTPS cert, audio decode).
REM Already installed? pip says "already satisfied" instantly. Offline? --timeout/--retries
REM make it fail fast (a few seconds) instead of hanging on a connection timeout.
echo    Checking 'Talk to Caine' helpers (first run only, needs internet)...
py -m pip install --quiet --disable-pip-version-check --timeout 5 --retries 0 cryptography faster-whisper imageio-ffmpeg >nul 2>nul
echo.
py caine_studio_web.py
if errorlevel 1 (
  echo.
  echo Something went wrong. Make sure Python is installed ^(the "py" launcher^).
  pause
)

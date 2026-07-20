@echo off
REM Проверяет /health и перезапускает бота, если не отвечает.
REM Запускается планировщиком раз в 2 минуты (задача TravelBotWatchdog).
REM Причина: uvicorn запущен через start-bot.vbs как обычный процесс без
REM авто-рестарта — если он падает на уровне ОС (не Python-исключение,
REM те логируются), поднять его некому. Наблюдалось падение ~2026-07-10.

curl -s -o nul --max-time 10 http://localhost:8000/health
if %errorlevel%==0 goto :ok

echo [%date% %time%] health check failed, restarting bot >> "C:\travel-agent-bot\logs\watchdog.log"
schtasks /run /tn RestartTravelBot
goto :eof

:ok
exit /b 0

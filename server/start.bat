@echo off
chcp 65001 >nul
title 梦幻神域 - 本地服务端
REM ============================================================
REM  一键启动本地服务端（更新服 HTTP:80 + 游戏服 TCP:9001）
REM  用法：双击运行；关闭窗口即停止服务
REM ============================================================
cd /d "%~dp0"

set PY=C:\Users\19136\.workbuddy\binaries\python\versions\3.13.12\python.exe
if not exist "%PY%" set PY=python

echo ============================================================
echo  梦幻神域 本地服务端
echo    更新服 (HTTP)  : 0.0.0.0:80
echo    游戏服 (TCP)   : 0.0.0.0:9001
echo    存档文件       : server\save.json
echo ============================================================
echo.

REM 结束可能残留的旧进程（只清理本项目启动的两个 python）
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r ":80 .*:9001 .*LISTENING"') do (
    tasklist /FI "PID eq %%p" 2>nul | findstr /i python.exe >nul && taskkill /PID %%p /F >nul 2>&1
)

echo [1/2] 启动更新服 (HTTP:80) ...
start "MHSY-UpdateServer" /min "%PY%" update_server.py

echo [2/2] 启动游戏服 (TCP:9001) ...
start "MHSY-GameServer" /min "%PY%" game_server.py --port 9001 --serial 1 --dyn-id 1 --born-pos 0,0,0

timeout /t 2 >nul
netstat -ano | findstr /r ":80 .*:9001 " | findstr LISTENING

echo.
echo 启动完成。日志见 server\logs\
echo 模拟器 hosts 劫持若失效，请运行:
echo    "%PY%" setup_mumu_hosts.py --host 192.168.0.12 --port 7555
echo.
pause

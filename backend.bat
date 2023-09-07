@echo off
chcp 65001 > nul

echo 检测8000端口是否被使用
netstat -ano | findstr "LISTENING" | findstr ":8000" > nul

if %errorlevel% equ 0 (
  rem 如果端口被占用，则关闭占用端口的进程
  echo 端口8000已被占用。终止占用端口的进程...
  for /f "tokens=5" %%a in ('netstat -ano ^| findstr "LISTENING" ^| findstr ":8000"') do (
    taskkill /f /pid %%a
  )
)

echo 激活虚拟环境...
call backend\venv\Scripts\activate.bat

echo 启动应用程序
start /b backend\venv\Scripts\python.exe backend\app\main.py > fastapi.log 2>&1

echo 如果日志文件夹不存在，则创建
if not exist log mkdir log



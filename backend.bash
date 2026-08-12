#!/bin/bash

# 检测8522端口是否被使用
check_port() {
  echo "Checking if port 8522 is in use..."
  if lsof -Pi :8522 -sTCP:LISTEN -t >/dev/null ; then
    echo "Port 8522 is already in use. Closing the application..."
    kill $(lsof -t -i:8522)
  fi
}

# 激活 uv venv。uv 创建的 venv 的 bin/ 里可能没有 activate 脚本（实测过），
# 但启动用的是 .venv/bin/python 直连（见 start_application），activate 只是
# 让后续 shell 命令能解析到 venv 里的工具——有则 source，没有就静默跳过，
# 不报 "No such file or directory" 噪音。
activate_venv() {
  if [ -f ".venv/bin/activate" ]; then
    echo "Activating uv virtual environment..."
    source .venv/bin/activate
  else
    echo "No activate script in .venv/bin (uv venv layout); using direct .venv/bin/python."
  fi
}

# 启动应用程序并守护进程
start_application() {
  echo "Starting the application with process guardian..."
  nohup bash -c "while true; do .venv/bin/python backend/app/main.py; echo 'Application crashed. Restarting...'; sleep 1; done" > fastapi.log 2>&1 &
}

# 执行检测端口、激活环境和启动应用程序的操作
check_port

if [ ! -d ".venv" ]; then
    echo "Virtual environment not found. Running uv sync..."
    uv sync
fi

if [ ! -f "backend/.env" ]; then
    echo "Copying .env.example to .env..."
    cp backend/.env.example backend/.env
fi

activate_venv
start_application

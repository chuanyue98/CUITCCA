#!/bin/bash

# 检测8000端口是否被使用
check_port() {
  echo "Checking if port 8000 is in use..."
  if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null ; then
    echo "Port 8000 is already in use. Closing the application..."
    kill $(lsof -t -i:8000)
  fi
}

# 激活 uv venv
activate_venv() {
  echo "Activating uv virtual environment..."
  source .venv/bin/activate
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

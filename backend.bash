#!/bin/bash

# 检测8000端口是否被使用
check_port() {
  echo "Checking if port 8000 is in use..."
  if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null ; then
    echo "Port 8000 is already in use. Closing the application..."
    kill $(lsof -t -i:8000)
  fi
}

# 激活conda环境
activate_conda() {
  echo "Activating conda environment..."
  conda activate cca
}

# 启动应用程序
start_application() {
  echo "Starting the application..."
  nohup python backend/app/main.py > fastapi.log 2>&1 &
}

# 执行检测端口、激活环境和启动应用程序的操作
check_port
activate_conda
start_application
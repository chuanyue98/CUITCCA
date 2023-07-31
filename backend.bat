rem 激活虚拟环境
call backend\venv\Scripts\activate.bat

rem 启动项目
start /b backend\venv\Scripts\python.exe backend\app\main.py > backend.log 2>&1
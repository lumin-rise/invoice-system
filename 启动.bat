@echo off
chcp 65001 >nul
cd /d %~dp0backend
echo 启动发票解析系统: http://127.0.0.1:8000 （--reload：改代码自动生效）
start "" http://127.0.0.1:8000
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

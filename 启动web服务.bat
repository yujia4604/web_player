@echo off
:: 添加路径到 PATH 环境变量
set PATH=%PATH%;.\ffmpeg\bin


.\env\python.exe server.py

pause
@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "dist\WoodFlow\WoodFlow.exe" (
  start "" "dist\WoodFlow\WoodFlow.exe"
) else if exist "dist\WoodFlow-Windows-x64\WoodFlow.bat" (
  call "dist\WoodFlow-Windows-x64\WoodFlow.bat"
) else if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m container_planner
) else (
  echo 请先解压Windows启动包，或按README.md安装开发环境。
  pause
)

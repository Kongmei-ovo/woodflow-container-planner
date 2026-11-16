#!/bin/zsh
set -e
cd "${0:A:h}"
if [[ -d "dist/WoodFlow.app" ]]; then
  open "dist/WoodFlow.app"
elif [[ -x ".venv/bin/python" ]]; then
  exec .venv/bin/python -m container_planner
else
  echo "请先使用打包好的WoodFlow.app，或按README.md完成开发环境安装。"
  read -r "?按回车关闭"
fi

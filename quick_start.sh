#!/usr/bin/env bash
set -euo pipefail

TARGET_DIR="${1:-/opt/emby_tg_admin}"

echo "[1/6] 创建目录: ${TARGET_DIR}"
mkdir -p "${TARGET_DIR}"
cd "${TARGET_DIR}"

echo "[2/6] 请把代码文件放到 ${TARGET_DIR} 后继续"
if [ ! -f ".env.example" ]; then
  echo "未找到 .env.example，请先把完整项目文件放到 ${TARGET_DIR}"
  exit 1
fi

echo "[3/6] 初始化 .env"
[ -f .env ] || cp .env.example .env

echo "[4/6] 请编辑 .env 后再启动"
echo "示例: nano .env"

echo "[5/6] 启动容器（默认不对外开放 Web 端口）"
docker compose up -d --build

echo "[6/6] 查看日志"
docker compose logs -f --tail=200

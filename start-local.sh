#!/bin/bash

set -e

echo "=============================================="
echo "  本地开发环境启动脚本 (不使用 Docker)"
echo "=============================================="
echo ""

echo "[1/4] 启动 ClickHouse..."
if ! docker ps | grep -q clickhouse; then
    docker run -d \
        --name clickhouse-server \
        -p 8123:8123 \
        -p 9000:9000 \
        --ulimit nofile=262144:262144 \
        clickhouse/clickhouse-server:24.3
    echo "✅ ClickHouse 容器已启动"
else
    echo "✅ ClickHouse 已在运行"
fi

echo ""
echo "[2/4] 等待 ClickHouse 就绪..."
sleep 5

echo ""
echo "[3/4] 初始化数据库和表结构..."
cd backend
python3 -c "
from db import get_db_client
db = get_db_client()
print('✅ 数据库初始化完成')
"

echo ""
echo "[4/4] 启动后端服务..."
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

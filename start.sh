#!/bin/bash

set -e

echo "=============================================="
echo "  晶圆厂气相化学品泄漏监控系统 - 启动脚本"
echo "  Fab Gas Leak Monitoring System"
echo "=============================================="
echo ""

echo "[1/4] 检查 Docker 环境..."
if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安装，请先安装 Docker"
    exit 1
fi
echo "✅ Docker 已安装"

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose 未安装，请先安装 Docker Compose"
    exit 1
fi
echo "✅ Docker Compose 已安装"
echo ""

echo "[2/4] 停止旧服务（如果存在）..."
docker-compose down 2>/dev/null || true
echo ""

echo "[3/4] 构建并启动服务..."
echo "  - ClickHouse (端口 8123, 9000)"
echo "  - FastAPI Backend (端口 8000)"
echo "  - Vue Frontend (端口 5173)"
echo "  - Data Simulator (持续生成传感器数据)"
echo ""

docker-compose up -d --build

echo ""
echo "[4/4] 等待服务就绪..."
echo ""

max_wait=60
count=0
while [ $count -lt $max_wait ]; do
    if curl -s http://localhost:8123 > /dev/null 2>&1; then
        echo "✅ ClickHouse 就绪"
        break
    fi
    count=$((count + 2))
    echo "  等待中... ${count}s"
    sleep 2
done

echo ""
echo "等待后端服务..."
sleep 10

echo ""
echo "=============================================="
echo "  🎉 所有服务已启动！"
echo "=============================================="
echo ""
echo "📊 前端看板:   http://localhost:5173"
echo "🔌 API 文档:   http://localhost:8000/docs"
echo "🗄️  ClickHouse: http://localhost:8123"
echo ""
echo "📝 查看服务日志:"
echo "   docker-compose logs -f backend"
echo "   docker-compose logs -f simulator"
echo "   docker-compose logs -f clickhouse"
echo ""
echo "⏹️  停止服务:"
echo "   docker-compose down"
echo ""
echo "💡 提示: 数据模拟器正在持续生成随机数据,"
echo "   包括偶尔的气体泄漏事件（红色闪烁告警）"
echo "=============================================="

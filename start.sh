#!/usr/bin/env bash
# ============================================================
# XuanMu RedTeam Agent - 一键启动脚本
# 启动 PostgreSQL + 后端 API + 前端（构建后自动托管）
# ============================================================
set -e

cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"
VENV_DIR="$PROJECT_DIR/.venv"

echo "========================================"
echo "  XuanMu RedTeam Agent"
echo "  Version 0.2.1"
echo "========================================"

# 1. 检查 PostgreSQL 是否运行
echo "[1/3] 检查 PostgreSQL..."
if pg_isready -q 2>/dev/null; then
    echo "  ✅ PostgreSQL 已在运行"
else
    echo "  ⏳ 启动 PostgreSQL..."
    sudo pg_ctlcluster 18 main start 2>/dev/null || sudo service postgresql start 2>/dev/null || {
        echo "  ❌ 启动失败，请手动运行: sudo pg_ctlcluster 18 main start"
        exit 1
    }
    sleep 2
    if pg_isready -q 2>/dev/null; then
        echo "  ✅ PostgreSQL 启动成功"
    else
        echo "  ❌ PostgreSQL 启动失败"
        exit 1
    fi
fi

# 2. 激活虚拟环境
echo "[2/3] 加载 Python 虚拟环境..."
if [ ! -d "$VENV_DIR" ]; then
    echo "  ⏳ 创建虚拟环境..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt
fi
source "$VENV_DIR/bin/activate"
echo "  ✅ 虚拟就绪: $(python3 --version)"

# 3. 启动后端
echo "[3/3] 启动 XuanMu 后端服务..."
echo ""
echo "  🌐 API 地址:     http://127.0.0.1:8000"
echo "  📖 API 文档:     http://127.0.0.1:8000/docs"
echo "  🖥️  前端界面:    http://127.0.0.1:8000"
echo "  👤 管理员登录:   admin@admin.com / admin123"
echo ""
echo "  按 Ctrl+C 停止服务"
echo "========================================"
echo ""

exec python main.py

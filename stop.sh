#!/usr/bin/env bash
# ============================================================
# Z3r0 - 停止脚本
# ============================================================
set -e

cd "$(dirname "$0")"

echo "停止 Z3r0 后端..."
pkill -f "python main.py" 2>/dev/null && echo "  ✅ 已停止" || echo "  ℹ️  未在运行"

# 可选：停止 PostgreSQL
# echo "停止 PostgreSQL..."
# sudo pg_ctlcluster 18 main stop 2>/dev/null && echo "  ✅ PostgreSQL 已停止" || echo "  ℹ️  PostgreSQL 未运行"

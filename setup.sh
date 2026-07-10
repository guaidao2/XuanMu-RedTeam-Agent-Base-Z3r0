#!/usr/bin/env bash
# ============================================================
# XuanMu RedTeam Agent - 完整安装配置脚本
# 从零开始：安装依赖 → 配置数据库 → 构建前端 → 启动服务
# 适用环境：Kali Linux / Debian
# ============================================================
set -e

cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"

# ---------- 颜色 ----------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }
info() { echo -e "${BLUE}[~]${NC} $1"; }

# ============================================================
echo "========================================"
echo "  XuanMu RedTeam Agent v0.2.1"
echo "  安装配置脚本"
echo "========================================"
echo ""

# ---------- 1. 检查系统 ----------
info "检查系统环境..."
OS="$(uname -s)"
if [ "$OS" != "Linux" ]; then
    err "仅支持 Linux (推荐 Kali/Debian)"
fi
log "系统: $(lsb_release -ds 2>/dev/null || cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d= -f2 | tr -d '\"')"

# ---------- 2. 安装系统依赖 ----------
info "安装系统依赖..."
PKGS=""
command -v psql >/dev/null 2>&1 || PKGS="$PKGS postgresql postgresql-client"
command -v node >/dev/null 2>&1 || PKGS="$PKGS nodejs npm"
if [ "$(id -u)" -eq 0 ]; then
    if [ -n "$PKGS" ]; then
        apt update -qq && apt install -y -qq $PKGS 2>&1 | tail -2
        log "系统依赖已安装"
    else
        log "系统依赖已就绪"
    fi
else
    if [ -n "$PKGS" ]; then
        warn "需要 root 权限安装: $PKGS"
        warn "请手动执行: sudo apt update && sudo apt install -y $PKGS"
    else
        log "系统依赖已就绪"
    fi
fi

# ---------- 3. 配置 PostgreSQL ----------
info "配置 PostgreSQL..."
if pg_isready -q 2>/dev/null; then
    log "PostgreSQL 已在运行"
else
    if command -v pg_ctlcluster >/dev/null 2>&1; then
        sudo pg_ctlcluster 18 main start 2>/dev/null || sudo pg_ctlcluster 16 main start 2>/dev/null || {
            warn "启动 PostgreSQL 失败，请手动启动"
        }
    else
        sudo service postgresql start 2>/dev/null || {
            warn "启动 PostgreSQL 失败，请手动启动"
        }
    fi
    sleep 2
fi

# 创建数据库和用户（幂等）
PG_VERSION=$(pg_config --version 2>/dev/null | grep -oP '\d+' | head -1 || echo "16")
sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='root'" 2>/dev/null | grep -q 1 || {
    sudo -u postgres psql -c "CREATE USER root WITH PASSWORD '123456';" >/dev/null 2>&1
    log "数据库用户 root 已创建"
}
sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='z3r0'" 2>/dev/null | grep -q 1 || {
    sudo -u postgres psql -c "CREATE DATABASE z3r0 OWNER root;" >/dev/null 2>&1
    log "数据库 z3r0 已创建"
}
log "PostgreSQL 配置完成"

# ---------- 4. 创建配置文件 ----------
info "创建配置文件..."
CONFIG_FILE="$PROJECT_DIR/.xuanmu/config.json"
mkdir -p "$PROJECT_DIR/.xuanmu"
if [ ! -f "$CONFIG_FILE" ]; then
    if [ -f "$PROJECT_DIR/.xuanmu/config.json.example" ]; then
        cp "$PROJECT_DIR/.xuanmu/config.json.example" "$CONFIG_FILE"
        # 生成随机 encrypt_key
        ENCRYPT_KEY=$(openssl rand -base64 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_urlsafe(32))")
        # 使用 Python 更新配置
        python3 <<-PYEOF
import json
with open("$CONFIG_FILE", "r") as f:
    cfg = json.load(f)
cfg["system"]["encrypt_key"] = "$ENCRYPT_KEY"
cfg["system"]["bootstrap_admin"]["enabled"] = True
cfg["system"]["bootstrap_admin"]["password"] = "admin123"
cfg["system"]["bootstrap_admin"]["email"] = "admin@admin.com"
cfg["database"]["host"] = "127.0.0.1"
cfg["database"]["port"] = 5432
cfg["database"]["database"] = "z3r0"
cfg["database"]["username"] = "root"
cfg["database"]["password"] = "123456"
# 清空示例 API Key，等待用户填写
for agent in cfg.get("agents", {}).values():
    agent["api_key"] = ""
with open("$CONFIG_FILE", "w") as f:
    json.dump(cfg, f, indent=4, ensure_ascii=False)
print("encrypt_key: $ENCRYPT_KEY")
PYEOF
        log "配置文件已创建: $CONFIG_FILE"
        warn "请编辑 $CONFIG_FILE 填入 LLM API Key 和模型名"
        warn "需要修改 agents 下每个角色的 api_key / base_url / model 字段"
    else
        err "未找到 config.json.example"
    fi
else
    log "配置文件已存在，跳过"
fi

# ---------- 5. 创建 Python 虚拟环境 ----------
info "配置 Python 虚拟环境..."
VENV_DIR="$PROJECT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    log "虚拟环境已创建"
fi
source "$VENV_DIR/bin/activate"

# 安装依赖
info "安装 Python 依赖（阿里云镜像）..."
pip install -i https://mirrors.aliyun.com/pypi/simple/ --upgrade pip -q 2>&1 | tail -1
pip install -i https://mirrors.aliyun.com/pypi/simple/ \
    asyncpg sqlmodel openai mcp tiktoken sse-starlette python-multipart \
    pyjwt pyyaml httpx httpx-sse docker fastapi uvicorn websockets \
    pydantic-settings pydantic annotated-types anyio certifi charset-normalizer \
    click cryptography distro greenlet h11 httpcore idna jiter jsonschema \
    jsonschema-specifications openai-agents pycparser referencing regex \
    rpds-py sniffio starlette tqdm typing-inspection typing_extensions urllib3 \
    2>&1 | tail -3
log "Python 依赖已安装"

# ---------- 6. 构建前端 ----------
info "构建前端界面..."
if [ -d "$PROJECT_DIR/web" ]; then
    if [ ! -d "$PROJECT_DIR/web/node_modules" ]; then
        cd "$PROJECT_DIR/web" && npm install 2>&1 | tail -1
    fi
    # 获取 openapi.json
    if [ ! -f "$PROJECT_DIR/openapi.json" ]; then
        # 如果后端没跑，临时启动获取
        if ! curl -s -o /dev/null http://127.0.0.1:8000/docs 2>/dev/null; then
            cd "$PROJECT_DIR"
            source "$VENV_DIR/bin/activate"
            timeout 10 python main.py 2>/dev/null &
            sleep 6
            RETRIES=0
            until curl -s http://127.0.0.1:8000/openapi.json -o "$PROJECT_DIR/openapi.json" 2>/dev/null; do
                RETRIES=$((RETRIES + 1))
                if [ $RETRIES -ge 3 ]; then
                    warn "无法获取 openapi.json，跳过前端 API 类型生成"
                    break
                fi
                sleep 2
            done
            pkill -f "python main.py" 2>/dev/null || true
        else
            curl -s http://127.0.0.1:8000/openapi.json -o "$PROJECT_DIR/openapi.json" 2>/dev/null
        fi
    fi
    cd "$PROJECT_DIR/web"
    # 将 openapi.json 链接到 web 目录
    if [ -f "$PROJECT_DIR/openapi.json" ]; then
        ln -sf "$PROJECT_DIR/openapi.json" "$PROJECT_DIR/web/openapi.json"
    fi
    if npm run build 2>&1 | tail -3; then
        log "前端构建完成"
    else
        warn "前端构建失败，请检查错误日志"
    fi
    cd "$PROJECT_DIR"
else
    warn "无 web 目录，跳过前端构建"
fi

# ---------- 7. 创建启动/停止脚本 ----------
info "创建便捷脚本..."

cat > "$PROJECT_DIR/start.sh" << 'SCRIPT'
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
echo "  🌐 API 地址:     http://0.0.0.0:8000"
echo "  📖 API 文档:     http://127.0.0.1:8000/docs"
echo "  🖥️  前端界面:    http://127.0.0.1:8000"
echo "  👤 管理员登录:   admin@admin.com / admin123"
echo ""
echo "  按 Ctrl+C 停止服务"
echo "========================================"
echo ""

exec python main.py
SCRIPT
chmod +x "$PROJECT_DIR/start.sh"

cat > "$PROJECT_DIR/stop.sh" << 'SCRIPT'
#!/usr/bin/env bash
echo "停止 XuanMu..."
pkill -f "python main.py" 2>/dev/null && echo "  ✅ 已停止" || echo "  ℹ️  未在运行"
SCRIPT
chmod +x "$PROJECT_DIR/stop.sh"

log "便捷脚本已创建"

# ============================================================
echo ""
echo "========================================"
echo "  🎉 安装配置完成！"
echo "========================================"
echo ""
echo "  启动服务:  bash start.sh"
echo "  停止服务:  bash stop.sh"
echo "  管理 API:  bash config-tool.sh"
echo "  配置文件:  .xuanmu/config.json"
echo ""
echo "  ⚠️  重要：编辑 .xuanmu/config.json"
echo "     填入 agents 字段中的:"
echo "      - api_key (你的 API Key)"
echo "      - base_url (API 地址)"
echo "      - model (模型名, 如 deepseek-v4-flash)"
echo ""
echo "  然后执行 bash start.sh 即可运行"
echo "========================================"

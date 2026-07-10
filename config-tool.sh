#!/usr/bin/env bash
# ============================================================
# XuanMu 配置管理工具
# 一键管理 LLM API Key：清除 / 查看 / 设置
# ============================================================
set -e

cd "$(dirname "$0")"
CONFIG_FILE=".xuanmu/config.json"

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

usage() {
    cat <<EOF
用法: bash config-tool.sh <命令> [选项]

命令:
  clear       清除所有智能体的 API Key（设为空）
  list        查看当前各智能体的配置摘要
  set <key>   为所有智能体设置同一个 API Key
              可选: --url <地址> --model <模型名>

示例:
  bash config-tool.sh clear
  bash config-tool.sh list
  bash config-tool.sh set sk-your-key-here
  bash config-tool.sh set sk-your-key \\
    --url https://api.deepseek.com/v1 \\
    --model deepseek-chat
EOF
    exit 0
}

[ $# -lt 1 ] && usage

CMD="$1"
shift

# 检查配置文件
[ ! -f "$CONFIG_FILE" ] && err "未找到 $CONFIG_FILE，请先执行 bash setup.sh"

case "$CMD" in
    clear)
        echo "========================================"
        echo "  清除所有智能体的 API Key"
        echo "========================================"
        python3 <<-PYEOF
import json

with open("$CONFIG_FILE", "r") as f:
    cfg = json.load(f)

count = 0
for code, agent in cfg.get("agents", {}).items():
    if agent.get("api_key"):
        old = agent["api_key"][:8] + "..."
        agent["api_key"] = ""
        count += 1
        print(f"  🧹 {code} ({agent.get('name','')}): {old} → 已清除")

with open("$CONFIG_FILE", "w") as f:
    json.dump(cfg, f, indent=4, ensure_ascii=False)

if count == 0:
    print("  ℹ️  所有智能体 API Key 已经是空的")
else:
    print(f"\n  ✅ 已清除 {count} 个智能体的 API Key")
PYEOF
        echo ""
        echo "  重启服务生效: bash start.sh"
        echo "========================================"
        ;;

    list)
        echo "========================================"
        echo "  智能体配置摘要"
        echo "========================================"
        python3 <<-'PYEOF'
import json

with open("/root/Desktop/Z3r0-0.2.1/.xuanmu/config.json", "r") as f:
    cfg = json.load(f)

agents = cfg.get("agents", {})
if not agents:
    print("  ℹ️  未配置任何智能体")
else:
    print(f"  {'代号':<6} {'名称':<8} {'模型':<20} {'API地址':<30} {'Key状态':<10}")
    print(f"  {'-'*74}")
    for code, agent in agents.items():
        name = agent.get("name", "")
        model = agent.get("model", "")
        url = agent.get("base_url", "")
        key = agent.get("api_key", "")
        key_status = "✅ 已配置" if key else "❌ 未配置"
        # 截断长 URL
        if len(url) > 28:
            url = url[:25] + "..."
        print(f"  {code:<6} {name:<8} {model:<20} {url:<30} {key_status}")

print()
print(f"  系统监听: {cfg.get('system',{}).get('listen_addr','')}:{cfg.get('system',{}).get('listen_port','')}")
print(f"  管理员:   {cfg.get('system',{}).get('bootstrap_admin',{}).get('username','')}")
print("========================================")
PYEOF
        ;;

    set)
        API_KEY="${1:-}"
        [ -z "$API_KEY" ] && err "请提供 API Key\n用法: bash config-tool.sh set sk-your-key [--url <地址>] [--model <模型名>]"

        shift
        BASE_URL=""
        MODEL=""

        while [ $# -gt 0 ]; do
            case "$1" in
                --url)    BASE_URL="$2"; shift 2 ;;
                --model)  MODEL="$2"; shift 2 ;;
                *) err "未知选项: $1" ;;
            esac
        done

        echo "========================================"
        echo "  设置智能体 API Key"
        echo "========================================"
        python3 <<-PYEOF
import json

with open("$CONFIG_FILE", "r") as f:
    cfg = json.load(f)

agents = cfg.get("agents", {})
count = 0
for code, agent in agents.items():
    agent["api_key"] = "$API_KEY"
    $([ -n "$BASE_URL" ] && echo "agent[\"base_url\"] = \"$BASE_URL\"")
    $([ -n "$MODEL" ] && echo "agent[\"model\"] = \"$MODEL\"")
    count += 1
    name = agent.get("name", "")
    print(f"  ✅ {code} ({name}): Key 已设置")

with open("$CONFIG_FILE", "w") as f:
    json.dump(cfg, f, indent=4, ensure_ascii=False)

print(f"\n  共设置 {count} 个智能体")
PYEOF

        if [ -n "$BASE_URL" ]; then
            log "API 地址: $BASE_URL"
        fi
        if [ -n "$MODEL" ]; then
            log "模型名称: $MODEL"
        fi
        echo ""
        echo "  重启服务生效: bash start.sh"
        echo "========================================"
        ;;

    *)
        usage
        ;;
esac

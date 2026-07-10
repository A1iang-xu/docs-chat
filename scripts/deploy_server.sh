#!/bin/bash
# ═══════════════════════════════════════════════════════════
# DocsChat 一键部署脚本
# 在全新的 Ubuntu 服务器上运行即可完成部署
# 使用方式: bash deploy_server.sh
# ═══════════════════════════════════════════════════════════
set -e

# ── 颜色输出 ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ── 配置 ──
REPO_URL="https://github.com/A1iang-xu/docs-chat.git"
PROJECT_DIR="/opt/docs-chat"
COMPOSE_FILE="docker-compose.yml"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║     DocsChat 一键部署脚本               ║"
echo "║     RAG 智能知识库问答系统              ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ═══════════════════════════════════════════
# Step 1: 检查 root 权限
# ═══════════════════════════════════════════
if [ "$EUID" -ne 0 ]; then
  warn "建议使用 root 用户运行，当前非 root，尝试使用 sudo..."
  SUDO="sudo"
else
  SUDO=""
fi

# ═══════════════════════════════════════════
# Step 2: 安装 Docker
# ═══════════════════════════════════════════
info "检查 Docker 环境..."
if command -v docker &> /dev/null; then
  ok "Docker 已安装: $(docker --version)"
else
  info "安装 Docker..."
  curl -fsSL https://get.docker.com | $SUDO bash
  $SUDO systemctl enable docker
  $SUDO systemctl start docker
  ok "Docker 安装完成"
fi

# 检查 docker compose
if docker compose version &> /dev/null; then
  ok "Docker Compose 已就绪"
else
  error "Docker Compose 不可用，请手动安装"
  exit 1
fi

# ═══════════════════════════════════════════
# Step 3: 克隆/更新项目
# ═══════════════════════════════════════════
if [ -d "$PROJECT_DIR/.git" ]; then
  info "项目已存在，拉取最新代码..."
  cd "$PROJECT_DIR"
  git pull origin main 2>/dev/null || git pull origin master 2>/dev/null || warn "无法自动拉取，使用现有代码"
else
  info "克隆项目到 $PROJECT_DIR ..."
  $SUDO mkdir -p "$PROJECT_DIR"
  $SUDO chown -R "$USER":"$USER" "$PROJECT_DIR"
  git clone "$REPO_URL" "$PROJECT_DIR"
  cd "$PROJECT_DIR"
fi
ok "代码准备完成"

# ═══════════════════════════════════════════
# Step 4: 配置环境变量
# ═══════════════════════════════════════════
info "配置环境变量..."

ENV_FILE="$PROJECT_DIR/.env.docker"

if [ -f "$ENV_FILE" ]; then
  info ".env.docker 已存在"
  read -p "是否重新配置？(y/N): " RECONFIG
  if [[ "$RECONFIG" != "y" && "$RECONFIG" != "Y" ]]; then
    ok "保留现有配置"
    SKIP_ENV=true
  fi
fi

if [ "$SKIP_ENV" != "true" ]; then
  # 获取服务器公网 IP
  SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || curl -s ip.sb 2>/dev/null || echo "localhost")
  info "检测到服务器 IP: $SERVER_IP"

  # 输入 API Key
  echo ""
  read -p "请输入 DeepSeek API Key (sk-xxx): " API_KEY
  if [ -z "$API_KEY" ]; then
    error "API Key 不能为空"
    exit 1
  fi

  # 是否启用 API Key 保护
  read -p "是否启用 Demo API Key 保护？(防止滥用) (y/N): " ENABLE_PROTECT
  DEMO_KEY_REQUIRED="false"
  DEMO_KEY=""
  if [[ "$ENABLE_PROTECT" == "y" || "$ENABLE_PROTECT" == "Y" ]]; then
    DEMO_KEY_REQUIRED="true"
    DEMO_KEY="docschat-$(openssl rand -hex 8)"
    info "Demo API Key: $DEMO_KEY (请在访问时携带)"
  fi

  # 生成 .env.docker
  cat > "$ENV_FILE" << EOF
# ── DocsChat 生产环境配置 ──
# 生成时间: $(date '+%Y-%m-%d %H:%M:%S')

# ── LLM ──
DEEPSEEK_API_KEY=$API_KEY
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat

# ── Embedding ──
EMBEDDING_MODEL=all-MiniLM-L6-v2
EMBEDDING_DIM=384

# ── 文档解析 ──
PARSER_TYPE=fallback

# ── Reranker ──
RERANKER_TYPE=fallback

# ── 服务 ──
HOST=0.0.0.0
PORT=8000
CORS_ORIGINS=["http://$SERVER_IP","http://localhost","http://localhost:80"]
LOG_LEVEL=INFO

# ── 缓存 ──
CACHE_L1_ENABLED=true
CACHE_L1_TTL_SECONDS=3600

# ── 速率限制 ──
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS=20
RATE_LIMIT_WINDOW_SECONDS=60

# ── Demo 防护 ──
DEMO_API_KEY_REQUIRED=$DEMO_KEY_REQUIRED
DEMO_API_KEY=$DEMO_KEY
EOF

  ok ".env.docker 生成完成"
fi

# ═══════════════════════════════════════════
# Step 5: 构建并启动容器
# ═══════════════════════════════════════════
info "构建 Docker 镜像（首次构建约需 5-10 分钟）..."
cd "$PROJECT_DIR"
docker compose --env-file .env.docker up --build -d

# 等待健康检查
info "等待服务启动..."
sleep 10

# 检查容器状态
BACKEND_STATUS=$(docker inspect --format='{{.State.Health.Status}}' docschat-backend 2>/dev/null || echo "starting")
FRONTEND_STATUS=$(docker inspect --format='{{.State.Status}}' docschat-frontend 2>/dev/null || echo "starting")

# ═══════════════════════════════════════════
# Step 6: 显示结果
# ═══════════════════════════════════════════
SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || echo "YOUR_SERVER_IP")

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║            部署完成！                    ║"
echo "╠══════════════════════════════════════════╣"
echo "║                                          ║"
echo "║  前端访问: http://$SERVER_IP"
echo "║  后端 API: http://$SERVER_IP:8000"
echo "║  健康检查: http://$SERVER_IP:8000/health"
echo "║                                          ║"
if [ "$DEMO_KEY_REQUIRED" = "true" ]; then
echo "║  Demo API Key: $DEMO_KEY"
fi
echo "║                                          ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "常用命令:"
echo "  查看日志:   cd $PROJECT_DIR && docker compose logs -f"
echo "  重启服务:   cd $PROJECT_DIR && docker compose restart"
echo "  停止服务:   cd $PROJECT_DIR && docker compose down"
echo "  更新部署:   cd $PROJECT_DIR && git pull && docker compose up --build -d"
echo ""

#!/usr/bin/env bash
# ==============================================================================
# 一周好好吃 (MealPlanner AI) — 腾讯云 / 任意 Linux 云服务器一键自动化部署脚本
# 支持系统：Ubuntu 20.04/22.04/24.04, Debian 11/12, CentOS 7/8/9, TencentOS
# ==============================================================================
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}====================================================${NC}"
echo -e "${GREEN}   正在开始部署：一周好好吃 (MealPlanner AI) 全栈服务   ${NC}"
echo -e "${GREEN}====================================================${NC}"

# 1. 检查 root 权限
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}请使用 root 用户运行此脚本（例如: sudo bash deploy.sh）${NC}"
  exit 1
fi

APP_DIR="/opt/wanting-meal-planner"
DB_NAME="meal_planner"
DB_USER="meal_user"
DB_PASS="$(tr -dc A-Za-z0-9 </dev/urandom | head -c 16)"

# 2. 交互式输入大模型配置
echo -e "\n${YELLOW}>>> 请配置大模型 API Key（推荐 DeepSeek）<<<${NC}"
read -rp "请输入大模型 API 基础地址 [默认: https://api.deepseek.com/v1]: " INPUT_LLM_URL
LLM_BASE_URL="${INPUT_LLM_URL:-https://api.deepseek.com/v1}"

read -rp "请输入大模型 Model 名称 [默认: deepseek-chat]: " INPUT_LLM_MODEL
LLM_MODEL="${INPUT_LLM_MODEL:-deepseek-chat}"

while true; do
  read -rsp "请输入大模型 API Key (输入时隐藏): " LLM_API_KEY
  echo ""
  if [ -n "$LLM_API_KEY" ]; then
    break
  fi
  echo -e "${RED}API Key 不能为空，请重新输入${NC}"
done

# 3. 安装系统依赖
echo -e "\n${YELLOW}>>> 1/5 正在安装系统基础环境 (Python3, Node.js, PostgreSQL, Nginx)...<<<${NC}"
if command -v apt-get >/dev/null 2>&1; then
  apt-get update -y
  apt-get install -y git curl python3 python3-pip python3-venv postgresql postgresql-contrib nginx
elif command -v yum >/dev/null 2>&1; then
  yum update -y
  yum install -y git curl python3 python3-pip postgresql-server postgresql-contrib nginx
  postgresql-setup initdb || true
fi

# 4. 安装 Node.js 20 (若未安装)
if ! command -v node >/dev/null 2>&1; then
  echo -e "${YELLOW}>>> 正在安装 Node.js LTS...<<<${NC}"
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs || yum install -y nodejs
fi

# 5. 配置 PostgreSQL
echo -e "\n${YELLOW}>>> 2/5 正在初始化 PostgreSQL 数据库...<<<${NC}"
systemctl enable postgresql
systemctl start postgresql

sudo -u postgres psql -c "CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASS}';" || true
sudo -u postgres psql -c "ALTER USER ${DB_USER} WITH PASSWORD '${DB_PASS}';"
sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};" || true
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};"

# 6. 拉取/更新代码仓库
echo -e "\n${YELLOW}>>> 3/5 正在同步最新源码...<<<${NC}"
mkdir -p "$APP_DIR"
if [ -d "$APP_DIR/.git" ]; then
  cd "$APP_DIR"
  git fetch origin
  git reset --hard origin/main
else
  git clone https://github.com/Sinera-kiki/wanting-meal-planner.git "$APP_DIR"
  cd "$APP_DIR"
fi

# 7. 配置后端环境并初始化表
echo -e "\n${YELLOW}>>> 4/5 正在构建后端服务与数据库表...<<<${NC}"
cat > "$APP_DIR/.env" <<EOF
APP_LLM_BASE_URL=${LLM_BASE_URL}
APP_LLM_API_KEY=${LLM_API_KEY}
APP_LLM_MODEL=${LLM_MODEL}
APP_DB_HOST=127.0.0.1
APP_DB_PORT=5432
APP_DB_NAME=${DB_NAME}
APP_DB_USER=${DB_USER}
APP_DB_PASSWORD=${DB_PASS}
EOF

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/backend/requirements.txt"

# 导出环境变量并运行 DDL 建表
set -a
# shellcheck disable=SC1091
source "$APP_DIR/.env"
set +a
"$APP_DIR/.venv/bin/python" "$APP_DIR/backend/init_db.py"

# 8. 构建前端生产静态资源
echo -e "\n${YELLOW}>>> 5/5 正在构建前端生产包并配置 Nginx...<<<${NC}"
cd "$APP_DIR/frontend"
npm install --registry=https://registry.npmjs.org
# 构建为真实全栈模式（VITE_DEMO_MODE=false）
VITE_DEMO_MODE=false npm run build

# 9. 配置 systemd 后台服务
cat > /etc/systemd/system/meal-planner.service <<EOF
[Unit]
Description=MealPlanner AI FastAPI Backend Service
After=network.target postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/.venv/bin/uvicorn backend.app:app --host 127.0.0.1 --port 3000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable meal-planner.service
systemctl restart meal-planner.service

# 10. 配置 Nginx 80 端口代理
cat > /etc/nginx/conf.d/meal_planner.conf <<EOF
server {
    listen 80;
    server_name _;

    root ${APP_DIR}/frontend/dist;
    index index.html;

    # 前端 SPA 路由 fallback
    location / {
        try_files \$uri \$uri/ /index.html;
    }

    # 后端 API 反向代理
    location /api/ {
        proxy_pass http://127.0.0.1:3000/api/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 90s;
        proxy_read_timeout 90s;
    }

    location /health {
        proxy_pass http://127.0.0.1:3000/health;
    }
}
EOF

# 清理 default 配置以防冲突
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl restart nginx

# 11. 获取服务器公网 IP
PUBLIC_IP=$(curl -s https://api.ipify.org || curl -s ifconfig.me || echo "你的服务器公网IP")

echo -e "\n${GREEN}====================================================${NC}"
echo -e "${GREEN}🎉 恭喜！一周好好吃 (MealPlanner AI) 已经成功部署上线！${NC}"
echo -e "${GREEN}====================================================${NC}"
echo -e "👉 网页访问地址: ${YELLOW}http://${PUBLIC_IP}${NC}"
echo -e "👉 后台服务状态: systemctl status meal-planner"
echo -e "👉 后端实时日志: journalctl -u meal-planner -f"
echo -e "👉 Nginx 状态:   systemctl status nginx"
echo -e "👉 配置文件目录: ${APP_DIR}/.env"
echo -e "${GREEN}====================================================${NC}"

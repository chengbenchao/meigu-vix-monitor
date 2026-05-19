#!/usr/bin/env bash
# ─────────────────────────────────────────────
# Meigu VIX Monitor — One-Click Deploy
# 在任意 Ubuntu/Debian 机器上运行此脚本即可部署
# ─────────────────────────────────────────────
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

# ── 1. Check prerequisites ──────────────────
command -v python3 &>/dev/null || err "需要 Python 3.9+"
command -v nginx  &>/dev/null || err "需要 nginx (apt install nginx)"
command -v systemctl &>/dev/null || err "需要 systemd"

# ── 2. FRED API Key ─────────────────────────
if [ -z "${FRED_API_KEY:-}" ]; then
    if [ -f /etc/systemd/system/meigu.service.d/env.conf ] 2>/dev/null; then
        warn "FRED_API_KEY 未设置，但不影响已配置的环境"
    else
        warn "请设置 FRED_API_KEY 环境变量:"
        warn "  export FRED_API_KEY=your_key_here"
        warn "  然后重新运行此脚本"
        warn ""
        warn "免费获取: https://fred.stlouisfed.org/docs/api/api_key.html"
        exit 1
    fi
fi

# ── 3. Project directory ────────────────────
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
DB_DIR="/var/lib/meigu"
NGINX_CONF="/etc/nginx/sites-enabled/meigu"

log "项目目录: $PROJECT_DIR"

# ── 4. Install Python dependencies ──────────
log "安装 Python 依赖..."
python3 -m pip install -r "$PROJECT_DIR/requirements.txt" -q

# ── 5. Database directory ───────────────────
log "创建数据库目录..."
mkdir -p "$DB_DIR"

# ── 6. Systemd service ──────────────────────
log "配置 systemd 服务..."
cat > /etc/systemd/system/meigu.service << SERVICE
[Unit]
Description=Meigu VIX Monitor (FastAPI)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$PROJECT_DIR
Environment="FRED_API_KEY=${FRED_API_KEY:-}"
ExecStart=$(which python3) -m uvicorn app:app --host 127.0.0.1 --port 8003
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable --now meigu
log "服务已启动"

# ── 7. Nginx ────────────────────────────────
log "配置 Nginx..."
# Find the existing server block listening on port 80
if [ -f "$NGINX_CONF" ]; then
    warn "Nginx 配置已存在，跳过"
else
    cat > /etc/nginx/sites-enabled/meigu.conf << 'NGINX'
# 将此 location 块添加到你的 server { listen 80; } 块中
location /meigu/ {
    proxy_pass http://127.0.0.1:8003/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Prefix /meigu;
    proxy_read_timeout 30s;
}
NGINX
    warn "Nginx 配置已写入 $NGINX_CONF"
    warn "请手动将它合并到你的 server 块中，然后 nginx -s reload"
fi

# ── 8. Cron ──────────────────────────────────
log "配置定时抓取（工作日 18:00 北京时间）..."
(crontab -l 2>/dev/null | grep -v 'fetch_daily.py'; echo "0 10 * * 1-5 FRED_API_KEY=${FRED_API_KEY:-} cd $PROJECT_DIR && $(which python3) fetch_daily.py >> /var/log/meigu-fetch.log 2>&1") | crontab -

# ── 9. Initial data fetch ───────────────────
log "首次数据抓取（这可能需要几分钟）..."
sleep 2
python3 "$PROJECT_DIR/fetch_daily.py"

# ── Done ────────────────────────────────────
echo ""
log "============================================"
log "  Meigu VIX Monitor 部署完成！"
log "  访问: http://$(hostname -I | awk '{print $1}')/meigu/"
log "============================================"

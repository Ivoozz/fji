#!/bin/bash
set -e

# ==========================================
# FixJeICT v2 Installer
# ==========================================
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/Ivoozz/fixjeictv2/main/install.sh | sudo bash
#
# Custom credentials (non-interactive):
#   ADMIN_USERNAME=myuser ADMIN_PASSWORD=mypass curl -fsSL ... | sudo bash
# ==========================================

export DEBIAN_FRONTEND=noninteractive

INSTALL_DIR="/opt/fixjeictv2"
GITHUB_REPO="https://github.com/Ivoozz/fixjeictv2"
SERVICE_NAME="fixjeict"

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

info()    { echo -e "${BLUE}ℹ $1${NC}"; }
success() { echo -e "${GREEN}✓ $1${NC}"; }
error()   { echo -e "${RED}✗ $1${NC}"; exit 1; }

echo "========================================"
echo "FixJeICT v2 Installer"
echo "========================================"
echo ""

# Must run as root
if [ "$EUID" -ne 0 ]; then
    error "Run this script as root (sudo)"
fi

info "Installation directory: ${INSTALL_DIR}"

# Step 1: Prerequisites
info "Checking prerequisites..."
apt-get update -qq
# Install python3-venv; fall back to python3.XX-venv on Debian 12+
if ! apt-get install -y -qq python3 python3-venv python3-pip curl openssl 2>/dev/null; then
    PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "3.11")
    apt-get install -y -qq python3 "python3.${PY_VER##*.}-venv" python3-pip curl openssl
fi
success "Prerequisites OK"

# Step 2: Download
info "Downloading FixJeICT v2..."
if [ -d "$INSTALL_DIR" ]; then
    systemctl stop $SERVICE_NAME 2>/dev/null || true
    rm -rf "$INSTALL_DIR"
fi
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"
curl -fsSL "${GITHUB_REPO}/archive/refs/heads/main.tar.gz" -o fixjeict.tar.gz
info "Extracting archive..."
tar -xzf fixjeict.tar.gz --strip-components=1
rm fixjeict.tar.gz
success "FixJeICT v2 downloaded and extracted"

# Step 3: Python virtualenv
info "Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate
info "Upgrading pip..."
pip install --upgrade pip -q
info "Installing Python dependencies..."
pip install -r requirements.txt -q
success "Dependencies installed"

echo ""
echo "========================================"
echo "Configuration"
echo "========================================"
echo ""

# Step 4: Configuration
SECRET_KEY_DEFAULT=$(openssl rand -hex 32)

# Detect interactive terminal
if [ -t 0 ] && [ -z "${CI:-}" ]; then
    # Interactive mode: prompt for credentials
    read -rp "Admin username [admin]: " ADMIN_USERNAME_INPUT
    ADMIN_USERNAME="${ADMIN_USERNAME:-${ADMIN_USERNAME_INPUT:-admin}}"

    while true; do
        read -rsp "Admin password (required): " ADMIN_PASSWORD_INPUT
        echo ""
        if [ -n "$ADMIN_PASSWORD_INPUT" ]; then
            ADMIN_PASSWORD="${ADMIN_PASSWORD:-$ADMIN_PASSWORD_INPUT}"
            break
        fi
        echo "Password cannot be empty, please try again."
    done

    read -rp "Secret key [auto-generated]: " SECRET_KEY_INPUT
    SECRET_KEY="${SECRET_KEY:-${SECRET_KEY_INPUT:-$SECRET_KEY_DEFAULT}}"

    echo ""
    echo "Email settings (Resend API + Cloudflare Email Routing):"
    read -rp "  Resend API key (re_...): " RESEND_API_KEY
    read -rp "  Email domain [fixjeict.nl]: " EMAIL_DOMAIN_INPUT
    EMAIL_DOMAIN="${EMAIL_DOMAIN_INPUT:-fixjeict.nl}"
    read -rp "  From email [FixJeICT <noreply@${EMAIL_DOMAIN}>]: " EMAIL_FROM_INPUT
    EMAIL_FROM="${EMAIL_FROM_INPUT:-FixJeICT <noreply@${EMAIL_DOMAIN}>}"
    echo ""
    echo "Cloudflare Email Routing (for auto-forwarding):"
    read -rp "  Cloudflare API token: " CLOUDFLARE_API_TOKEN
    read -rp "  Cloudflare Account ID: " CLOUDFLARE_ACCOUNT_ID
    read -rp "  Cloudflare Zone ID: " CLOUDFLARE_ZONE_ID
else
    # Non-interactive mode: use env vars or safe defaults
    ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
    ADMIN_PASSWORD="${ADMIN_PASSWORD:-$(openssl rand -hex 12)}"
    SECRET_KEY="${SECRET_KEY:-$SECRET_KEY_DEFAULT}"
    RESEND_API_KEY="${RESEND_API_KEY:-}"
    EMAIL_DOMAIN="${EMAIL_DOMAIN:-fixjeict.nl}"
    EMAIL_FROM="${EMAIL_FROM:-FixJeICT <noreply@fixjeict.nl>}"
    CLOUDFLARE_API_TOKEN="${CLOUDFLARE_API_TOKEN:-}"
    CLOUDFLARE_ACCOUNT_ID="${CLOUDFLARE_ACCOUNT_ID:-}"
    CLOUDFLARE_ZONE_ID="${CLOUDFLARE_ZONE_ID:-}"
fi

success "Generated SECRET_KEY"

mkdir -p data
mkdir -p static/css

cat > .env << EOF
# FixJeICT v2 Configuration
SECRET_KEY=${SECRET_KEY}
ADMIN_USERNAME=${ADMIN_USERNAME}
ADMIN_PASSWORD=${ADMIN_PASSWORD}

# Database
DATABASE_URL=sqlite:///${INSTALL_DIR}/data/fixjeict.db

# Server Settings
HOST=0.0.0.0
PORT=5000

# Email (Resend API)
RESEND_API_KEY=${RESEND_API_KEY}
EMAIL_FROM=${EMAIL_FROM}
EMAIL_DOMAIN=${EMAIL_DOMAIN}

# Cloudflare Email Routing
CLOUDFLARE_API_TOKEN=${CLOUDFLARE_API_TOKEN}
CLOUDFLARE_ACCOUNT_ID=${CLOUDFLARE_ACCOUNT_ID}
CLOUDFLARE_ZONE_ID=${CLOUDFLARE_ZONE_ID}
EOF

chmod 600 .env
success "Configuration written to ${INSTALL_DIR}/.env"

# Step 5: Database
info "Initializing database..."
python3 -c "from models import init_db; init_db(); print('Database initialized')" 2>/dev/null || info "Database init skipped (will run on first start)"

# Step 6: Systemd service
info "Creating systemd service..."
cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=FixJeICT v2 Application
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/venv/bin/uvicorn main:app --host 0.0.0.0 --port 5000
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=${INSTALL_DIR}/.env

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable $SERVICE_NAME
systemctl start $SERVICE_NAME

# Step 7: Firewall
if command -v ufw &>/dev/null; then
    ufw allow 5000/tcp 2>/dev/null || true
    info "Opened port 5000 in UFW"
fi

# Step 8: Health check
info "Waiting for service to start..."
SERVER_IP=$(hostname -I | awk '{print $1}')
HEALTH_OK=0
for i in 1 2 3; do
    sleep 5
    if curl -sf "http://localhost:5000/" -o /dev/null 2>/dev/null; then
        HEALTH_OK=1
        break
    fi
    info "Attempt ${i}/3: service not yet ready, retrying..."
done

echo ""
echo "========================================"
if [ "$HEALTH_OK" -eq 1 ]; then
    echo "✓ Installation complete!"
else
    echo "⚠ Installation complete (service may still be starting)"
fi
echo "========================================"
echo ""
echo "FixJeICT v2 is now running at:"
echo "  Website: http://${SERVER_IP}:5000"
echo "  Admin:   http://${SERVER_IP}:5000/admin/login"
echo ""
echo "Admin credentials:"
echo "  Username: ${ADMIN_USERNAME}"
echo "  Password: ${ADMIN_PASSWORD}"
echo ""
echo "To use custom credentials next time:"
echo "  ADMIN_USERNAME=user ADMIN_PASSWORD=pass curl -fsSL ... | sudo bash"
echo ""
echo "Service commands:"
echo "  Status:  systemctl status ${SERVICE_NAME}"
echo "  Restart: systemctl restart ${SERVICE_NAME}"
echo "  Logs:    journalctl -u ${SERVICE_NAME} -f"
echo "  Config:  ${INSTALL_DIR}/.env"
echo ""
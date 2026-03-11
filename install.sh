#!/bin/bash
# FixJeICT - LXC Native Production Installer [v4.0]
# Geoptimaliseerd voor Debian 12 (Bookworm) / Debian Trixie LXC.
# Geen Docker nesting - Maximale performance.

set -e

# Kleuren voor output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

clear
echo -e "${BLUE}====================================================${NC}"
echo -e "${BLUE}   FixJeICT - LXC Enterprise Installer [v4.0]      ${NC}"
echo -e "${BLUE}====================================================${NC}"

# 1. Root Check
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}❌ Fout: Voer dit script uit als root (sudo).${NC}"
  exit 1
fi

# 2. Systeem Afhankelijkheden
echo -e "${BLUE}[1/6] Systeem pakketten installeren...${NC}"
apt-get update -qq
apt-get install -y python3-pip python3-venv postgresql postgresql-contrib nginx git curl openssl ufw -qq

# 3. PostgreSQL Configuratie
echo -e "${BLUE}[2/6] Database configureren...${NC}"
DB_NAME="fji_db"
DB_USER="fji_user"
DB_PASS=$(openssl rand -hex 16)

# PostgreSQL gebruiker en DB aanmaken (indien niet aanwezig)
sudo -u postgres psql -c "CREATE DATABASE $DB_NAME;" || true
sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';" || true
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;" || true

# 4. Applicatie Setup
INSTALL_DIR="/opt/fji"
echo -e "${BLUE}[3/6] Applicatie installeren in $INSTALL_DIR...${NC}"

if [ -d "$INSTALL_DIR" ]; then
    cd "$INSTALL_DIR"
    git fetch --all
    git reset --hard origin/main
else
    git clone https://github.com/Ivoozz/fji.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# Venv en Requirements
python3 -m venv venv
./venv/bin/pip install --upgrade pip -q
./venv/bin/pip install -r requirements.txt -q

# .env genereren
cat <<EOF > .env
DATABASE_URL=postgresql://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME
ENCRYPTION_KEY=$(openssl rand -base64 32)
APP_URL=http://$(hostname -I | awk '{print $1}')
EOF

# Directories en Rechten
mkdir -p data/uploads
chmod -R 775 data/uploads
chown -R www-data:www-data "$INSTALL_DIR"

# 5. Systemd Service aanmaken
echo -e "${BLUE}[4/6] Systemd service configureren...${NC}"
cat <<EOF > /etc/systemd/system/fji.service
[Unit]
Description=FixJeICT FastAPI Application
After=network.target postgresql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=$INSTALL_DIR
Environment="PATH=$INSTALL_DIR/venv/bin"
ExecStart=$INSTALL_DIR/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --proxy-headers
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable fji
systemctl restart fji

# 6. Nginx Reverse Proxy
echo -e "${BLUE}[5/6] Nginx webserver configureren...${NC}"
cat <<EOF > /etc/nginx/sites-available/fji
server {
    listen 80;
    server_name _;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /static {
        alias $INSTALL_DIR/static;
    }
}
EOF

ln -sf /etc/nginx/sites-available/fji /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
systemctl restart nginx

echo -e "${GREEN}====================================================${NC}"
echo -e "${GREEN}🎉 Native LXC Installatie Succesvol!${NC}"
echo -e "Performance geoptimaliseerd voor bare-metal Debian."
echo ""
echo -e "📍 URL: http://$(hostname -I | awk '{print $1}')"
echo -e "⚙️  Setup: Ga direct naar /setup om te beginnen."
echo -e "${GREEN}====================================================${NC}"

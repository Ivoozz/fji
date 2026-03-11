#!/bin/bash
# FixJeICT - Ultieme Productie Installer [v3.0]
# Geoptimaliseerd voor Debian/Ubuntu & Docker-first deployment.

set -e

# Kleuren voor output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

clear
echo -e "${BLUE}====================================================${NC}"
echo -e "${BLUE}   FixJeICT - Enterprise Edition Installer [v3.0]   ${NC}"
echo -e "${BLUE}====================================================${NC}"

# 1. Root Check
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}❌ Fout: Voer dit script uit als root (sudo).${NC}"
  exit 1
fi

# 2. Systeem Checks
echo -e "${BLUE}[1/5] Systeem validatie...${NC}"
TOTAL_RAM=$(free -m | awk '/^Mem:/{print $2}')
if [ "$TOTAL_RAM" -lt 1024 ]; then
    echo -e "⚠️  Waarschuwing: Minder dan 1GB RAM gedetecteerd ($TOTAL_RAM MB). Performance kan lager zijn."
fi

# 3. Dependencies Installeren
echo -e "${BLUE}[2/5] Benodigde pakketten installeren...${NC}"
apt-get update -qq
apt-get install -y git curl openssl ufw -qq

# 4. Docker & Compose Installeren
echo -e "${BLUE}[3/5] Docker stack voorbereiden...${NC}"
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
else
    echo "✅ Docker is reeds aanwezig."
fi

if ! command -v docker-compose &> /dev/null; then
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
else
    echo "✅ Docker Compose is reeds aanwezig."
fi

# 5. Deployment
INSTALL_DIR="/opt/fji"
echo -e "${BLUE}[4/5] Applicatie uitrollen naar $INSTALL_DIR...${NC}"

if [ -d "$INSTALL_DIR" ]; then
    cd "$INSTALL_DIR"
    git fetch --all
    git reset --hard origin/main
else
    git clone https://github.com/Ivoozz/fji.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# Automatische .env generatie voor productie
if [ ! -f .env ]; then
    echo -e "${BLUE}[5/5] Beveiliging configureren...${NC}"
    DB_PASS=$(openssl rand -hex 16)
    cp .env.example .env 2>/dev/null || touch .env
    echo "POSTGRES_PASSWORD=$DB_PASS" >> .env
    echo "DATABASE_URL=postgresql://fji_user:$DB_PASS@db:5432/fji_db" >> .env
fi

# Rechten goedzetten
chmod +x start-production.sh
mkdir -p data/uploads
chmod -R 777 data/uploads

# Starten
./start-production.sh

echo -e "${GREEN}====================================================${NC}"
echo -e "${GREEN}🎉 Installatie Succesvol!${NC}"
echo -e "FixJeICT draait nu in de achtergrond via Docker."
echo ""
echo -e "📍 URL: http://$(hostname -I | awk '{print $1}'):8000"
echo -e "⚙️  Setup: Ga direct naar /setup om de app te configureren."
echo -e "${GREEN}====================================================${NC}"

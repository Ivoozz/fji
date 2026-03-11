#!/bin/bash
# FixJeICT Productie Installer
# Dit script installeert Docker en start de FixJeICT applicatie.

set -e

echo "===================================================="
echo "   FixJeICT - Enterprise Editie Installer"
echo "===================================================="

# 1. Check Root
if [ "$EUID" -ne 0 ]; then
  echo "❌ Start dit script als root (sudo)."
  exit 1
fi

# 2. Systeem updaten & Dependencies
echo "🔄 [1/4] Systeem updaten en afhankelijkheden installeren..."
apt-get update -qq
apt-get install -y git curl openssl -qq

# 3. Docker Installeren (indien niet aanwezig)
if ! command -v docker &> /dev/null; then
    echo "🐳 [2/4] Docker installeren..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
else
    echo "✅ [2/4] Docker is al geïnstalleerd."
fi

# Docker Compose check
if ! command -v docker-compose &> /dev/null; then
    echo "🐳 [3/4] Docker Compose installeren..."
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
else
    echo "✅ [3/4] Docker Compose is al geïnstalleerd."
fi

# 4. Applicatie Uitrollen
INSTALL_DIR="/opt/fixjeict"
echo "🚀 [4/4] Applicatie uitrollen naar $INSTALL_DIR..."

if [ -d "$INSTALL_DIR" ]; then
    echo "⚠️ Map $INSTALL_DIR bestaat al. Updaten..."
    cd "$INSTALL_DIR"
    git fetch --all
    git reset --hard origin/main
else
    git clone https://github.com/Ivoozz/fji.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# Start script uitvoeren
chmod +x start-production.sh
./start-production.sh

echo "===================================================="
echo "🎉 Installatie Voltooid!"
echo "➡️  Open je browser en navigeer naar http://<jouw-server-ip>:8000/setup"
echo "===================================================="

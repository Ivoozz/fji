#!/bin/bash
echo "🚀 Start FixJeICT in Productie Modus"

# Ensure .env exists
if [ ! -f .env ]; then
    echo "⚠️ Geen .env bestand gevonden. Kopieer .env.example..."
    cp .env.example .env
fi

# Generate strong passwords if empty
DB_PASS=$(openssl rand -hex 16)
sed -i "s/POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$DB_PASS/g" .env

# Build and Start Docker
echo "📦 Docker containers bouwen en starten..."
docker-compose up -d --build

echo "✅ Productie-omgeving succesvol gestart!"
echo "➡️ Open http://localhost:8000/setup in je browser om de installatie af te ronden."

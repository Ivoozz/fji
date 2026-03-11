# FixJeICT Enterprise

Een robuust, modern en snel ticketsysteem gebouwd voor IT-dienstverleners. Gemaakt met FastAPI, PostgreSQL, en een SEO-geoptimaliseerde "Liquid Glass" frontend.

![SaaS Ready](https://img.shields.io/badge/Status-Productie_Klaar-success)
![Docker](https://img.shields.io/badge/Deployment-Docker-blue)

## ✨ Kernfuncties

- **Interactieve First-Run Setup:** Volledige webgebaseerde configuratie (geen `.env` bestanden lokaal aanpassen).
- **Asynchrone E-mail & Routing:** Maakt gebruik van Resend API en Cloudflare Email Routing in de achtergrond (Non-blocking).
- **Beveiligde Opslag (AES):** Gevoelige API-sleutels worden versleuteld (Fernet) opgeslagen in de database.
- **Rollen en Rechten (RBAC):**
  - **Gebruiker:** Kan tickets aanmaken, reageren en bijlagen uploaden.
  - **Fixer:** IT-support medewerker. Kan alle tickets beheren en interne notities toevoegen, maar geen systeeminstellingen wijzigen.
  - **Admin:** Volledige systeemtoegang (inclusief API instellingen en gebruikersbeheer).
- **Bestandsbijlagen:** Naadloze file-uploads gekoppeld aan support tickets.
- **Liquid Glass UI:** Een moderne, responsieve en aantrekkelijke gebruikersinterface.

## 🚀 Snelle Installatie (Aanbevolen)

Run het volgende commando op een frisse Linux server (Debian/Ubuntu). Dit installeert Docker en start de database + applicatie automatisch op.

```bash
curl -fsSL https://raw.githubusercontent.com/Ivoozz/fji/main/install.sh | sudo bash
```

Navigeer vervolgens naar `http://<jouw-server-ip>:8000/setup` om de configuratie af te ronden.

## 🐳 Handmatige Docker Installatie

```bash
# 1. Clone repository
git clone https://github.com/Ivoozz/fji.git /opt/fji
cd /opt/fji

# 2. Start Productie Script
chmod +x start-production.sh
./start-production.sh
```

## 🛠 Tech Stack

- **Backend:** FastAPI (Python 3.11)
- **Database:** PostgreSQL (via SQLAlchemy ORM)
- **Frontend:** Jinja2 + Bootstrap 5 + Liquid Glass CSS
- **Encryptie:** Cryptography (Fernet)
- **Infrastructuur:** Docker & Docker Compose

## 🔐 Veiligheid & Authenticatie

- Magic Link login voor gebruikers en fixers (geen wachtwoorden onthouden).
- Admin heeft een sterk (gehasht) wachtwoord voor back-up toegang.
- Alle systeemsleutels zijn versleuteld met een eenmalig gegenereerde `ENCRYPTION_KEY`.

---
*Gemaakt voor en door IT-professionals.*

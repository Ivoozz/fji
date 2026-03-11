# FixJeICT Enterprise (LXC Native)

Een professioneel, modern en razendsnel ticketsysteem gebouwd voor IT-dienstverleners. Geoptimaliseerd voor directe uitvoering op **Debian LXC** containers voor maximale performance en minimale latency.

![Bare Metal Performance](https://img.shields.io/badge/Performance-Bare_Metal-success)
![Debian Ready](https://img.shields.io/badge/OS-Debian_12-blue)

## ✨ Kernfuncties

- **LXC Optimized:** Geen Docker nesting of overhead. Draait direct op Debian met Systemd en Nginx.
- **Interactieve First-Run Setup:** Volledige webgebaseerde configuratie (geen handmatige bewerking van configuratiebestanden nodig).
- **Beveiligde Opslag (AES):** Gevoelige API-sleutels (Resend, Cloudflare) worden versleuteld opgeslagen in de database.
- **Role-Based Access Control (RBAC):**
  - **Gebruiker:** Maakt tickets aan en uploadt bijlagen.
  - **Fixer (Support):** Beheert tickets en interne notities via het admin dashboard.
  - **Admin:** Volledige controle over systeeminstellingen en gebruikers.
- **Asynchrone Background Tasks:** E-mails en API-calls worden op de achtergrond verwerkt via FastAPI BackgroundTasks.
- **Bestandsbijlagen:** Directe ondersteuning voor screenshots en documenten bij tickets.

## 🚀 Snelle Installatie (One-Line)

Voer het volgende commando uit in een schone Debian 12 (of Trixie) LXC container als root:

```bash
curl -fsSL https://raw.githubusercontent.com/Ivoozz/fji/main/install.sh | sudo bash
```

Dit script doet automatisch het volgende:
1. Installeert Python 3, PostgreSQL en Nginx.
2. Configureert een lokale beveiligde database.
3. Zet een Systemd service op (`fji.service`).
4. Configureert Nginx als reverse proxy op poort 80.

## 🛠 Beheer via de terminal

Na installatie kun je de applicatie beheren met standaard Linux commando's:

```bash
# Status bekijken
systemctl status fji

# Herstarten
systemctl restart fji

# Logs inzien
journalctl -u fji -f
```

## 🛠 Tech Stack

- **Framework:** FastAPI (Python 3.11+)
- **Database:** PostgreSQL (Native)
- **Webserver:** Nginx (Reverse Proxy)
- **Service Manager:** Systemd
- **Frontend:** Jinja2, Bootstrap 5, Liquid Glass CSS

---
*Gebouwd voor IT-professionals die geen genoegen nemen met minder dan de beste performance.*

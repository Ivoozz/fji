# FixJeICT v2

Eenvoudig ticketsysteem voor IT-support, gebouwd met FastAPI.

## Snelle Installatie

```bash
# Download en run installer
curl -fsSL https://raw.githubusercontent.com/Ivoozz/fji/main/install.sh | sudo bash
```

Of handmatig:

```bash
# 1. Clone repository
git clone https://github.com/Ivoozz/fji.git /opt/fji
cd /opt/fji

# 2. Setup environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Configureer
cp .env.example .env
# Bewerk .env met je instellingen

# 4. Database initialiseren
mkdir -p data
python3 -c "from models import init_db; init_db()"

# 5. Start applicatie
uvicorn main:app --host 0.0.0.0 --port 5000
```

## Structuur

```
/
├── main.py              # FastAPI applicatie
├── models.py            # Database modellen
├── requirements.txt     # Dependencies
├── install.sh           # Installer script
├── .env.example         # Voorbeeld configuratie
├── templates/           # Jinja2 templates
│   ├── base.html
│   ├── index.html
│   ├── login.html
│   ├── tickets.html
│   ├── ticket_form.html
│   ├── ticket_detail.html
│   └── admin/
│       ├── login.html
│       ├── base.html
│       ├── dashboard.html
│       ├── tickets.html
│       ├── ticket_detail.html
│       ├── users.html
│       ├── user_detail.html
│       └── settings.html
└── static/              # CSS, JS, images
```

## Configuratie (.env)

```env
SECRET_KEY=your-secret-key
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-secure-password
DATABASE_URL=sqlite:///data/fixjeict.db
HOST=0.0.0.0
PORT=5000
```

## URLs

- **Website**: http://server-ip:5000/
- **Admin Login**: http://server-ip:5000/admin/login
- **API Docs**: http://server-ip:5000/docs

## Service Beheer

```bash
# Status bekijken
systemctl status fixjeict

# Restart
systemctl restart fixjeict

# Logs bekijken
journalctl -u fixjeict -f
```

## Default Credentials

- **Username**: admin
- **Password**: fixjeict123 (wijzig dit na installatie!)

## Requirements

- Python 3.8+
- SQLite (standaard) of PostgreSQL
- 512MB RAM minimum

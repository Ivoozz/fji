"""Email service using Resend API and Cloudflare Email Routing"""
import os

import re

import httpx
import resend

resend.api_key = os.getenv("RESEND_API_KEY", "")

CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "")
CLOUDFLARE_ZONE_ID = os.getenv("CLOUDFLARE_ZONE_ID", "")
CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
EMAIL_DOMAIN = os.getenv("EMAIL_DOMAIN", "fixjeict.nl")


def send_magic_link_email(to_email: str, magic_link_url: str, user_name: str):
    """Send magic link login email via Resend"""
    if not resend.api_key:
        print(f"[WARNING] RESEND_API_KEY not set. Magic link URL: {magic_link_url}")
        return None

    from_email = os.getenv("EMAIL_FROM", "FixJeICT <noreply@fixjeict.nl>")

    params = {
        "from": from_email,
        "to": [to_email],
        "subject": "Uw login link voor FixJeICT",
        "html": f"""
        <h2>Hallo {user_name},</h2>
        <p>Klik op de onderstaande link om in te loggen bij FixJeICT:</p>
        <p><a href="{magic_link_url}" style="background-color: #0d6efd; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px;">Inloggen</a></p>
        <p>Deze link is 24 uur geldig.</p>
        <p>Als u dit niet heeft aangevraagd, kunt u deze e-mail negeren.</p>
        <br>
        <p>Met vriendelijke groet,<br>FixJeICT Team</p>
        """,
    }

    try:
        email = resend.Emails.send(params)
        return email
    except Exception as e:
        print(f"[ERROR] Failed to send email via Resend: {e}")
        return None


def send_ticket_notification(to_email: str, ticket_number: str, subject: str, user_name: str):
    """Send ticket confirmation email"""
    if not resend.api_key:
        return None

    from_email = os.getenv("EMAIL_FROM", "FixJeICT <noreply@fixjeict.nl>")

    params = {
        "from": from_email,
        "to": [to_email],
        "subject": f"Ticket {ticket_number} aangemaakt - {subject}",
        "html": f"""
        <h2>Hallo {user_name},</h2>
        <p>Uw ticket is succesvol aangemaakt:</p>
        <ul>
            <li><strong>Ticket nummer:</strong> {ticket_number}</li>
            <li><strong>Onderwerp:</strong> {subject}</li>
        </ul>
        <p>Wij nemen zo snel mogelijk contact met u op.</p>
        <br>
        <p>Met vriendelijke groet,<br>FixJeICT Team</p>
        """,
    }

    try:
        return resend.Emails.send(params)
    except Exception as e:
        print(f"[ERROR] Failed to send ticket notification: {e}")
        return None


async def create_email_forwarding(user_email: str, username: str) -> dict:
    """
    Create a Cloudflare Email Routing rule to forward username@fixjeict.nl to user's private email.

    1. Register user's private email as destination address
    2. Create routing rule: username@fixjeict.nl -> user_email

    Returns dict with 'alias' (the @fixjeict.nl address) and 'status'.
    """
    if not all([CLOUDFLARE_API_TOKEN, CLOUDFLARE_ZONE_ID, CLOUDFLARE_ACCOUNT_ID]):
        print(f"[WARNING] Cloudflare API not configured. Skipping email forwarding for {user_email}")
        return {"alias": None, "status": "skipped", "error": "Cloudflare API not configured"}

    # Clean username for email alias (lowercase, only alphanumeric, dots, and hyphens)
    alias_local = username.lower().replace(" ", ".")
    alias_local = re.sub(r"[^a-z0-9.\-]", "", alias_local)
    alias_local = re.sub(r"\.{2,}", ".", alias_local)
    alias_local = alias_local.strip(".-")
    if not alias_local:
        alias_local = "user"
    alias_email = f"{alias_local}@{EMAIL_DOMAIN}"

    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient() as client:
        # Step 1: Add destination address (user's private email)
        try:
            dest_resp = await client.post(
                f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/email/routing/addresses",
                headers=headers,
                json={"email": user_email},
            )
            dest_data = dest_resp.json()
            # It's OK if destination already exists (Cloudflare error code 1032)
            if not dest_data.get("success"):
                errors = dest_data.get("errors", [])
                if not any(e.get("code") == 1032 for e in errors if isinstance(e, dict)):
                    print(f"[WARNING] Cloudflare destination address creation response: {dest_data}")
        except Exception as e:
            print(f"[ERROR] Failed to create destination address: {e}")

        # Step 2: Create routing rule
        try:
            rule_resp = await client.post(
                f"https://api.cloudflare.com/client/v4/zones/{CLOUDFLARE_ZONE_ID}/email/routing/rules",
                headers=headers,
                json={
                    "actions": [
                        {
                            "type": "forward",
                            "value": [user_email],
                        }
                    ],
                    "enabled": True,
                    "matchers": [
                        {
                            "field": "to",
                            "type": "literal",
                            "value": alias_email,
                        }
                    ],
                    "name": f"FixJeICT forwarding for {username}",
                    "priority": 0,
                },
            )
            rule_data = rule_resp.json()
            if rule_data.get("success"):
                return {"alias": alias_email, "status": "created"}
            else:
                # Rule may already exist
                errors = rule_data.get("errors", [])
                if any(e.get("code") == 1032 for e in errors if isinstance(e, dict)):
                    return {"alias": alias_email, "status": "exists"}
                print(f"[WARNING] Cloudflare rule creation response: {rule_data}")
                return {"alias": alias_email, "status": "error", "error": str(errors)}
        except Exception as e:
            print(f"[ERROR] Failed to create routing rule: {e}")
            return {"alias": alias_email, "status": "error", "error": str(e)}

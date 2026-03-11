"""Email service using Resend API and Cloudflare Email Routing"""
import re
import httpx
import resend

def send_magic_link_email(to_email: str, magic_link_url: str, user_name: str, resend_api_key: str, email_from: str):
    """Send magic link login email via Resend"""
    if not resend_api_key:
        print(f"[WARNING] resend_api_key not provided. Magic link URL: {magic_link_url}")
        return None

    resend.api_key = resend_api_key
    from_email = email_from or "FixJeICT <noreply@fixjeict.nl>"

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


def send_ticket_notification(to_email: str, ticket_number: str, subject: str, user_name: str, resend_api_key: str, email_from: str):
    """Send ticket confirmation email"""
    if not resend_api_key:
        return None

    resend.api_key = resend_api_key
    from_email = email_from or "FixJeICT <noreply@fixjeict.nl>"

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


async def create_email_forwarding(user_email: str, username: str, cf_token: str, cf_zone: str, cf_account: str, email_domain: str) -> dict:
    """
    Create a Cloudflare Email Routing rule to forward username@domain to user's private email.
    """
    if not all([cf_token, cf_zone, cf_account, email_domain]):
        print(f"[WARNING] Cloudflare API not fully configured. Skipping email forwarding for {user_email}")
        return {"alias": None, "status": "skipped", "error": "Cloudflare API not fully configured"}

    # Clean username for email alias
    alias_local = username.lower().replace(" ", ".")
    alias_local = re.sub(r"[^a-z0-9.\-]", "", alias_local)
    alias_local = re.sub(r"\.{2,}", ".", alias_local)
    alias_local = alias_local.strip(".-")
    if not alias_local:
        alias_local = "user"
    alias_email = f"{alias_local}@{email_domain}"

    headers = {
        "Authorization": f"Bearer {cf_token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient() as client:
        # Step 1: Add destination address
        try:
            dest_resp = await client.post(
                f"https://api.cloudflare.com/client/v4/accounts/{cf_account}/email/routing/addresses",
                headers=headers,
                json={"email": user_email},
            )
            dest_data = dest_resp.json()
            if not dest_data.get("success"):
                errors = dest_data.get("errors", [])
                if not any(e.get("code") == 1032 for e in errors if isinstance(e, dict)):
                    print(f"[WARNING] Cloudflare destination creation response: {dest_data}")
        except Exception as e:
            print(f"[ERROR] Failed to create destination address: {e}")

        # Step 2: Create routing rule
        try:
            rule_resp = await client.post(
                f"https://api.cloudflare.com/client/v4/zones/{cf_zone}/email/routing/rules",
                headers=headers,
                json={
                    "actions": [{"type": "forward", "value": [user_email]}],
                    "enabled": True,
                    "matchers": [{"field": "to", "type": "literal", "value": alias_email}],
                    "name": f"FixJeICT forwarding for {username}",
                    "priority": 0,
                },
            )
            rule_data = rule_resp.json()
            if rule_data.get("success"):
                return {"alias": alias_email, "status": "created"}
            else:
                errors = rule_data.get("errors", [])
                if any(e.get("code") == 1032 for e in errors if isinstance(e, dict)):
                    return {"alias": alias_email, "status": "exists"}
                print(f"[WARNING] Cloudflare rule creation response: {rule_data}")
                return {"alias": alias_email, "status": "error", "error": str(errors)}
        except Exception as e:
            print(f"[ERROR] Failed to create routing rule: {e}")
            return {"alias": alias_email, "status": "error", "error": str(e)}

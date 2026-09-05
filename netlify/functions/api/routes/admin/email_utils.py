"""Admin email utilities using SMTP config from environment / AppSetting."""
import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime


def _get_smtp_config():
    """Read SMTP config from env first, then AppSetting table."""
    from models import AppSetting
    def _e(key, setting_key, default=""):
        return os.getenv(key) or AppSetting.get(setting_key, default)

    return {
        "host": _e("SMTP_HOST", "smtp_host", "smtp.gmail.com"),
        "port": int(_e("SMTP_PORT", "smtp_port", "587")),
        "username": _e("SMTP_USERNAME", "smtp_username", ""),
        "password": os.getenv("SMTP_PASSWORD", ""),  # Never from DB
        "use_tls": (_e("SMTP_USE_TLS", "smtp_use_tls", "true")).lower() in ("true", "1", "yes"),
        "from_email": _e("SMTP_FROM_EMAIL", "smtp_from_email", ""),
        "from_name": _e("SMTP_FROM_NAME", "smtp_from_name", "Gracegifthub Gift Hub"),
    }


def send_email(to_email: str, subject: str, html_body: str) -> tuple[bool, str]:
    """Send an email. Returns (success, error_message)."""
    cfg = _get_smtp_config()
    if not cfg["username"] or not cfg["password"]:
        return False, "SMTP not configured (missing username or password)."

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{cfg['from_name']} <{cfg['from_email'] or cfg['username']}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    try:
        context = ssl.create_default_context()
        if cfg["port"] == 465:
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=context, timeout=15) as server:
                server.login(cfg["username"], cfg["password"])
                server.sendmail(msg["From"], [to_email], msg.as_string())
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as server:
                server.ehlo()
                if cfg["use_tls"]:
                    server.starttls(context=context)
                    server.ehlo()
                server.login(cfg["username"], cfg["password"])
                server.sendmail(msg["From"], [to_email], msg.as_string())
        return True, ""
    except smtplib.SMTPAuthenticationError:
        return False, "SMTP authentication failed. Check username/App Password."
    except smtplib.SMTPConnectError:
        return False, f"Could not connect to SMTP server {cfg['host']}:{cfg['port']}."
    except ssl.SSLError as e:
        return False, f"TLS/SSL error: {e}"
    except Exception as e:
        return False, str(e)


def send_new_order_notification(order, customer):
    """Send admin email when a new order is paid."""
    from models import AppSetting
    admin_email = os.getenv("ADMIN_EMAIL") or AppSetting.get("admin_email", "")
    if not admin_email:
        return
    items_html = "".join(
        f"<tr><td style='padding:4px 8px'>{i.product.name if i.product else 'Product'}</td>"
        f"<td style='padding:4px 8px;text-align:center'>{i.quantity}</td>"
        f"<td style='padding:4px 8px;text-align:right'>₦{float(i.unit_price):,.2f}</td></tr>"
        for i in order.items
    )
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto">
      <div style="background:#1a3a6b;color:#fff;padding:20px;border-radius:8px 8px 0 0">
        <h2 style="margin:0">🛍️ New Order Received</h2>
        <p style="margin:4px 0 0">Gracegifthub Gift Hub</p>
      </div>
      <div style="background:#f8f9fa;padding:20px">
        <table style="width:100%;border-collapse:collapse">
          <tr><td><strong>Order ID:</strong></td><td>#{order.id} ({order.order_ref})</td></tr>
          <tr><td><strong>Customer:</strong></td><td>{customer.full_name} &lt;{customer.email}&gt;</td></tr>
          <tr><td><strong>Amount:</strong></td><td>₦{float(order.total):,.2f}</td></tr>
          <tr><td><strong>Status:</strong></td><td>{order.status.upper()}</td></tr>
          <tr><td><strong>Date:</strong></td><td>{order.created_at.strftime('%Y-%m-%d %H:%M UTC')}</td></tr>
        </table>
        <h3>Items</h3>
        <table style="width:100%;border-collapse:collapse;background:#fff">
          <tr style="background:#1a3a6b;color:#fff">
            <th style="padding:6px 8px;text-align:left">Product</th>
            <th style="padding:6px 8px">Qty</th>
            <th style="padding:6px 8px;text-align:right">Price</th>
          </tr>
          {items_html}
        </table>
      </div>
      <div style="background:#eee;padding:10px;text-align:center;font-size:12px;color:#666;border-radius:0 0 8px 8px">
        © {datetime.utcnow().year} Gracegifthub Gift Hub — Admin Notification
      </div>
    </div>"""
    send_email(admin_email, f"New Order Received #{order.id} - Gracegifthub Gift Hub", html)

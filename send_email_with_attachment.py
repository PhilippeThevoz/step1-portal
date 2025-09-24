import smtplib
from email.message import EmailMessage

def send_email_with_attachment(
    smtp_cfg: dict,
    to_email: str,
    subject: str,
    body_text: str,
    attachment_filename: str,
    attachment_bytes: bytes,
):
    msg = EmailMessage()
    sender_name = smtp_cfg.get("sender_name") or ""
    sender_email = smtp_cfg.get("sender_email")
    from_header = f"{sender_name} <{sender_email}>" if sender_name else sender_email

    msg["From"] = from_header
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body_text)

    # Attach JSON (or any bytes)
    msg.add_attachment(
        attachment_bytes,
        maintype="application",
        subtype="octet-stream",
        filename=attachment_filename,
    )

    use_ssl = bool(smtp_cfg.get("use_ssl"))
    use_starttls = bool(smtp_cfg.get("use_starttls", True))
    host = smtp_cfg["host"]
    port = int(smtp_cfg["port"])
    username = smtp_cfg.get("username")
    password = smtp_cfg.get("password")

    if use_ssl:
        with smtplib.SMTP_SSL(host, port) as server:
            if username and password:
                server.login(username, password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port) as server:
            server.ehlo()
            if use_starttls:
                server.starttls()
                server.ehlo()
            if username and password:
                server.login(username, password)
            server.send_message(msg)

import os
import smtplib
from email.message import EmailMessage
import streamlit as st

def _smtp_cfg_from_env():
    return {
        "host": st.secrets.get("SMTP_HOST") or os.getenv("SMTP_HOST"),
        "port": int(st.secrets.get("SMTP_PORT", os.getenv("SMTP_PORT") or 587)),
        "username": st.secrets.get("SMTP_USERNAME") or os.getenv("SMTP_USERNAME"),
        "password": st.secrets.get("BLUEWIN_SMTP_PASSWORD") or os.getenv("BLUEWIN_SMTP_PASSWORD"),
        "sender_email": st.secrets.get("SENDER_EMAIL") or os.getenv("SENDER_EMAIL"),
        "sender_name": st.secrets.get("SENDER_NAME") or os.getenv("SENDER_NAME") or "Your Team",
        "use_ssl": str(st.secrets.get("SMTP_SSL") or os.getenv("SMTP_SSL") or "false").lower() == "true",
        "use_starttls": str(st.secrets.get("SMTP_STARTTLS") or os.getenv("SMTP_STARTTLS") or "true").lower() == "true",
    }

def send_plain_email(to_email: str, subject: str, body_text: str):
    cfg = _smtp_cfg_from_env()
    if not cfg["host"] or not cfg["sender_email"]:
        raise RuntimeError("SMTP not configured (SMTP_HOST / SENDER_EMAIL).")

    msg = EmailMessage()
    sender = f"{cfg['sender_name']} <{cfg['sender_email']}>"
    msg["From"] = sender
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body_text)

    if cfg["use_ssl"]:
        with smtplib.SMTP_SSL(cfg["host"], cfg["port"]) as s:
            if cfg["username"] and cfg["password"]:
                s.login(cfg["username"], cfg["password"])
            s.send_message(msg)
    else:
        with smtplib.SMTP(cfg["host"], cfg["port"]) as s:
            s.ehlo()
            if cfg["use_starttls"]:
                s.starttls(); s.ehlo()
            if cfg["username"] and cfg["password"]:
                s.login(cfg["username"], cfg["password"])
            s.send_message(msg)

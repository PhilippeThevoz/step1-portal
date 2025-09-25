import os, json, re, requests, smtplib, mimetypes
from email.message import EmailMessage
from datetime import datetime
from collections import OrderedDict
import streamlit as st

from services.supabase_client import get_client, get_bucket, get_users_object
from services.users import (
    load_onboarding_template,
    build_dynamic_record_from_inputs,
    append_user_record,
    save_single_user_file,
)
from clear_fields import clear_fields
from send_email_with_attachment import send_email_with_attachment  # still used for the single-file flows if you want
from send_sms_vonage import send_sms_vonage

# CERTUS ops from your root-level certus.py
from certus import (
    download_batch_zip,
    upload_zip_to_storage,
    activate_batch_put_activation,
    parse_qr_codes_in_storage,
)

T_CERTUS_PATH = "config/Template-CERTUS-Member.json"

def _slug(label: str) -> str:
    s = (label or "").strip().lower()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^a-z0-9_]", "_", s)
    return s

def _render_field(label: str, default: str):
    key = f"dyn_{_slug(label)}"
    low = label.lower()
    if "address" in low:
        return st.text_area(label, key=key, value=default or "")
    if "password" in low:
        return st.text_input(label, type="password", key=key, value="")
    return st.text_input(label, key=key, value=default or "")

# -------------------- helpers for CERTUS merge --------------------
def _ci_get(d: dict, *names: str) -> str:
    """Case-insensitive get across multiple possible labels."""
    # exact first
    for n in names:
        if n in d:
            v = d.get(n)
            return "" if v is None else str(v)
    # case-insensitive
    lowmap = { (k or "").strip().lower(): k for k in d.keys() }
    for n in names:
        k = lowmap.get((n or "").strip().lower())
        if k is not None:
            v = d.get(k)
            return "" if v is None else str(v)
    # fuzzy contains
    want = [ (n or "").strip().lower() for n in names if n ]
    for k, v in d.items():
        lk = (k or "").strip().lower()
        if any(tok in lk for tok in want):
            return "" if v is None else str(v)
    return ""

def _build_certus_row_and_id(captured: dict):
    """
    Returns (row_values_list, ghana_id_str) in the exact order required by your template.
    Order:
      Last Name, First Name, Birth Date, Ghana Card ID Number, Private Address,
      email, Mobile phone number, username, Public Key
    """
    last_name  = _ci_get(captured, "Last Name", "surname", "lastname", "name_last")
    first_name = _ci_get(captured, "First Name", "firstname", "given name", "givenname", "name_first")
    birth_date = _ci_get(captured, "Birth Date", "Birth Date (DD-MM-YYYY)", "birth_date", "date of birth", "dob")
    ghana_id   = _ci_get(captured, "Ghana Card ID Number", "ghana card id", "ghana_card_id")
    address    = _ci_get(captured, "Private Address", "Private Address (GhanaPostGPS)", "address")
    email      = _ci_get(captured, "email", "e-mail")
    mobile     = _ci_get(captured, "Mobile phone number", "mobile", "phone", "mobile phone number")
    username   = _ci_get(captured, "username", "user name")
    public_key = _ci_get(captured, "Public Key", "public key", "pubkey")

    row = [last_name, first_name, birth_date, ghana_id, address, email, mobile, username, public_key]
    row = [ (v or "").replace("\n"," ").strip() for v in row ]
    return row, ghana_id

def _load_text_from_storage(supabase, bucket: str, path: str) -> str:
    blob = supabase.storage.from_(bucket).download(path)
    if isinstance(blob, dict) and "data" in blob:
        blob = blob["data"]
    if not blob:
        raise FileNotFoundError(f"Template not found: {bucket}/{path}")
    try:
        return blob.decode("utf-8")
    except Exception:
        return str(blob)

def _merge_certus_template(template_text: str, row_values: list[str], ghana_id: str) -> dict:
    """
    Replace:
      1) <Last Name,First Name,Birth Date,Ghana Card ID Number,Private Address,email,Mobile phone number,username,Public Key>
         with a JSON snippet of quoted strings (to keep JSON valid):
         "LN","FN","..."
      2) "<GhanaCardID>" in "name":"<GhanaCardID>" with the actual ghana_id (no extra quotes).
    """
    row_json_inside_array = ",".join(json.dumps(v) for v in row_values)
    pattern_row = (
        r"<\s*Last Name\s*,\s*First Name\s*,\s*Birth Date\s*,\s*Ghana Card ID Number\s*,\s*Private Address\s*,\s*email\s*,\s*Mobile phone number\s*,\s*username\s*,\s*Public Key\s*>"
    )
    merged = re.sub(pattern_row, row_json_inside_array, template_text)

    pattern_gid = r"<\s*GhanaCardID\s*>"
    merged = re.sub(pattern_gid, ghana_id, merged)

    return json.loads(merged)

# -------------------- email with multiple attachments --------------------
def _send_email_with_attachments(to_email: str, subject: str, body_text: str, attachments: list[tuple[str, bytes, str]]):
    """
    attachments: list of (filename, data_bytes, content_type)
    SMTP config loaded from secrets/env (same keys you've used before).
    """
    host = st.secrets.get("SMTP_HOST") or os.getenv("SMTP_HOST")
    port = int(st.secrets.get("SMTP_PORT", os.getenv("SMTP_PORT") or 587))
    user = st.secrets.get("SMTP_USERNAME") or os.getenv("SMTP_USERNAME")
    pwd  = st.secrets.get("BLUEWIN_SMTP_PASSWORD") or os.getenv("BLUEWIN_SMTP_PASSWORD")
    sender = st.secrets.get("SENDER_EMAIL") or os.getenv("SENDER_EMAIL")
    sender_name = st.secrets.get("SENDER_NAME") or os.getenv("SENDER_NAME") or "Your Team"
    use_ssl = str(st.secrets.get("SMTP_SSL") or os.getenv("SMTP_SSL") or "false").lower() == "true"
    use_starttls = str(st.secrets.get("SMTP_STARTTLS") or os.getenv("SMTP_STARTTLS") or "true").lower() == "true"

    if not host or not sender:
        raise RuntimeError("SMTP is not configured (missing SMTP_HOST or SENDER_EMAIL).")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{sender_name} <{sender}>"
    msg["To"] = to_email
    msg.set_content(body_text)

    for filename, data, content_type in attachments:
        if not content_type:
            content_type, _ = mimetypes.guess_type(filename)
        if not content_type:
            content_type = "application/octet-stream"
        maintype, subtype = content_type.split("/", 1)
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)

    if use_ssl:
        with smtplib.SMTP_SSL(host, port) as s:
            if user and pwd:
                s.login(user, pwd)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port) as s:
            if use_starttls:
                s.starttls()
            if user and pwd:
                s.login(user, pwd)
            s.send_message(msg)

# -------------------- main view --------------------
def render(go):
    st.title("on-boarding (dynamic template)")
    st.caption("Fields are generated from Supabase: Test1/config/Template_onboarding_Member.json")

    supabase = get_client()
    bucket = get_bucket()
    users_object = get_users_object()

    # Load onboarding template (fields for the form)
    try:
        tmpl: OrderedDict = load_onboarding_template(supabase, bucket)
    except Exception as e:
        st.error(f"Cannot load onboarding template: {e}")
        st.stop()

    # ----- Dynamic form -----
    with st.form("onboarding_dynamic_form", clear_on_submit=False):
        st.subheader("Member information")
        captured: dict[str, str] = {}
        for label, default in tmpl.items():
            captured[label] = _render_field(label, str(default if default is not None else ""))

        filename = st.text_input("Filename (optional, e.g., member_2025-09-23.json)", key="dyn_filename")

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            save_clicked = st.form_submit_button("Save", type="prima_

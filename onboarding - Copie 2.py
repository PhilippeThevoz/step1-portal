import os
import json
from datetime import datetime
import streamlit as st
from supabase import create_client, Client

# ---- External helpers you already use ----
from send_sms_vonage import send_sms_vonage
from download_users_json import download_users_json
from remove_users_json_if_exists import remove_users_json_if_exists
from upload_users_json import upload_users_json
from load_users_as_list import load_users_as_list
from clear_fields import clear_fields
from exit_app import exit_app
from upload_single_user_json import upload_single_user_json
from send_email_with_attachment import send_email_with_attachment

# ------------------------------------------------------------------------------
# App config & Supabase client
# ------------------------------------------------------------------------------
st.set_page_config(page_title="Test Web Platform", page_icon="🧪", layout="centered")

@st.cache_resource(show_spinner=False)
def get_supabase() -> Client:
    url = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
    key = st.secrets.get("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        st.error("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.")
        st.stop()
    return create_client(url, key)

supabase = get_supabase()

# Storage config (adjust if needed)
BUCKET = "Test1"            # Supabase Storage bucket name
OBJECT_PATH = "Users.json"  # File path inside the bucket


# ------------------------------------------------------------------------------
# Simple router (Home / Signin / Onboarding)
# ------------------------------------------------------------------------------
if "view" not in st.session_state:
    st.session_state["view"] = "home"

def go(view: str):
    st.session_state["view"] = view
    st.rerun()

# ------------------------------------------------------------------------------
# Views
# ------------------------------------------------------------------------------

def view_home():
    st.title("Test Web Platform")
    st.write("Choose an action:")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Sign in your account", type="primary", use_container_width=True):
            go("signin")
    with c2:
        if st.button("Sign up", use_container_width=True):
            go("onboarding")

def view_signin():
    st.title("Sign in your account")
    with st.form("signin_form", clear_on_submit=False):
        username = st.text_input("Username (or email)")
        password = st.text_input("Password", type="password")
        method = st.radio("2-FA delivery method", ["email", "SMS"], horizontal=True, index=0)
        col = st.columns(2)
        submit = st.form_submit_button("Continue", type="primary")
        if submit:
            st.info("Authentication flow not implemented yet. (Coming next)")
    st.divider()
    if st.button("← Back to Home"):
        go("home")

def view_onboarding():
    # Header
    st.title("on-boarding")
    st.caption("Enter user data, then Save to append it to Users.json in your Supabase bucket.")

    # ---------- Form ----------
    with st.form("onboarding_form", clear_on_submit=False):
        st.subheader("User information")

        name = st.text_input("Name", key="name")
        birth_date = st.text_input("Birth Date", key="birth_date")
        nationality = st.text_input("Nationality", key="nationality")
        address = st.text_area("Address", key="address")
        email = st.text_input("email", key="email")
        mobile = st.text_input("mobile phone number", key="mobile")

        # optional single-file save name
        filename = st.text_input("Filename (optional, e.g., alice_2025-09-23.json)", key="filename")

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            save_clicked = st.form_submit_button("Save", type="primary")
        with c2:
            clear_clicked = st.form_submit_button("Clear all the fields")
        with c3:
            send_email_clicked = st.form_submit_button("Send email")
        with c4:
            send_sms_clicked = st.form_submit_button("Send SMS")

    # actions outside the form
    if clear_clicked:
        clear_fields()

    def build_record():
        return {
            "name": (name or "").strip(),
            "birth_date": (birth_date or "").strip(),
            "nationality": (nationality or "").strip(),
            "address": (address or "").strip(),
            "email": (email or "").strip(),
            "mobile": (mobile or "").strip(),
        }

    # ---------- SAVE ----------
    if save_clicked:
        missing = [fld for fld, val in {"Name": name, "email": email}.items() if not str(val).strip()]
        if missing:
            st.error("Please fill the required field(s): " + ", ".join(missing))
        else:
            try:
                record = build_record()

                # 1) Append to Users.json (list)
                users = load_users_as_list(supabase, BUCKET, OBJECT_PATH)
                users.append(record)
                remove_users_json_if_exists(supabase, BUCKET, OBJECT_PATH)
                upload_users_json(supabase, BUCKET, OBJECT_PATH, users)
                st.success("Saved to Supabase: Users.json")

                # 2) If filename is provided, also store this single record under that file
                filename_clean = (filename or "").strip()
                if filename_clean:
                    single_path = upload_single_user_json(supabase, BUCKET, filename_clean, record)
                    signed = supabase.storage.from_(BUCKET).create_signed_url(single_path, 60 * 60)
                    signed_url = signed.get("signedURL") if isinstance(signed, dict) else signed["signedURL"]
                    st.info(f"Saved separate JSON as: {single_path}")
                    st.link_button("⬇️ Download separate JSON (valid 1h)", signed_url)

            except Exception as e:
                st.error(f"Save failed: {e}")

    # ---------- SEND EMAIL ----------
    if 'send_email_clicked' in locals() and send_email_clicked:
        rec = build_record()
        if not rec["email"]:
            st.error("Please enter a valid email address before sending.")
        else:
            try:
                # Build the JSON for this single record
                json_str = json.dumps(rec, ensure_ascii=False, indent=2)
                attachment_name = (filename or "").strip()
                if not attachment_name:
                    base = (rec["name"] or "record").replace(" ", "_") or "record"
                    attachment_name = f"{base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                elif not attachment_name.lower().endswith(".json"):
                    attachment_name = f"{attachment_name}.json"

                subject = "Successful onboarding"
                body = (
                    "Dear Madam/Dear Sir,\n"
                    "Your on-boarding has been successful.\n"
                    "Please find below and enclosed your records.\n"
                    "Best Regards.\n"
                    "Your Team\n\n"
                    f"{json_str}\n"
                )

                # SMTP config
                smtp_cfg = {
                    "host": st.secrets.get("SMTP_HOST") or os.getenv("SMTP_HOST"),
                    "port": int(st.secrets.get("SMTP_PORT", os.getenv("SMTP_PORT") or 587)),
                    "username": st.secrets.get("SMTP_USERNAME") or os.getenv("SMTP_USERNAME"),
                    "password": st.secrets.get("BLUEWIN_SMTP_PASSWORD") or os.getenv("BLUEWIN_SMTP_PASSWORD"),
                    "sender_email": st.secrets.get("SENDER_EMAIL") or os.getenv("SENDER_EMAIL"),
                    "sender_name": st.secrets.get("SENDER_NAME") or os.getenv("SENDER_NAME") or "Your Team",
                    "use_ssl": str(st.secrets.get("SMTP_SSL") or os.getenv("SMTP_SSL") or "false").lower() == "true",
                    "use_starttls": str(st.secrets.get("SMTP_STARTTLS") or os.getenv("SMTP_STARTTLS") or "true").lower() == "true",
                }

                send_email_with_attachment(
                    smtp_cfg=smtp_cfg,
                    to_email=rec["email"],
                    subject=subject,
                    body_text=body,
                    attachment_filename=attachment_name,
                    attachment_bytes=json_str.encode("utf-8"),
                )
                st.success(f"Email sent to {rec['email']}")

            except Exception as e:
                st.error(f"Send email failed: {e}")

    # ---------- SEND SMS (Vonage) ----------
    if 'send_sms_clicked' in locals() and send_sms_clicked:
        rec = build_record()
        if not rec["mobile"]:
            st.error("Please enter a mobile number (e.g., +41...) before sending SMS.")
        else:
            try:
                api_key    = st.secrets.get("VONAGE_API_KEY")    or os.getenv("VONAGE_API_KEY")
                api_secret = st.secrets.get("VONAGE_API_SECRET") or os.getenv("VONAGE_API_SECRET")
                from_id    = st.secrets.get("VONAGE_SMS_FROM")   or os.getenv("VONAGE_SMS_FROM") or "Onboarding"

                if not api_key or not api_secret:
                    st.error("Missing VONAGE_API_KEY or VONAGE_API_SECRET in secrets/env.")
                else:
                    message = rec["name"] or "Hello from the onboarding portal"
                    msg_id = send_sms_vonage(api_key, api_secret, from_id, rec["mobile"], message)
                    st.success(f"SMS queued via Vonage (message-id: {msg_id})")
            except Exception as e:
                st.error(f"Send SMS failed: {e}")

    st.divider()
    # ---------- Download & Exit ----------
    d1, d2, d3 = st.columns(3)
    with d1:
        if st.button("Download"):
            content = download_users_json(supabase, BUCKET, OBJECT_PATH)
            if not content:
                st.warning("Users.json does not exist yet.")
            else:
                st.download_button(
                    label="⬇️ Download Users.json",
                    data=content,
                    file_name="Users.json",
                    mime="application/json",
                )
    with d2:
        if st.button("Exit"):
            exit_app()
    with d3:
        if st.button("← Back to Home"):
            go("home")


# ------------------------------------------------------------------------------
# Router dispatch
# ------------------------------------------------------------------------------
route = st.session_state["view"]
if route == "home":
    view_home()
elif route == "signin":
    view_signin()
else:
    # default to onboarding for unknown states
    view_onboarding()

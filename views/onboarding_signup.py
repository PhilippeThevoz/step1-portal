import os, json
from datetime import datetime
import streamlit as st
from services.users import hash_password_sha256, build_user_record, append_user_record, save_single_user_file
from services.supabase_client import get_client, get_bucket, get_users_object
from clear_fields import clear_fields
from send_email_with_attachment import send_email_with_attachment
from send_sms_vonage import send_sms_vonage

def render(go):
    st.title("on-boarding")
    st.caption("Enter user data, then Save to append it to Users.json in your Supabase bucket.")
    with st.form("onboarding_form", clear_on_submit=False):
        st.subheader("User information")
        name = st.text_input("Name", key="name")
        birth_date = st.text_input("Birth Date", key="birth_date")
        nationality = st.text_input("Nationality", key="nationality")
        address = st.text_area("Address", key="address")
        email = st.text_input("email", key="email")
        mobile = st.text_input("mobile phone number", key="mobile")
        username = st.text_input("username", key="username")
        password = st.text_input("password", type="password", key="password")
        repeat_password = st.text_input("repeat password", type="password", key="repeat_password")
        filename = st.text_input("Filename (optional, e.g., alice_2025-09-23.json)", key="filename")
        c1, c2, c3, c4 = st.columns(4)
        with c1: save_clicked = st.form_submit_button("Save", type="primary")
        with c2: clear_clicked = st.form_submit_button("Clear all the fields")
        with c3: send_email_clicked = st.form_submit_button("Send email")
        with c4: send_sms_clicked = st.form_submit_button("Send SMS")
    if clear_clicked:
        clear_fields()
        for k in ("username", "password", "repeat_password"):
            st.session_state.pop(k, None)
    supabase = get_client(); bucket = get_bucket(); users_object = get_users_object()
    def base_record():
        return build_user_record(name,birth_date,nationality,address,email,mobile,username)
    if save_clicked:
        missing = [fld for fld, val in {"Name": name, "email": email, "username": username, "password": password, "repeat password": repeat_password}.items() if not str(val or "").strip()]
        if missing:
            st.error("Please fill the required field(s): " + ", ".join(missing))
        elif password != repeat_password:
            st.error("Passwords do not match. Please re-enter them.")
        else:
            try:
                rec = base_record()
                rec["password_sha256"] = hash_password_sha256(password)
                append_user_record(supabase, bucket, users_object, rec)
                st.success("Saved to Supabase: Users.json")
                filename_clean = (filename or "").strip()
                if filename_clean:
                    single_path = save_single_user_file(supabase, bucket, filename_clean, rec)
                    signed = supabase.storage.from_(bucket).create_signed_url(single_path, 3600)
                    signed_url = signed.get("signedURL") if isinstance(signed, dict) else signed["signedURL"]
                    st.info(f"Saved separate JSON as: {single_path}")
                    st.link_button("⬇️ Download separate JSON (valid 1h)", signed_url)
            except Exception as e:
                st.error(f"Save failed: {e}")
    if 'send_email_clicked' in locals() and send_email_clicked:
        rec = base_record()
        if not rec["email"]:
            st.error("Please enter a valid email address before sending.")
        else:
            try:
                json_str = json.dumps(rec, ensure_ascii=False, indent=2)
                attachment_name = (filename or "").strip()
                if not attachment_name:
                    base = (rec["name"] or "record").replace(" ", "_") or "record"
                    attachment_name = f"{base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                elif not attachment_name.lower().endswith(".json"):
                    attachment_name = f"{attachment_name}.json"
                send_email_with_attachment(
                    smtp_cfg={
                        "host": st.secrets.get("SMTP_HOST") or os.getenv("SMTP_HOST"),
                        "port": int(st.secrets.get("SMTP_PORT", os.getenv("SMTP_PORT") or 587)),
                        "username": st.secrets.get("SMTP_USERNAME") or os.getenv("SMTP_USERNAME"),
                        "password": st.secrets.get("BLUEWIN_SMTP_PASSWORD") or os.getenv("BLUEWIN_SMTP_PASSWORD"),
                        "sender_email": st.secrets.get("SENDER_EMAIL") or os.getenv("SENDER_EMAIL"),
                        "sender_name": st.secrets.get("SENDER_NAME") or os.getenv("SENDER_NAME") or "Your Team",
                        "use_ssl": str(st.secrets.get("SMTP_SSL") or os.getenv("SMTP_SSL") or "false").lower() == "true",
                        "use_starttls": str(st.secrets.get("SMTP_STARTTLS") or os.getenv("SMTP_STARTTLS") or "true").lower() == "true",
                    },
                    to_email=rec["email"],
                    subject="Successful onboarding",
                    body_text=("Dear Madam/Dear Sir,\nYour on-boarding has been successful.\nPlease find below and enclosed your records.\nBest Regards.\nYour Team\n\n" + json_str + "\n"),
                    attachment_filename=attachment_name,
                    attachment_bytes=json_str.encode("utf-8"),
                )
                st.success(f"Email sent to {rec['email']}")
            except Exception as e:
                st.error(f"Send email failed: {e}")
    if 'send_sms_clicked' in locals() and send_sms_clicked:
        rec = base_record()
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
                    from send_sms_vonage import send_sms_vonage as _send
                    msg_id = _send(api_key, api_secret, from_id, rec["mobile"], rec["name"] or "Hello")
                    st.success(f"SMS queued via Vonage (message-id: {msg_id})")
            except Exception as e:
                st.error(f"Send SMS failed: {e}")
    st.divider()
    if st.button("← Back to Home"):
        go("home")

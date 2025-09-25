import os, json, re
from datetime import datetime
from collections import OrderedDict
import streamlit as st
from services.supabase_client import get_client, get_bucket, get_users_object
from services.users import load_onboarding_template, build_dynamic_record_from_inputs, append_user_record, save_single_user_file
from clear_fields import clear_fields
from send_email_with_attachment import send_email_with_attachment
from send_sms_vonage import send_sms_vonage

def _slug(label: str) -> str:
    s = (label or "").strip().lower()
    s = re.sub(r"\s+", "_", s); s = re.sub(r"[^a-z0-9_]", "_", s)
    return s

def _render_field(label: str, default: str):
    key = f"dyn_{_slug(label)}"; low = label.lower()
    if "address" in low: return st.text_area(label, key=key, value=default or "")
    if "password" in low: return st.text_input(label, type="password", key=key, value="")
    return st.text_input(label, key=key, value=default or "")

def render(go):
    st.title("on-boarding (dynamic template)")
    st.caption("Fields are generated from Supabase: Test1/config/Template_onboarding_Member.json")
    supabase = get_client(); bucket = get_bucket(); users_object = get_users_object()
    try:
        tmpl: OrderedDict = load_onboarding_template(supabase, bucket)
    except Exception as e:
        st.error(f"Cannot load onboarding template: {e}"); st.stop()

    with st.form("onboarding_dynamic_form", clear_on_submit=False):
        st.subheader("Member information")
        captured: dict[str, str] = {}
        for label, default in tmpl.items():
            captured[label] = _render_field(label, str(default if default is not None else ""))
        filename = st.text_input("Filename (optional, e.g., member_2025-09-23.json)", key="dyn_filename")
        c1, c2, c3, c4 = st.columns(4)
        with c1: save_clicked = st.form_submit_button("Save", type="primary")
        with c2: clear_clicked = st.form_submit_button("Clear all the fields")
        with c3: send_email_clicked = st.form_submit_button("Send email")
        with c4: send_sms_clicked = st.form_submit_button("Send SMS")

    if clear_clicked:
        clear_fields()
        for label in tmpl.keys():
            st.session_state.pop(f"dyn_{_slug(label)}", None)
        st.session_state.pop("dyn_filename", None)

    def _record_for_email():
        filtered = {k: v for k, v in captured.items() if "password" not in k.lower()}
        return json.dumps(filtered, ensure_ascii=False, indent=2)

    if save_clicked:
        try:
            record, username, err = build_dynamic_record_from_inputs(captured)
            if err: st.error(err)
            else:
                append_user_record(supabase, bucket, users_object, record)
                st.success("Saved to Supabase: Users.json")
                filename_clean = (filename or "").strip()
                if filename_clean:
                    single_path = save_single_user_file(supabase, bucket, filename_clean, record)
                    signed = supabase.storage.from_(bucket).create_signed_url(single_path, 3600)
                    signed_url = signed.get("signedURL") if isinstance(signed, dict) else signed["signedURL"]
                    st.info(f"Saved separate JSON as: {single_path}")
                    st.link_button("⬇️ Download separate JSON (valid 1h)", signed_url)
        except Exception as e:
            st.error(f"Save failed: {e}")

    if 'send_email_clicked' in locals() and send_email_clicked:
        try:
            json_str = _record_for_email()
            # find an email-like field
            to_email = ""
            for k, v in captured.items():
                if "email" in k.lower(): to_email = v.strip(); break
            if not to_email: st.error("No email field found in template or it's empty.")
            else:
                attach_name = (filename or "").strip() or f"record_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                if not attach_name.lower().endswith(".json"): attach_name += ".json"
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
                    to_email=to_email,
                    subject="Successful onboarding",
                    body_text=("Dear Madam/Dear Sir,\nYour on-boarding has been successful.\nPlease find below and enclosed your records.\nBest Regards.\nYour Team\n\n" + json_str + "\n"),
                    attachment_filename=attach_name,
                    attachment_bytes=json_str.encode("utf-8"),
                )
                st.success(f"Email sent to {to_email}")
        except Exception as e:
            st.error(f"Send email failed: {e}")

    if 'send_sms_clicked' in locals() and send_sms_clicked:
        try:
            to_msisdn = ""
            for k, v in captured.items():
                if "mobile" in k.lower() or "phone" in k.lower(): to_msisdn = v.strip(); break
            if not to_msisdn: st.error("No mobile/phone field found in template or it's empty.")
            else:
                api_key    = st.secrets.get("VONAGE_API_KEY")    or os.getenv("VONAGE_API_KEY")
                api_secret = st.secrets.get("VONAGE_API_SECRET") or os.getenv("VONAGE_API_SECRET")
                from_id    = st.secrets.get("VONAGE_SMS_FROM")   or os.getenv("VONAGE_SMS_FROM") or "Onboarding"
                if not api_key or not api_secret: st.error("Missing VONAGE_API_KEY or VONAGE_API_SECRET in secrets/env.")
                else:
                    from send_sms_vonage import send_sms_vonage as _send
                    name_fields = [k for k in captured.keys() if "name" in k.lower()]
                    msg_text = " ".join([captured[k] for k in name_fields]).strip() if name_fields else "Hello from the onboarding portal"
                    msg_id = _send(api_key, api_secret, from_id, to_msisdn, msg_text)
                    st.success(f"SMS queued via Vonage (message-id: {msg_id})")
        except Exception as e:
            st.error(f"Send SMS failed: {e}")

    st.divider()
    if st.button("← Back to Home"): go("home")

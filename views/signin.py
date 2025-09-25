import os, secrets, streamlit as st
from services.users import list_users, find_user_by_username, verify_password_sha256
from services.supabase_client import get_client, get_bucket, get_users_object
from send_plain_email import send_plain_email
from send_sms_vonage import send_sms_vonage

def _send_2fa_code(user_rec: dict, method: str, code: str) -> str:
    if method == "email":
        to_email = (user_rec.get("email") or "")
        if not to_email:
            for k, v in user_rec.items():
                if "email" in str(k).lower(): to_email = str(v or ""); break
        to_email = to_email.strip()
        if not to_email: raise RuntimeError("No email on record for this user.")
        send_plain_email(to_email=to_email, subject="Your login code", body_text=f"Your 2FA code is: {code}")
        return f"email {to_email}"
    to_msisdn = (user_rec.get("mobile") or "")
    if not to_msisdn:
        for k, v in user_rec.items():
            if "mobile" in str(k).lower() or "phone" in str(k).lower(): to_msisdn = str(v or ""); break
    to_msisdn = to_msisdn.strip()
    if not to_msisdn: raise RuntimeError("No mobile number on record for this user.")
    api_key    = st.secrets.get("VONAGE_API_KEY")    or os.getenv("VONAGE_API_KEY")
    api_secret = st.secrets.get("VONAGE_API_SECRET") or os.getenv("VONAGE_API_SECRET")
    from_id    = st.secrets.get("VONAGE_SMS_FROM")   or os.getenv("VONAGE_SMS_FROM") or "Login"
    if not api_key or not api_secret: raise RuntimeError("Missing VONAGE_API_KEY / VONAGE_API_SECRET.")
    send_sms_vonage(api_key, api_secret, from_id, to_msisdn, f"Your 2FA code is: {code}")
    return f"SMS {to_msisdn}"

def render(go):
    st.title("Sign in your account")
    if "signin_stage" not in st.session_state: st.session_state["signin_stage"] = "credentials"
    if "pending_2fa" not in st.session_state: st.session_state["pending_2fa"] = None
    supabase = get_client(); bucket = get_bucket(); users_object = get_users_object()
    if st.session_state["signin_stage"] == "credentials":
        with st.form("signin_form", clear_on_submit=False):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            method = st.radio("2-FA delivery method", ["email", "SMS"], horizontal=True, index=0)
            submitted = st.form_submit_button("Continue", type="primary")
        if submitted:
            try: users = list_users(supabase, bucket, users_object)
            except Exception as e: st.error(f"Could not read Users.json: {e}"); users = []
            user_rec = find_user_by_username(users, username)
            if not user_rec: st.error("Unknown username."); st.stop()
            stored_hash = user_rec.get("password_sha256")
            if not stored_hash: st.error("This account has no password set yet."); st.stop()
            if not verify_password_sha256(password, stored_hash): st.error("Invalid password."); st.stop()
            code = f"{secrets.randbelow(10000):04d}"
            try:
                sent_to = _send_2fa_code(user_rec, method, code)
                st.session_state["pending_2fa"] = {"username": username,"method": method,"code": code,"contact": sent_to.split()[-1],"user": user_rec}
                st.session_state["signin_stage"] = "verify"; st.success(f"Code sent via {sent_to}."); st.rerun()
            except Exception as e: st.error(f"Could not send the 2FA code: {e}")
    else:
        pending = st.session_state.get("pending_2fa") or {}
        st.write(f"Enter the 4-digit code sent via **{pending.get('method','?')}** to **{pending.get('contact','?')}**.")
        with st.form("verify_form", clear_on_submit=False):
            code_input = st.text_input("4-digit code", max_chars=4)
            verify = st.form_submit_button("Verify", type="primary")
        if verify:
            if (code_input or "").strip() == (pending.get("code") or ""):
                st.success("✅ Login successful."); st.session_state["logged_in"] = True; st.session_state["user"] = pending.get("user")
                st.session_state["pending_2fa"] = None; st.session_state["signin_stage"] = "credentials"; go("dashboard")
            else: st.error("Incorrect code. Please try again.")
        st.divider()
        if st.button("← Back to Home"): st.session_state["pending_2fa"] = None; st.session_state["signin_stage"] = "credentials"; go("home")

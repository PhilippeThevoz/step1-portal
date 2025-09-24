import os
import json
import hashlib
import secrets
from datetime import datetime
import streamlit as st
import requests
from supabase import create_client, Client

# ---- External helpers ----
from send_sms_vonage import send_sms_vonage
from send_plain_email import send_plain_email
from download_users_json import download_users_json
from remove_users_json_if_exists import remove_users_json_if_exists
from upload_users_json import upload_users_json
from load_users_as_list import load_users_as_list
from clear_fields import clear_fields
from exit_app import exit_app
from upload_single_user_json import upload_single_user_json
from send_email_with_attachment import send_email_with_attachment

# ----------------------------------------------------------------------------
# App config & Supabase client
# ----------------------------------------------------------------------------
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

# Storage config
BUCKET = os.getenv("SUPABASE_BUCKET") or "Test1"            # Supabase Storage bucket name
OBJECT_PATH = os.getenv("SUPABASE_USERS_OBJECT") or "Users.json"  # File path inside the bucket

# ----------------------------------------------------------------------------
# Simple router (Home / Signin / Onboarding)
# ----------------------------------------------------------------------------
if "view" not in st.session_state:
    st.session_state["view"] = "home"

def go(view: str):
    st.session_state["view"] = view
    st.rerun()

# ----------------------------------------------------------------------------
# Views
# ----------------------------------------------------------------------------
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

    # mini-router for this view: 'credentials' -> 'verify'
    if "signin_stage" not in st.session_state:
        st.session_state["signin_stage"] = "credentials"
    if "pending_2fa" not in st.session_state:
        st.session_state["pending_2fa"] = None

    # ---------------- Stage 1: enter credentials ----------------
    if st.session_state["signin_stage"] == "credentials":
        with st.form("signin_form", clear_on_submit=False):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            method = st.radio("2-FA delivery method", ["email", "SMS"], horizontal=True, index=0)
            submitted = st.form_submit_button("Continue", type="primary")

        if submitted:
            # 1) Read Users.json from Supabase
            try:
                users = load_users_as_list(supabase, BUCKET, OBJECT_PATH)
            except Exception as e:
                st.error(f"Could not read Users.json: {e}")
                users = []

            # 2) Find record by username (case-insensitive)
            uname = (username or "").strip().lower()
            user_rec = next((u for u in users if (u.get("username") or "").strip().lower() == uname), None)
            if not user_rec:
                st.error("Unknown username.")
                st.stop()

            # 3) Check SHA-256(password)
            stored_hash = user_rec.get("password_sha256")
            if not stored_hash:
                st.error("This account has no password set yet.")
                st.stop()

            given_hash = hashlib.sha256((password or "").encode("utf-8")).hexdigest()
            if given_hash != stored_hash:
                st.error("Invalid password.")
                st.stop()

            # 4) Generate a 4-digit code
            code = f"{secrets.randbelow(10000):04d}"

            # 5) Send via email or SMS
            try:
                if method == "email":
                    to_email = (user_rec.get("email") or "").strip()
                    if not to_email:
                        st.error("No email on record for this user.")
                        st.stop()
                    send_plain_email(
                        to_email=to_email,
                        subject="Your login code",
                        body_text=f"Your 2FA code is: {code}",
                    )
                    sent_to = f"email {to_email}"
                else:
                    to_msisdn = (user_rec.get("mobile") or "").strip()
                    if not to_msisdn:
                        st.error("No mobile number on record for this user.")
                        st.stop()

                    api_key    = st.secrets.get("VONAGE_API_KEY")    or os.getenv("VONAGE_API_KEY")
                    api_secret = st.secrets.get("VONAGE_API_SECRET") or os.getenv("VONAGE_API_SECRET")
                    from_id    = st.secrets.get("VONAGE_SMS_FROM")   or os.getenv("VONAGE_SMS_FROM") or "Login"

                    if not api_key or not api_secret:
                        st.error("Missing VONAGE_API_KEY / VONAGE_API_SECRET.")
                        st.stop()

                    send_sms_vonage(api_key, api_secret, from_id, to_msisdn, f"Your 2FA code is: {code}")
                    sent_to = f"SMS {to_msisdn}"

                # keep 2FA state and switch stage
                st.session_state["pending_2fa"] = {
                    "username": user_rec.get("username"),
                    "method": method,
                    "code": code,
                    "contact": user_rec.get("email") if method == "email" else user_rec.get("mobile"),
                    "user": user_rec,
                }
                st.session_state["signin_stage"] = "verify"
                st.success(f"Code sent via {sent_to}.")
                st.rerun()

            except Exception as e:
                st.error(f"Could not send the 2FA code: {e}")

    # ---------------- Stage 2: verify the code ----------------
    else:
        pending = st.session_state.get("pending_2fa") or {}
        st.write(f"Enter the 4-digit code sent via **{pending.get('method','?')}** to **{pending.get('contact','?')}**.")
        with st.form("verify_form", clear_on_submit=False):
            code_input = st.text_input("4-digit code", max_chars=4)
            verify = st.form_submit_button("Verify", type="primary")

        if verify:
            if (code_input or "").strip() == (pending.get("code") or ""):
                st.success("✅ Login successful.")
                st.session_state["logged_in"] = True
                st.session_state["user"] = pending.get("user")
                # clear 2FA state
                st.session_state["pending_2fa"] = None
                st.session_state["signin_stage"] = "credentials"
                # NEW: jump to the dashboard view
                st.session_state["view"] = "dashboard"
                st.rerun()
            else:
                st.error("Incorrect code. Please try again.")

        st.divider()
        if st.button("← Back to Home"):
            st.session_state["pending_2fa"] = None
            st.session_state["signin_stage"] = "credentials"
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

        # signup credentials
        username = st.text_input("username", key="username")
        password = st.text_input("password", type="password", key="password")
        repeat_password = st.text_input("repeat password", type="password", key="repeat_password")

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
        for k in ("username", "password", "repeat_password"):
            st.session_state.pop(k, None)

    def build_record_base():
        return {
            "name": (name or "").strip(),
            "birth_date": (birth_date or "").strip(),
            "nationality": (nationality or "").strip(),
            "address": (address or "").strip(),
            "email": (email or "").strip(),
            "mobile": (mobile or "").strip(),
            "username": (username or "").strip(),
        }

    # ---------- SAVE ----------
    if save_clicked:
        missing = [fld for fld, val in {
            "Name": name, "email": email, "username": username, "password": password, "repeat password": repeat_password
        }.items() if not str(val or "").strip()]
        if missing:
            st.error("Please fill the required field(s): " + ", ".join(missing))
        elif password != repeat_password:
            st.error("Passwords do not match. Please re-enter them.")
        else:
            try:
                password_sha256 = hashlib.sha256(password.encode("utf-8")).hexdigest()
                record = build_record_base()
                record["password_sha256"] = password_sha256

                # 1) Append to Users.json (list)
                users = load_users_as_list(supabase, BUCKET, OBJECT_PATH)
                users.append(record)
                remove_users_json_if_exists(supabase, BUCKET, OBJECT_PATH)
                upload_users_json(supabase, BUCKET, OBJECT_PATH, users)
                st.success("Saved to Supabase: Users.json")

                # 2) optional per-file save
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
        rec = build_record_base()
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

                subject = "Successful onboarding"
                body = (
                    "Dear Madam/Dear Sir,\n"
                    "Your on-boarding has been successful.\n"
                    "Please find below and enclosed your records.\n"
                    "Best Regards.\n"
                    "Your Team\n\n"
                    f"{json_str}\n"
                )

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
                    subject=subject,
                    body_text=body,
                    attachment_filename=attachment_name,
                    attachment_bytes=json_str.encode("utf-8"),
                )
                st.success(f"Email sent to {rec['email']}")

            except Exception as e:
                st.error(f"Send email failed: {e}")

    # ---------- SEND SMS ----------
    if 'send_sms_clicked' in locals() and send_sms_clicked:
        rec = build_record_base()
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

def view_dashboard():
    user = st.session_state.get("user") or {}
    st.title("Welcome")
    st.caption(f"Logged in as: {user.get('username','(unknown)')}")

    c1, c2 = st.columns(2)
    with c1:
        logout = st.button("Logout", use_container_width=True)
    with c2:
        create_certus = st.button("Create CERTUS", type="primary", use_container_width=True)

    # --- Logout ---
    if logout:
        # minimal, safe reset
        for k in ("logged_in", "user", "pending_2fa"):
            st.session_state.pop(k, None)
        st.session_state["view"] = "home"
        st.rerun()

    # --- Create CERTUS ---
# --- Create CERTUS ---
    if create_certus:
        try:
            # 1) Download CERTUS-Test.json from Supabase bucket
            object_name = "CERTUS-Test.json"
            raw = supabase.storage.from_(BUCKET).download(object_name)
            if isinstance(raw, dict) and "data" in raw:
                raw = raw["data"]
            if not raw:
                st.error(f"{object_name} not found in bucket '{BUCKET}'.")
                st.stop()

            # 2) Parse into certus_content
            try:
                certus_content = json.loads(raw.decode("utf-8"))
            except Exception:
                certus_content = json.loads(raw)

            st.subheader("CERTUS content (preview)")
            st.json(certus_content, expanded=False)

            # 3) Call CERTUS API
            base = st.secrets.get("CERTUS_API_PATH") or os.getenv("CERTUS_API_PATH")
            key  = st.secrets.get("CERTUS_API_KEY")  or os.getenv("CERTUS_API_KEY")
            if not base or not key:
                st.error("Missing CERTUS_API_PATH or CERTUS_API_KEY environment variables.")
                st.stop()

            url = base.rstrip("/") + "/batches/json"
            headers = {
                "accept": "application/json",
                "issuer-impersonate": "utopia",
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            }

            resp = requests.post(url, headers=headers, json=certus_content, timeout=60)

            # Parse response into certus_output
            try:
                certus_output = resp.json()
            except Exception:
                certus_output = resp.text

            # Extract batchId if present
            CERTUS_Batch_ID = None
            try:
                payload = certus_output if isinstance(certus_output, dict) else json.loads(certus_output)
                if isinstance(payload, dict):
                    CERTUS_Batch_ID = payload.get("batchId") or payload.get("batch_id")
            except Exception:
                pass

            st.subheader("-------- CERTUS API response")
            if isinstance(certus_output, (dict, list)):
                st.json(certus_output, expanded=False)
            else:
                st.code(certus_output)

            if CERTUS_Batch_ID:
                st.info(f"CERTUS_Batch_ID: {CERTUS_Batch_ID}")
                st.session_state["CERTUS_Batch_ID"] = CERTUS_Batch_ID

            if resp.ok:
                st.success("-------- CERTUS batch created successfully.")
            else:
                st.error(f"CERTUS API error: HTTP {resp.status_code}")

        except Exception as e:
            st.error(f"Create CERTUS failed: {e}")
            
            
#
#-------- Add below the API call to download a batch --------

#-------- Add below the API call to download a batch --------

    # Only proceed if we have a CERTUS_Batch_ID from the previous step
    CERTUS_Batch_ID = st.session_state.get("CERTUS_Batch_ID")
    if CERTUS_Batch_ID:
        import io, zipfile, mimetypes  # local imports to avoid changing your global header

        st.subheader("Download CERTUS batch")
        if st.button("Download batch ZIP & upload to Supabase", use_container_width=True):
            try:
                # Build the download request
                key = st.secrets.get("CERTUS_API_KEY") or os.getenv("CERTUS_API_KEY")
                if not key:
                    st.error("Missing CERTUS_API_KEY environment/secret value.")
                    st.stop()

                dl_url = f"https://dm-api.pp.certusdoc.com/api/v1/batches/{CERTUS_Batch_ID}/download"
                headers = {
                    "accept": "*/*",
                    "issuer-impersonate": "utopia",
                    "Authorization": f"Bearer {key}",
                }

                # Call the CERTUS download API (should return a ZIP)
                r = requests.get(dl_url, headers=headers, timeout=180)
                if not r.ok:
                    st.error(f"Download API error: HTTP {r.status_code}")
                    st.stop()

                zip_bytes = r.content

                # Offer the ZIP for direct download in the UI
                st.download_button(
                    label="⬇️ Download CERTUS ZIP",
                    data=zip_bytes,
                    file_name=f"{CERTUS_Batch_ID}.zip",
                    mime="application/zip",
                )

                # Unzip in-memory and upload files to Supabase bucket (Test1)
                try:
                    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
                except zipfile.BadZipFile:
                    st.error("Downloaded file is not a valid ZIP.")
                    st.stop()

                uploaded = []
                for member in zf.infolist():
                    if member.is_dir():
                        continue
                    data = zf.read(member)  # bytes of the extracted file

                    # Store under a prefix per batch: Test1/CERTUS/<batch>/...
                    object_path = f"CERTUS/{CERTUS_Batch_ID}/{member.filename}".replace("\\", "/")
                    content_type, _ = mimetypes.guess_type(member.filename)
                    opts = {"contentType": content_type or "application/octet-stream"}

                    # Best-effort remove if it already exists (prevents upsert quirks)
                    try:
                        supabase.storage.from_(BUCKET).remove([object_path])
                    except Exception:
                        pass

                    supabase.storage.from_(BUCKET).upload(object_path, data, opts)
                    uploaded.append(object_path)

                st.success(f"Uploaded {len(uploaded)} file(s) to Supabase at '{BUCKET}/CERTUS/{CERTUS_Batch_ID}/'.")

            except Exception as e:
                st.error(f"Batch download/upload failed: {e}")
    else:
        st.info("Create a CERTUS batch first to enable download.")
        
#
#--------------- activate the batch

# Only proceed if we have a CERTUS_Batch_ID
    print("CERTUS_Batch_ID : ",CERTUS_Batch_ID)
    if CERTUS_Batch_ID:
        st.subheader("Activate CERTUS batch")
        if st.button("Activate batch", use_container_width=True):
            try:
                key = st.secrets.get("CERTUS_API_KEY") or os.getenv("CERTUS_API_KEY")
                if not key:
                    st.error("Missing CERTUS_API_KEY environment/secret value.")
                    st.stop()

                # API call (as requested)
                dl_url = f"https://dm-api.pp.certusdoc.com/api/v1/batches/{CERTUS_Batch_ID}/activation"
                headers = {
                    "accept": "application/json",
                    "issuer-impersonate": "utopia",
                    "Authorization": f"Bearer {key}",
                }

                # Most APIs use POST for activate; fall back to GET if needed
                resp = requests.post(dl_url, headers=headers, timeout=60)
                if resp.status_code == 405:  # Method Not Allowed -> try GET
                    resp = requests.get(dl_url, headers=headers, timeout=60)

                if resp.ok:
                    st.success("Activation has been successful")
                else:
                    st.error(f"Activation failed: HTTP {resp.status_code} — {resp.text}")

            except Exception as e:
                st.error(f"Activation error: {e}")
    else:
        st.info("No CERTUS_Batch_ID available. Create a batch first.")

# ----------------------------------------------------------------------------
# Router dispatch
# ----------------------------------------------------------------------------

route = st.session_state["view"]
if route == "home":
    view_home()
elif route == "signin":
    view_signin()
elif route == "dashboard":   # NEW
    # protect this view
    if st.session_state.get("logged_in"):
        view_dashboard()
    else:
        st.warning("Please sign in first.")
        view_signin()
else:
    view_onboarding()

import os
import json
from datetime import datetime, timezone, date

import streamlit as st
from supabase import create_client, Client
from streamlit.components.v1 import html as st_html

# ----------------------------- App setup -----------------------------
st.set_page_config(page_title="on-boarding", page_icon="🧾", layout="centered")
st.title("on-boarding")
st.caption("Enter user data, then Save to append it to Users.json in your Supabase bucket.")

# ----------------------------- Supabase ------------------------------
@st.cache_resource(show_spinner=False)
def get_supabase() -> Client:
    url = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
    key = st.secrets.get("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        st.error(
            "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.\n"
            "Add them in .streamlit/secrets.toml (local) or as Render environment variables (prod)."
        )
        st.stop()
    return create_client(url, key)

supabase = get_supabase()

# Bucket and file path (adjust if your bucket name differs)
BUCKET = "Test1"          # <-- bucket name
OBJECT_PATH = "Users.json"  # <-- file name inside the bucket

# ----------------------------- Helpers -------------------------------
def _download_users_json() -> bytes | None:
    """
    Returns file bytes if Users.json exists, else None.
    """
    try:
        blob = supabase.storage.from_(BUCKET).download(OBJECT_PATH)
        # supabase-py v2 returns bytes; if dict, adapt accordingly
        if isinstance(blob, (bytes, bytearray)):
            return bytes(blob)
        # Some client versions return dict with 'data' bytes
        if isinstance(blob, dict) and "data" in blob:
            return blob["data"]
        return None
    except Exception:
        return None

def _upload_users_json(data: list[dict]) -> None:
    """
    Uploads (overwrites) Users.json with the provided list of user records.
    """
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    supabase.storage.from_(BUCKET).upload(
        OBJECT_PATH,
        payload,
        {
            "content-type": "application/json; charset=utf-8",
            "upsert": True,  # allow overwrite if the file already exists
        },
    )

def _load_users_as_list() -> list[dict]:
    """
    Loads Users.json as a Python list. If file is missing or invalid, returns [].
    """
    raw = _download_users_json()
    if not raw:
        return []
    try:
        obj = json.loads(raw.decode("utf-8"))
        if isinstance(obj, list):
            return obj
        # If someone manually created a non-list JSON, wrap it for safety
        return [obj]
    except Exception:
        return []

def _serialize_date(d: date | None) -> str | None:
    return d.isoformat() if isinstance(d, date) else None

def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _clear_fields():
    for k in ("name", "birth_date", "nationality", "address", "email", "mobile"):
        if k in st.session_state:
            del st.session_state[k]
    st.success("All fields cleared.")
    st.rerun()

def _exit_app():
    # Best effort: attempt to close the browser tab (will only work if opened by script)
    st_html(
        """
        <script>
          try { window.close(); } catch (e) {}
        </script>
        """,
        height=0,
    )
    # Fallback UX if the browser blocks window.close()
    st.success("You can now close this tab/window.")
    st.stop()

# ----------------------------- Form UI -------------------------------
with st.form("onboarding_form", clear_on_submit=False):
    st.subheader("User information")

    name = st.text_input("Name", key="name")
    birth_date = st.date_input("Birth Date", key="birth_date", value=None, format="YYYY-MM-DD")
    nationality = st.text_input("Nationality", key="nationality")
    address = st.text_area("Address", key="address", placeholder="Street, ZIP, City, Country")
    email = st.text_input("email", key="email", placeholder="name@example.com")
    mobile = st.text_input("mobile phone number", key="mobile", placeholder="+41 79 123 45 67")

    # Buttons row inside the form for Save / Clear
    c1, c2 = st.columns(2)
    with c1:
        save_clicked = st.form_submit_button("Save", type="primary")
    with c2:
        clear_clicked = st.form_submit_button("Clear all the fields")

# Process form buttons
if clear_clicked:
    _clear_fields()

if save_clicked:
    # Minimal validation
    missing = []
    if not name.strip():
        missing.append("Name")
    if not email.strip():
        missing.append("email")
    if missing:
        st.error(f"Please fill the required field(s): {', '.join(missing)}.")
    else:
        try:
            # Load existing list (or empty), append new record, overwrite Users.json
            users = _load_users_as_list()
            record = {
                "timestamp_utc": _now_utc_iso(),
                "name": name.strip(),
                "birth_date": _serialize_date(birth_date),
                "nationality": nationality.strip(),
                "address": address.strip(),
                "email": email.strip(),
                "mobile": mobile.strip(),
            }
            users.append(record)
            _upload_users_json(users)
            st.success("Saved to Supabase: Users.json")
        except Exception as e:
            st.error(f"Save failed: {e}")

st.divider()

# ----------------------------- Download & Exit ------------------------
d1, d2 = st.columns(2)

with d1:
    if st.button("Download"):
        content = _download_users_json()
        if not content:
            st.warning("Users.json does not exist yet.")
        else:
            # Show an actual download button with the loaded bytes
            st.download_button(
                label="⬇️ Download Users.json",
                data=content,
                file_name="Users.json",
                mime="application/json",
            )

with d2:
    if st.button("Exit"):
        _exit_app()

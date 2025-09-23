import os
import io
import json
from datetime import datetime, timezone, date

import streamlit as st
from supabase import create_client, Client
from streamlit.components.v1 import html as st_html

# ---------- Page ----------
st.set_page_config(page_title="on-boarding", page_icon="🧾", layout="centered")
st.title("on-boarding")
st.caption("Enter user data, then Save to append it to Users.json in your Supabase bucket.")

# ---------- Supabase ----------
@st.cache_resource(show_spinner=False)
def get_supabase() -> Client:
    url = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
    key = st.secrets.get("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        st.error("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.")
        st.stop()
    return create_client(url, key)

supabase = get_supabase()

# Change these if needed
BUCKET = "Test1"           # storage bucket name
OBJECT_PATH = "Users.json" # file path inside the bucket

# ---------- Helpers ----------
def _download_users_json() -> bytes | None:
    """Return the Users.json bytes if present, else None."""
    try:
        blob = supabase.storage.from_(BUCKET).download(OBJECT_PATH)
        if isinstance(blob, (bytes, bytearray)):
            return bytes(blob)
        if isinstance(blob, dict) and "data" in blob:  # some client versions
            return blob["data"]
    except Exception:
        pass
    return None

def _remove_users_json_if_exists():
    """Best-effort removal before re-upload (avoids upsert edge cases)."""
    try:
        supabase.storage.from_(BUCKET).remove([OBJECT_PATH])
    except Exception:
        pass  # ignore if it doesn't exist

def _upload_users_json(records: list[dict]):
    """Write the entire list to Users.json (overwrite)."""
    data_bytes = json.dumps(records, ensure_ascii=False, indent=2).encode("utf-8")
    _remove_users_json_if_exists()  # avoid using upsert
    supabase.storage.from_(BUCKET).upload(
        OBJECT_PATH,
        data_bytes,
        {"contentType": "application/json; charset=utf-8"},
    )
    
def _load_users_as_list() -> list[dict]:
    """Load Users.json as list; return [] if missing/invalid."""
    raw = _download_users_json()
    if not raw:
        return []
    try:
        obj = json.loads(raw.decode("utf-8"))
        return obj if isinstance(obj, list) else [obj]
    except Exception:
        return []

def _clear_fields():
    for k in ("name", "birth_date", "nationality", "address", "email", "mobile"):
        st.session_state.pop(k, None)
    st.success("All fields cleared.")
    st.rerun()

def _exit_app():
    st_html("<script>try{window.close()}catch(e){}</script>", height=0)
    st.success("You can now close this tab/window.")
    st.stop()

# ---------- Form ----------
with st.form("onboarding_form", clear_on_submit=False):
    st.subheader("User information")

    name = st.text_input("Name", key="name")
    birth_date = st.text_input("Birth Date", key="birth_date")
    nationality = st.text_input("Nationality", key="nationality")
    address = st.text_area("Address", key="address")
    email = st.text_input("email", key="email")
    mobile = st.text_input("mobile phone number", key="mobile")

    c1, c2 = st.columns(2)
    with c1:
        save_clicked = st.form_submit_button("Save", type="primary")
    with c2:
        clear_clicked = st.form_submit_button("Clear all the fields")

if clear_clicked:
    _clear_fields()

if save_clicked:
    missing = [fld for fld, val in {"Name": name, "email": email}.items() if not str(val).strip()]
    if missing:
        st.error("Please fill the required field(s): " + ", ".join(missing))
    else:
        try:
            users = _load_users_as_list()
            users.append(
                {
                    "name": name.strip(),
                    "birth_date": birth_date.strip(),
                    "nationality": nationality.strip(),
                    "address": address.strip(),
                    "email": email.strip(),
                    "mobile": mobile.strip(),
                }
            )
            _upload_users_json(users)
            st.success("Saved to Supabase: Users.json")
        except Exception as e:
            st.error(f"Save failed: {e}")

st.divider()

# ---------- Download & Exit ----------
d1, d2 = st.columns(2)
with d1:
    if st.button("Download"):
        content = _download_users_json()
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
        _exit_app()

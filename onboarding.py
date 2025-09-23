import os
import json
import streamlit as st
from supabase import create_client, Client

# Helper imports
from download_users_json import download_users_json
from remove_users_json_if_exists import remove_users_json_if_exists
from upload_users_json import upload_users_json
from load_users_as_list import load_users_as_list
from clear_fields import clear_fields
from exit_app import exit_app
from upload_single_user_json import upload_single_user_json  # NEW

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

# Adjust if needed
BUCKET = "Test1"            # storage bucket name
OBJECT_PATH = "Users.json"  # file name inside the bucket

# ---------- Form ----------
with st.form("onboarding_form", clear_on_submit=False):
    st.subheader("User information")

    name = st.text_input("Name", key="name")
    birth_date = st.text_input("Birth Date", key="birth_date")
    nationality = st.text_input("Nationality", key="nationality")
    address = st.text_area("Address", key="address")
    email = st.text_input("email", key="email")
    mobile = st.text_input("mobile phone number", key="mobile")

    # NEW: optional filename to also store this single record as its own JSON
    filename = st.text_input("Filename (optional, e.g., alice_2025-09-23.json)", key="filename")

    c1, c2 = st.columns(2)
    with c1:
        save_clicked = st.form_submit_button("Save", type="primary")
    with c2:
        clear_clicked = st.form_submit_button("Clear all the fields")

if clear_clicked:
    clear_fields()

if save_clicked:
    missing = [fld for fld, val in {"Name": name, "email": email}.items() if not str(val).strip()]
    if missing:
        st.error("Please fill the required field(s): " + ", ".join(missing))
    else:
        try:
            # Record built from the form (single user entry)
            record = {
                "name": name.strip(),
                "birth_date": birth_date.strip(),
                "nationality": nationality.strip(),
                "address": address.strip(),
                "email": email.strip(),
                "mobile": mobile.strip(),
            }

            # 1) Append to Users.json (list)
            users = load_users_as_list(supabase, BUCKET, OBJECT_PATH)
            users.append(record)
            remove_users_json_if_exists(supabase, BUCKET, OBJECT_PATH)
            upload_users_json(supabase, BUCKET, OBJECT_PATH, users)
            st.success("Saved to Supabase: Users.json")

            # 2) If a filename is provided, also store this single record under that file
            filename_clean = (filename or "").strip()
            if filename_clean:
                # store the single-record JSON; returns the final path (with .json ensured)
                single_path = upload_single_user_json(supabase, BUCKET, filename_clean, record)

                # Provide a signed download link (1 hour)
                signed = supabase.storage.from_(BUCKET).create_signed_url(single_path, 60 * 60)
                signed_url = signed.get("signedURL") if isinstance(signed, dict) else signed["signedURL"]
                st.info(f"Saved separate JSON as: {single_path}")
                st.link_button("⬇️ Download separate JSON (valid 1h)", signed_url)

        except Exception as e:
            st.error(f"Save failed: {e}")

st.divider()

# ---------- Download & Exit ----------
d1, d2 = st.columns(2)
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

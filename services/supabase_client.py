import os
import streamlit as st
from supabase import create_client, Client

DEFAULT_BUCKET = "Test1"
DEFAULT_USERS_OBJECT = "Users.json"

@st.cache_resource(show_spinner=False)
def get_client() -> Client:
    url = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
    key = st.secrets.get("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        st.error("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.")
        st.stop()
    return create_client(url, key)

def get_bucket() -> str:
    return os.getenv("SUPABASE_BUCKET") or DEFAULT_BUCKET

def get_users_object() -> str:
    return os.getenv("SUPABASE_USERS_OBJECT") or DEFAULT_USERS_OBJECT

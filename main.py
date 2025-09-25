import streamlit as st
from services.supabase_client import get_client
from views.home import render as view_home
from views.signin import render as view_signin
from views.onboarding_signup import render as view_onboarding
from views.dashboard import render as view_dashboard

st.set_page_config(page_title="Test Web Platform", page_icon="🧪", layout="centered")
_ = get_client()

if "view" not in st.session_state:
    st.session_state["view"] = "home"

def go(view: str):
    st.session_state["view"] = view
    st.rerun()

route = st.session_state["view"]
if route == "home":
    view_home(go)
elif route == "signin":
    view_signin(go)
elif route == "dashboard":
    if st.session_state.get("logged_in"):
        view_dashboard(go)
    else:
        st.warning("Please sign in first.")
        view_signin(go)
else:
    view_onboarding(go)

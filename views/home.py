import streamlit as st
def render(go):
    st.title("Test Web Platform")
    st.write("Choose an action:")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Sign in your account", type="primary", use_container_width=True):
            go("signin")
    with c2:
        if st.button("Sign up", use_container_width=True):
            go("onboarding")

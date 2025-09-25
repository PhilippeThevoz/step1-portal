import streamlit as st
def render(go):
    st.title("Welcome (Dashboard)")
    st.write("Dynamic onboarding is template-driven. Use Home → Sign up to test it.")
    if st.button("← Back to Home"): go("home")

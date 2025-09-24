import streamlit as st
def clear_fields() -> None:
    for k in ("name","birth_date","nationality","address","email","mobile","username","password","repeat_password","filename"):
        st.session_state.pop(k, None)
    st.success("All fields cleared.")
    st.rerun()

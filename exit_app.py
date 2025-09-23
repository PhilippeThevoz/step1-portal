import streamlit as st
from streamlit.components.v1 import html as st_html

def exit_app() -> None:
    # Best effort: close window if possible
    st_html("<script>try{window.close()}catch(e){}</script>", height=0)
    st.success("You can now close this tab/window.")
    st.stop()

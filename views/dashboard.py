import os, streamlit as st
from services.supabase_client import get_client, get_bucket
from services.certus import get_env, load_payload_from_storage, create_batch, activate_batch_put_activation, download_batch_zip, upload_zip_to_storage, parse_qr_codes_in_storage

def render(go):
    st.title("Welcome")
    user = st.session_state.get("user") or {}
    st.caption(f"Logged in as: {user.get('username','(unknown)')}")
    supabase = get_client(); bucket = get_bucket()
    c1, c2 = st.columns(2)
    with c1: logout = st.button("Logout", use_container_width=True)
    with c2: create_certus = st.button("Create CERTUS", type="primary", use_container_width=True)
    if logout:
        for k in ("logged_in", "user", "pending_2fa", "CERTUS_Batch_ID", "certus_output"):
            st.session_state.pop(k, None)
        go("home")
    if create_certus:
        try:
            certus_content = load_payload_from_storage(supabase, bucket, "CERTUS-Test.json")
            st.subheader("CERTUS content (preview)"); st.json(certus_content, expanded=False)
            base = st.secrets.get("CERTUS_API_PATH") or os.getenv("CERTUS_API_PATH")
            key  = st.secrets.get("CERTUS_API_KEY")  or os.getenv("CERTUS_API_KEY")
            if not base or not key: st.error("Missing CERTUS env vars."); st.stop()
            certus_output, batch_id = create_batch(base, key, certus_content)
            st.subheader("-------- CERTUS API response")
            if isinstance(certus_output, (dict, list)): st.json(certus_output, expanded=False)
            else: st.code(certus_output)
            if batch_id:
                st.info(f"CERTUS_Batch_ID: {batch_id}")
                st.session_state["CERTUS_Batch_ID"] = batch_id
            st.success("-------- CERTUS batch created successfully.")
        except Exception as e:
            st.error(f"Create CERTUS failed: {e}")
    st.divider()
    batch_id = st.session_state.get("CERTUS_Batch_ID")
    if batch_id:
        st.subheader("Download CERTUS batch")
        if st.button("Download batch ZIP & upload to Supabase", use_container_width=True):
            try:
                key = st.secrets.get("CERTUS_API_KEY") or os.getenv("CERTUS_API_KEY")
                zip_bytes = download_batch_zip(batch_id, key)
                st.download_button(label="⬇️ Download CERTUS ZIP", data=zip_bytes, file_name=f"{batch_id}.zip", mime="application/zip")
                uploaded = upload_zip_to_storage(supabase, bucket, batch_id, zip_bytes)
                st.success(f"Uploaded {len(uploaded)} file(s) to Supabase at '{bucket}/CERTUS/{batch_id}/'.")
            except Exception as e:
                st.error(f"Batch download/upload failed: {e}")
        st.subheader("Activate CERTUS batch")
        if st.button("Activate batch", use_container_width=True):
            try:
                key = st.secrets.get("CERTUS_API_KEY") or os.getenv("CERTUS_API_KEY")
                res = activate_batch_put_activation(batch_id, key)
                if res.get("ok"): st.success("Activation has been successful")
                else: st.error(f"Activation failed: HTTP {res.get('status_code')} — {res.get('body')}")
            except Exception as e: st.error(f"Activation error: {e}")
        st.subheader("CERTUS QR codes parsing")
        if st.button("Parse QR codes", use_container_width=True):
            try:
                results = parse_qr_codes_in_storage(supabase, bucket, batch_id)
                if results:
                    st.success(f"Parsed {len(results)} QR PNG file(s) and saved JSON next to them.")
                    st.json(results, expanded=False)
                else:
                    st.info("No QR PNGs found or none decoded.")
            except Exception as e: st.error(f"QR parsing failed: {e}")
    else:
        st.info("No CERTUS_Batch_ID available. Create a batch first.")

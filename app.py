import io
import os
import uuid
import csv
from datetime import datetime, timezone

import streamlit as st
from supabase import create_client, Client

st.set_page_config(page_title="Step 2 Portal", page_icon="🧪", layout="centered")
st.title("Step 2 – Save results to a file (Supabase)")
st.caption("Compute locally, store file in a private Supabase bucket, and download via signed link.")

# ---------------- Supabase client (server-only credentials) ----------------
@st.cache_resource(show_spinner=False)
def get_supabase() -> Client:
    url = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
    key = st.secrets.get("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        st.error("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY. Add them in Streamlit secrets (local) and Render env vars (prod).")
        st.stop()
    return create_client(url, key)

supabase = get_supabase()
BUCKET = "step2-files"

# ---------------- Calculator (same as Step 1) ----------------
with st.form("calc_form", clear_on_submit=False):
    st.subheader("Input data")
    name = st.text_input("Your name", placeholder="Ada Lovelace")
    col1, col2 = st.columns(2)
    with col1:
        a = st.number_input("Value A", value=10.0, step=0.1)
    with col2:
        b = st.number_input("Value B", value=5.0, step=0.1)

    operation = st.selectbox(
        "Operation",
        [
            "Add (A + B)",
            "Subtract (A - B)",
            "Multiply (A × B)",
            "Divide (A ÷ B)",
            "Mean of A & B",
            "Euclidean norm √(A² + B²)",
        ],
        index=0,
    )
    apply_vat = st.checkbox("Add VAT 7.7% to result (example)")
    submitted = st.form_submit_button("Compute", type="primary")

result = None
formula = None

if submitted:
    if operation == "Add (A + B)":
        result = a + b
        formula = "A + B"
    elif operation == "Subtract (A - B)":
        result = a - b
        formula = "A - B"
    elif operation == "Multiply (A × B)":
        result = a * b
        formula = "A × B"
    elif operation == "Divide (A ÷ B)":
        if b == 0:
            st.error("Cannot divide by zero.")
            st.stop()
        result = a / b
        formula = "A ÷ B"
    elif operation == "Mean of A & B":
        result = (a + b) / 2
        formula = "(A + B) / 2"
    else:
        result = (a**2 + b**2) ** 0.5
        formula = "√(A² + B²)"

    if apply_vat:
        result *= 1.077

    st.success("Computed successfully.")
    if name:
        st.write(f"Hello, **{name}**!")
    st.metric(label="Result", value=f"{result:,.4f}")
    with st.expander("Details"):
        st.json(
            {
                "inputs": {"A": a, "B": b, "operation": operation, "apply_vat": apply_vat, "name": name},
                "outputs": {"result": result, "formula": formula},
            }
        )

st.divider()

# ---------------- Save & Retrieve (Step 2) ----------------
st.subheader("Save result as a file (Supabase)")
st.caption("Creates a CSV in a private bucket and returns a 1-hour signed download link.")

col_save, col_retrieve = st.columns(2)

with col_save:
    if st.button("💾 Save current result to file", type="primary", disabled=result is None):
        if result is None:
            st.warning("Compute a result first.")
        else:
            # Build CSV content in memory
            now = datetime.now(timezone.utc)
            rows = [
                ["timestamp_utc", now.isoformat()],
                ["name", name],
                ["A", a],
                ["B", b],
                ["operation", operation],
                ["apply_vat", str(apply_vat)],
                ["formula", formula],
                ["result", f"{result:.10f}"],
            ]

            buf = io.StringIO()
            writer = csv.writer(buf)
            for r in rows:
                writer.writerow(r)
            data_bytes = buf.getvalue().encode("utf-8")

            # Path pattern: YYYY/MM/DD/<uuid>.csv
            path = f"{now:%Y/%m/%d}/{uuid.uuid4()}.csv"

            try:
                # Upload (private bucket)
                supabase.storage.from_(BUCKET).upload(path, data_bytes, {"content-type": "text/csv"})

                # Signed URL (1 hour)
                signed = supabase.storage.from_(BUCKET).create_signed_url(path, 60 * 60)
                # supabase-py returns a dict with 'signedURL'
                signed_url = signed.get("signedURL") if isinstance(signed, dict) else signed["signedURL"]

                st.success("File saved to Supabase.")
                st.write("Download link (valid 1 hour):")
                st.link_button("⬇️ Download CSV", signed_url)
                st.code(path, language="text")  # show the stored path

                # keep a session list of created files for easy retrieval later
                files = st.session_state.get("created_files", [])
                files.append({"path": path, "created": now.isoformat()})
                st.session_state["created_files"] = files

            except Exception as e:
                st.error(f"Upload failed: {e}")

with col_retrieve:
    st.write("Retrieve any stored file if you know its path.")
    known_path = st.text_input("Supabase storage path (YYYY/MM/DD/uuid.csv)")
    if st.button("Get a fresh download link"):
        if not known_path.strip():
            st.warning("Enter a path.")
        else:
            try:
                signed = supabase.storage.from_(BUCKET).create_signed_url(known_path.strip(), 60 * 60)
                signed_url = signed.get("signedURL") if isinstance(signed, dict) else signed["signedURL"]
                st.success("Link generated (valid 1 hour):")
                st.link_button("⬇️ Download CSV", signed_url)
            except Exception as e:
                st.error(f"Could not generate link: {e}")

st.divider()

# List files created THIS SESSION (convenience only)
created = st.session_state.get("created_files", [])
if created:
    st.subheader("Files created this session")
    for i, f in enumerate(created, start=1):
        st.write(f"**{i}.** `{f['path']}` — {f['created']}")
else:
    st.caption("No saved files in this session yet.")

import io
import os
import uuid
import csv
from datetime import datetime, timezone

import streamlit as st
from supabase import create_client, Client

st.set_page_config(page_title="Step 2 Portal", page_icon="🧪", layout="centered")
st.title("Step 2 – Auto-save results to Supabase (Test1/)")
st.caption("Compute locally; each result is auto-saved as a CSV to a private Supabase bucket under Test1/.")

# ---------------- Supabase client (server-only credentials) ----------------
@st.cache_resource(show_spinner=False)
def get_supabase() -> Client:
    url = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
    key = st.secrets.get("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        st.error("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY. Add them in Streamlit secrets (local) and Render env vars (prod).")
        st.stop()
    return create_client(url, key)

st.write("Service key configured:", bool(st.secrets.get("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")))

supabase = get_supabase()

# ❗ Change this if your bucket has a different name
BUCKET = "Test1"             # bucket name


# ---------------- Calculator ----------------
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
    # ---- compute ----
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

    # ---- AUTO-SAVE to Supabase under Test1/ ----
    try:
        now = datetime.now(timezone.utc)

        # Build CSV in-memory
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
        writer.writerows(rows)
        data_bytes = buf.getvalue().encode("utf-8")

        # Store inside the Test1/ directory (object key prefix)
        # Example filename: Test1/20250923_153045_3f9b7b1e.csv
        path   = f"{now:%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}.csv"

        supabase.storage.from_(BUCKET).upload(path, data_bytes, {"content-type": "text/csv"})

        # Optional: show a 1-hour signed download link
        signed = supabase.storage.from_(BUCKET).create_signed_url(path, 60 * 60)
        signed_url = signed.get("signedURL") if isinstance(signed, dict) else signed["signedURL"]

        st.info("Auto-saved to Supabase (private bucket).")
        st.code(path, language="text")
        st.link_button("⬇️ Download CSV (valid 1h)", signed_url)

        # keep a session list of created files for convenience
        files = st.session_state.get("created_files", [])
        files.append({"path": path, "created": now.isoformat()})
        st.session_state["created_files"] = files

    except Exception as e:
        st.error(f"Auto-save failed: {e}")

st.divider()

# ---------------- Retrieve a previously saved file ----------------
st.subheader("Retrieve a previously saved file")
st.caption("Paste a Supabase storage path (e.g., Test1/20250923_153045_ab12cd34.csv) to get a fresh signed link.")
known_path = st.text_input("Supabase storage path inside the bucket")
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

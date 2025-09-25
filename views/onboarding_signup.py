import os, json, re, requests
from datetime import datetime
from collections import OrderedDict
import streamlit as st

from services.supabase_client import get_client, get_bucket, get_users_object
from services.users import (
    load_onboarding_template,
    build_dynamic_record_from_inputs,
    append_user_record,
    save_single_user_file,
)
from clear_fields import clear_fields
from send_email_with_attachment import send_email_with_attachment
from send_sms_vonage import send_sms_vonage

T_CERTUS_PATH = "config/Template-CERTUS-Member.json"

def _slug(label: str) -> str:
    s = (label or "").strip().lower()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^a-z0-9_]", "_", s)
    return s

def _render_field(label: str, default: str):
    key = f"dyn_{_slug(label)}"
    low = label.lower()
    if "address" in low:
        return st.text_area(label, key=key, value=default or "")
    if "password" in low:
        return st.text_input(label, type="password", key=key, value="")
    return st.text_input(label, key=key, value=default or "")

# -------------------- helpers for CERTUS merge --------------------
def _ci_get(d: dict, *names: str) -> str:
    """Case-insensitive get across multiple possible labels."""
    # exact first
    for n in names:
        if n in d:
            v = d.get(n)
            return "" if v is None else str(v)
    # case-insensitive
    lowmap = { (k or "").strip().lower(): k for k in d.keys() }
    for n in names:
        k = lowmap.get((n or "").strip().lower())
        if k is not None:
            v = d.get(k)
            return "" if v is None else str(v)
    # fuzzy contains
    want = [ (n or "").strip().lower() for n in names if n ]
    for k, v in d.items():
        lk = (k or "").strip().lower()
        if any(tok in lk for tok in want):
            return "" if v is None else str(v)
    return ""

def _build_certus_row_and_id(captured: dict):
    """
    Returns (row_values_list, ghana_id_str) in the exact order required by your template.
    Order:
      Last Name, First Name, Birth Date, Ghana Card ID Number, Private Address,
      email, Mobile phone number, username, Public Key
    """
    last_name  = _ci_get(captured, "Last Name", "surname", "lastname", "name_last")
    first_name = _ci_get(captured, "First Name", "firstname", "given name", "givenname", "name_first")
    birth_date = _ci_get(captured, "Birth Date", "Birth Date (DD-MM-YYYY)", "birth_date", "date of birth", "dob")
    ghana_id   = _ci_get(captured, "Ghana Card ID Number", "ghana card id", "ghana_card_id")
    address    = _ci_get(captured, "Private Address", "Private Address (GhanaPostGPS)", "address")
    email      = _ci_get(captured, "email", "e-mail")
    mobile     = _ci_get(captured, "Mobile phone number", "mobile", "phone", "mobile phone number")
    username   = _ci_get(captured, "username", "user name")
    public_key = _ci_get(captured, "Public Key", "public key", "pubkey")

    row = [last_name, first_name, birth_date, ghana_id, address, email, mobile, username, public_key]
    # normalize whitespace
    row = [ (v or "").replace("\n"," ").strip() for v in row ]
    return row, ghana_id

def _load_text_from_storage(supabase, bucket: str, path: str) -> str:
    blob = supabase.storage.from_(bucket).download(path)
    if isinstance(blob, dict) and "data" in blob:
        blob = blob["data"]
    if not blob:
        raise FileNotFoundError(f"Template not found: {bucket}/{path}")
    try:
        return blob.decode("utf-8")
    except Exception:
        return str(blob)

def _merge_certus_template(template_text: str, row_values: list[str], ghana_id: str) -> dict:
    """
    Replace:
      1) <Last Name,First Name,Birth Date,Ghana Card ID Number,Private Address,email,Mobile phone number,username,Public Key>
         with a JSON snippet of quoted strings: "LN","FN",...
         so that the surrounding JSON remains valid:
           "documents":[["1",  <here>  ]]
      2) "<GhanaCardID>" in "name":"<GhanaCardID>" with the actual ghana_id (no extra quotes).
    """
    # Build JSON snippet for the row (quoted items, comma-separated, no surrounding [ ])
    row_json_inside_array = ",".join(json.dumps(v) for v in row_values)

    pattern_row = (
        r"<\s*Last Name\s*,\s*First Name\s*,\s*Birth Date\s*,\s*Ghana Card ID Number\s*,\s*Private Address\s*,\s*email\s*,\s*Mobile phone number\s*,\s*username\s*,\s*Public Key\s*>"
    )
    merged = re.sub(pattern_row, row_json_inside_array, template_text)

    # Replace <GhanaCardID> inside quotes
    pattern_gid = r"<\s*GhanaCardID\s*>"
    merged = re.sub(pattern_gid, ghana_id, merged)

    # Parse final JSON
    return json.loads(merged)

# -------------------- main view --------------------
def render(go):
    st.title("on-boarding (dynamic template)")
    st.caption("Fields are generated from Supabase: Test1/config/Template_onboarding_Member.json")

    supabase = get_client()
    bucket = get_bucket()
    users_object = get_users_object()

    # Load onboarding template (fields for the form)
    try:
        tmpl: OrderedDict = load_onboarding_template(supabase, bucket)
    except Exception as e:
        st.error(f"Cannot load onboarding template: {e}")
        st.stop()

    # ----- Dynamic form -----
    with st.form("onboarding_dynamic_form", clear_on_submit=False):
        st.subheader("Member information")
        captured: dict[str, str] = {}
        for label, default in tmpl.items():
            captured[label] = _render_field(label, str(default if default is not None else ""))

        filename = st.text_input("Filename (optional, e.g., member_2025-09-23.json)", key="dyn_filename")

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            save_clicked = st.form_submit_button("Save", type="primary")
        with c2:
            clear_clicked = st.form_submit_button("Clear all the fields")
        with c3:
            send_email_clicked = st.form_submit_button("Send email")
        with c4:
            send_sms_clicked = st.form_submit_button("Send SMS")

    # ----- Buttons actions -----
    if clear_clicked:
        clear_fields()
        for label in tmpl.keys():
            st.session_state.pop(f"dyn_{_slug(label)}", None)
        st.session_state.pop("dyn_filename", None)

    def _record_for_email():
        filtered = {k: v for k, v in captured.items() if "password" not in k.lower()}
        return json.dumps(filtered, ensure_ascii=False, indent=2)

    if save_clicked:
        try:
            # 1) Build and save the user record
            record, username, err = build_dynamic_record_from_inputs(captured)
            if err:
                st.error(err)
                st.stop()

            append_user_record(supabase, bucket, users_object, record)
            st.success("Saved to Supabase: Users.json")

            filename_clean = (filename or "").strip()
            if filename_clean:
                single_path = save_single_user_file(supabase, bucket, filename_clean, record)
                signed = supabase.storage.from_(bucket).create_signed_url(single_path, 3600)
                signed_url = signed.get("signedURL") if isinstance(signed, dict) else signed["signedURL"]
                st.info(f"Saved separate JSON as: {single_path}")
                st.link_button("⬇️ Download separate JSON (valid 1h)", signed_url)

            # 2) Build certus_content from Template-CERTUS-Member.json using captured data
            try:
                template_text = _load_text_from_storage(supabase, bucket, T_CERTUS_PATH)
            except Exception as te:
                st.error(f"Could not read CERTUS template from Supabase ({T_CERTUS_PATH}): {te}")
                st.stop()

            row_values, ghana_id = _build_certus_row_and_id(captured)
            certus_content = _merge_certus_template(template_text, row_values, ghana_id)

            # (Optional) show what will be sent
            with st.expander("CERTUS payload preview"):
                st.json(certus_content, expanded=False)

            # 3) Call CERTUS create batch with this certus_content
            base = st.secrets.get("CERTUS_API_PATH") or os.getenv("CERTUS_API_PATH")
            key  = st.secrets.get("CERTUS_API_KEY")  or os.getenv("CERTUS_API_KEY")
            if not base or not key:
                st.warning("CERTUS_API_PATH / CERTUS_API_KEY not set; skipping CERTUS batch creation.")
            else:
                url = base.rstrip("/") + "/batches/json"
                headers = {
                    "accept": "application/json",
                    "issuer-impersonate": "utopia",
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                }
                resp = requests.post(url, headers=headers, json=certus_content, timeout=60)
                try:
                    certus_output = resp.json()
                except Exception:
                    certus_output = resp.text

                st.subheader("CERTUS API response")
                if resp.ok:
                    st.success("CERTUS batch created successfully.")
                    if isinstance(certus_output, (dict, list)):
                        st.json(certus_output, expanded=False)
                    else:
                        st.code(certus_output)
                    # Extract and store batch id if present
                    batch_id = ""
                    try:
                        payload = certus_output if isinstance(certus_output, dict) else json.loads(certus_output)
                        if isinstance(payload, dict):
                            batch_id = payload.get("batchId") or payload.get("batch_id") or ""
                    except Exception:
                        pass
                    if batch_id:
                        st.info(f"CERTUS_Batch_ID: {batch_id}")
                        st.session_state["CERTUS_Batch_ID"] = batch_id
                    st.session_state["certus_output"] = certus_output
                else:
                    st.error(f"CERTUS API error: HTTP {resp.status_code}")
                    st.code(certus_output if isinstance(certus_output, str) else json.dumps(certus_output, indent=2))

        except Exception as e:
            st.error(f"Save failed: {e}")

    if 'send_email_clicked' in locals() and send_email_clicked:
        try:
            json_str = _record_for_email()
            # find an email-like field
            to_email = ""
            for k, v in captured.items():
                if "email" in k.lower():
                    to_email = v.strip(); break
            if not to_email:
                st.error("No email field found in template or it's empty.")
            else:
                attach_name = (filename or "").strip() or f"record_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                if not attach_name.lower().endswith(".json"):
                    attach_name += ".json"
                send_email_with_attachment(
                    smtp_cfg={
                        "host": st.secrets.get("SMTP_HOST") or os.getenv("SMTP_HOST"),
                        "port": int(st.secrets.get("SMTP_PORT", os.getenv("SMTP_PORT") or 587)),
                        "username": st.secrets.get("SMTP_USERNAME") or os.getenv("SMTP_USERNAME"),
                        "password": st.secrets.get("BLUEWIN_SMTP_PASSWORD") or os.getenv("BLUEWIN_SMTP_PASSWORD"),
                        "sender_email": st.secrets.get("SENDER_EMAIL") or os.getenv("SENDER_EMAIL"),
                        "sender_name": st.secrets.get("SENDER_NAME") or os.getenv("SENDER_NAME") or "Your Team",
                        "use_ssl": str(st.secrets.get("SMTP_SSL") or os.getenv("SMTP_SSL") or "false").lower() == "true",
                        "use_starttls": str(st.secrets.get("SMTP_STARTTLS") or os.getenv("SMTP_STARTTLS") or "true").lower() == "true",
                    },
                    to_email=to_email,
                    subject="Successful onboarding",
                    body_text=("Dear Madam/Dear Sir,\nYour on-boarding has been successful.\nPlease find below and enclosed your records.\nBest Regards.\nYour Team\n\n" + json_str + "\n"),
                    attachment_filename=attach_name,
                    attachment_bytes=json_str.encode("utf-8"),
                )
                st.success(f"Email sent to {to_email}")
        except Exception as e:
            st.error(f"Send email failed: {e}")

    if 'send_sms_clicked' in locals() and send_sms_clicked:
        try:
            to_msisdn = ""
            for k, v in captured.items():
                if "mobile" in k.lower() or "phone" in k.lower():
                    to_msisdn = v.strip(); break
            if not to_msisdn:
                st.error("No mobile/phone field found in template or it's empty.")
            else:
                api_key    = st.secrets.get("VONAGE_API_KEY")    or os.getenv("VONAGE_API_KEY")
                api_secret = st.secrets.get("VONAGE_API_SECRET") or os.getenv("VONAGE_API_SECRET")
                from_id    = st.secrets.get("VONAGE_SMS_FROM")   or os.getenv("VONAGE_SMS_FROM") or "Onboarding"
                if not api_key or not api_secret:
                    st.error("Missing VONAGE_API_KEY or VONAGE_API_SECRET in secrets/env.")
                else:
                    from send_sms_vonage import send_sms_vonage as _send
                    name_fields = [k for k in captured.keys() if "name" in k.lower()]
                    msg_text = " ".join([captured[k] for k in name_fields]).strip() if name_fields else "Hello from the onboarding portal"
                    msg_id = _send(api_key, api_secret, from_id, to_msisdn, msg_text)
                    st.success(f"SMS queued via Vonage (message-id: {msg_id})")
        except Exception as e:
            st.error(f"Send SMS failed: {e}")

    st.divider()
    if st.button("← Back to Home"):
        go("home")

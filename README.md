# Test Web Platform – Modular Refactor (v2)

Run:
  pip install -r requirements.txt
  streamlit run app.py

Configure `.streamlit/secrets.toml` from `.streamlit/secrets.example.toml`.

Place your existing helper modules (send_plain_email.py, send_email_with_attachment.py, send_sms_vonage.py, download_users_json.py, load_users_as_list.py, remove_users_json_if_exists.py, upload_users_json.py, upload_single_user_json.py, clear_fields.py, exit_app.py) next to `app.py`.

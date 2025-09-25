# Dynamic Template Onboarding

This version generates the onboarding form from a template stored in Supabase Storage:

- Bucket: `Test1`
- Path: `config/Template_onboarding_Member.json`

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Notes

- Keep helper modules next to `app.py`:
  - send_plain_email.py
  - send_email_with_attachment.py
  - send_sms_vonage.py
  - download_users_json.py
  - load_users_as_list.py
  - remove_users_json_if_exists.py
  - upload_users_json.py
  - upload_single_user_json.py
  - clear_fields.py
  - exit_app.py
- Password fields in the template must be labeled exactly **"password"** and **"Repeat password"** (case-insensitive).
- Saved records include `password_sha256` and exclude the clear-text password fields.

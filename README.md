# Test Web Platform (Streamlit + Supabase)

Sign-up with password hashing, Sign-in with 2FA (email or SMS via Vonage), and basic user file storage.

## Setup

1. **Python env**
   ```bash
   pip install -r requirements.txt
   ```

2. **Secrets**  
   Copy `.streamlit/secrets.example.toml` to `.streamlit/secrets.toml` and fill values:
   - `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`
   - SMTP vars for email
   - Vonage vars for SMS

3. **Run**
   ```bash
   streamlit run onboarding.py
   ```

## Notes
- Users are stored in Supabase **Storage** as JSON at `bucket/object` (defaults `Test1/Users.json`).
- Passwords are stored **only as SHA-256** hashes.
- 2FA sends a 4-digit code by email or SMS, then verifies it.

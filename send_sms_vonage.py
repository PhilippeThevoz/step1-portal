# send_sms_vonage.py
import re
import vonage

def _to_e164_ch(number: str) -> str:
    """Very light normalization: turn '079...' into '+4179...' when no leading '+'."""
    n = (number or "").strip().replace(" ", "")
    if n.startswith("+"):
        return n
    if n.startswith("00"):
        return "+" + n[2:]
    if n.startswith("0"):  # assume Swiss national format
        return "+41" + n[1:]
    # if user typed digits only, assume it's already an international number without '+'
    if re.fullmatch(r"\d{6,15}", n):
        return "+" + n
    return n  # last resort; Vonage will reject if invalid

def send_sms_vonage(api_key: str, api_secret: str, from_id: str, to_number: str, text: str) -> str:
    """
    Send a text SMS via Vonage's SMS API.
    Returns the Vonage message-id on success; raises on error.
    """
    client = vonage.Client(key=api_key, secret=api_secret)
    sms = vonage.Sms(client)

    to_e164 = _to_e164_ch(to_number)
    resp = sms.send_message({
        "from": from_id,        # e.g. 'Onboarding' or a Vonage-allowed numeric sender
        "to": to_e164,          # e.g. '+41...'
        "text": text,
        # optional: "type": "unicode" if you need non-GSM characters
    })

    # Vonage returns {'messages': [{'status': '0', 'message-id': '...'}]}
    msg = (resp or {}).get("messages", [{}])[0]
    if msg.get("status") != "0":
        raise RuntimeError(msg.get("error-text", "Unknown Vonage error"))
    return msg.get("message-id", "")

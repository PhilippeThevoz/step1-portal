import re

def _to_e164_ch(number: str) -> str:
    n = (number or "").strip().replace(" ", "")
    if n.startswith("+"): return n
    if n.startswith("00"): return "+" + n[2:]
    if n.startswith("0"):  return "+41" + n[1:]  # assume Swiss national
    if re.fullmatch(r"\d{6,15}", n): return "+" + n
    return n

def send_sms_vonage(api_key: str, api_secret: str, from_id: str, to_number: str, text: str) -> str:
    to_e164 = _to_e164_ch(to_number)

    # Try Vonage v4 SDK first
    try:
        from vonage import Vonage, Auth            # v4
        from vonage_sms import SmsMessage          # v4 SMS model
        client = Vonage(Auth(api_key=api_key, api_secret=api_secret))
        message = SmsMessage(to=to_e164, from_=(from_id or "Onboarding"), text=text)
        resp = client.sms.send(message)
        try:
            data = resp.model_dump(exclude_unset=True)
        except Exception:
            data = {}
        msg_id = (data.get("message_uuid")
                  or data.get("message-id")
                  or (data.get("messages") or [{}])[0].get("message_uuid")
                  or (data.get("messages") or [{}])[0].get("message-id"))
        return msg_id or "ok"
    except Exception:
        # Legacy SDK fallback
        try:
            import vonage  # legacy v2/v3
            client = vonage.Client(key=api_key, secret=api_secret)
            sms = vonage.Sms(client)
            resp = sms.send_message({"from": from_id or "Onboarding", "to": to_e164, "text": text})
            msg = (resp or {}).get("messages", [{}])[0]
            if msg.get("status") != "0":
                raise RuntimeError(msg.get("error-text", "Vonage error"))
            return msg.get("message-id", "")
        except Exception:
            # REST fallback
            import requests
            r = requests.post(
                "https://rest.nexmo.com/sms/json",
                data={
                    "api_key": api_key,
                    "api_secret": api_secret,
                    "from": from_id or "Onboarding",
                    "to": to_e164,
                    "text": text,
                },
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            msg = (data or {}).get("messages", [{}])[0]
            if msg.get("status") != "0":
                raise RuntimeError(msg.get("error-text", "Vonage REST error"))
            return msg.get("message-id", "")

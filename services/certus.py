import os, io, json, zipfile, mimetypes, requests
from typing import Any, Dict, List, Tuple, Union

def get_env():
    base = os.getenv("CERTUS_API_PATH")
    key  = os.getenv("CERTUS_API_KEY")
    return base, key

def load_payload_from_storage(supabase, bucket: str, object_name: str = "CERTUS-Test.json") -> Dict[str, Any]:
    raw = supabase.storage.from_(bucket).download(object_name)
    if isinstance(raw, dict) and "data" in raw:
        raw = raw["data"]
    if not raw:
        raise FileNotFoundError(f"{object_name} not found in bucket '{bucket}'.")
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return json.loads(raw)

def create_batch(base_path: str, api_key: str, certus_content: Dict[str, Any]) -> Tuple[Union[Dict, str], str]:
    url = base_path.rstrip("/") + "/batches/json"
    headers = {
        "accept": "application/json",
        "issuer-impersonate": "utopia",
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    resp = requests.post(url, headers=headers, json=certus_content, timeout=60)
    try:
        certus_output = resp.json()
    except Exception:
        certus_output = resp.text
    batch_id = ""
    try:
        payload = certus_output if isinstance(certus_output, dict) else json.loads(certus_output)
        if isinstance(payload, dict):
            batch_id = payload.get("batchId") or payload.get("batch_id") or ""
    except Exception:
        pass
    if not resp.ok:
        raise RuntimeError(f"Create batch failed: HTTP {resp.status_code} {resp.text}")
    return certus_output, batch_id

def activate_batch_put_activation(batch_id: str, api_key: str) -> Dict[str, Any]:
    url = f"https://dm-api.pp.certusdoc.com/api/v1/batches/{batch_id}/activation"
    headers = {
        "accept": "*/*",
        "issuer-impersonate": "utopia",
        "Authorization": f"Bearer {api_key}",
    }
    resp = requests.put(url, headers=headers, timeout=60)
    try:
        return {"status_code": resp.status_code, "ok": resp.ok, "body": resp.json()}
    except Exception:
        return {"status_code": resp.status_code, "ok": resp.ok, "body": resp.text}

def download_batch_zip(batch_id: str, api_key: str) -> bytes:
    url = f"https://dm-api.pp.certusdoc.com/api/v1/batches/{batch_id}/download"
    headers = {
        "accept": "*/*",
        "issuer-impersonate": "utopia",
        "Authorization": f"Bearer {api_key}",
    }
    r = requests.get(url, headers=headers, timeout=180)
    if not r.ok:
        raise RuntimeError(f"Download API error: HTTP {r.status_code}")
    return r.content

def upload_zip_to_storage(supabase, bucket: str, batch_id: str, zip_bytes: bytes) -> List[str]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        raise ValueError("Downloaded file is not a valid ZIP.")
    uploaded = []
    for member in zf.infolist():
        if member.is_dir():
            continue
        data = zf.read(member)
        object_path = f"CERTUS/{batch_id}/{member.filename}".replace("\\", "/")
        content_type, _ = mimetypes.guess_type(member.filename)
        opts = {"contentType": content_type or "application/octet-stream"}
        try:
            supabase.storage.from_(bucket).remove([object_path])
        except Exception:
            pass
        supabase.storage.from_(bucket).upload(object_path, data, opts)
        uploaded.append(object_path)
    return uploaded

def parse_qr_codes_in_storage(supabase, bucket: str, batch_id: str):
    try:
        import numpy as np
        import cv2
    except ImportError as e:
        raise ImportError("QR parsing requires OpenCV and NumPy. Install with: pip install opencv-python-headless numpy") from e
    import os as _os
    _os.environ["OPENCV_LOG_LEVEL"] = "ERROR"
    qr_dir = f"CERTUS/{batch_id}/QR-code"
    entries = supabase.storage.from_(bucket).list(qr_dir)
    pngs = [e.get("name") for e in entries if isinstance(e, dict) and str(e.get("name","")).lower().endswith(".png")]
    results = []
    for fname in pngs:
        object_path = f"{qr_dir}/{fname}"
        blob = supabase.storage.from_(bucket).download(object_path)
        if isinstance(blob, dict) and "data" in blob:
            blob = blob["data"]
        img_arr = np.frombuffer(blob, dtype=np.uint8)
        img = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
        detector = cv2.QRCodeDetector()
        texts = []
        try:
            retval, decoded_info, points, _ = detector.detectAndDecodeMulti(img)
            if retval and decoded_info:
                texts = [t for t in decoded_info if t]
        except Exception:
            pass
        if not texts:
            t, _, _ = detector.detectAndDecode(img)
            if t:
                texts = [t]
        if not texts:
            continue
        prefix = fname.rsplit(".", 1)[0]
        json_path = f"{qr_dir}/{prefix}.json"
        payload = {"file": fname, "batchId": batch_id, "qr": texts if len(texts) > 1 else texts[0]}
        data_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        try:
            supabase.storage.from_(bucket).remove([json_path])
        except Exception:
            pass
        supabase.storage.from_(bucket).upload(json_path, data_bytes, {"contentType": "application/json; charset=utf-8"})
        results.append({"png": fname, "json": prefix + ".json", "qr": payload["qr"]})
    return results

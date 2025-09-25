import hashlib, json
from typing import Dict, List, Optional, Tuple
from collections import OrderedDict
from load_users_as_list import load_users_as_list
from remove_users_json_if_exists import remove_users_json_if_exists
from upload_users_json import upload_users_json
from upload_single_user_json import upload_single_user_json

TEMPLATE_PATH_DEFAULT = "config/Template-onboarding-Member.json"

def hash_password_sha256(password: str) -> str:
    return hashlib.sha256((password or "").encode("utf-8")).hexdigest()

def verify_password_sha256(password: str, stored_hash: str) -> bool:
    return hash_password_sha256(password) == (stored_hash or "")

def load_onboarding_template(supabase, bucket: str, path: str = TEMPLATE_PATH_DEFAULT) -> OrderedDict:
    blob = supabase.storage.from_(bucket).download(path)
    if isinstance(blob, dict) and "data" in blob:
        blob = blob["data"]
    if not blob:
        raise FileNotFoundError(f"Template not found at {bucket}/{path}")
    try:
        data = json.loads(blob.decode("utf-8"), object_pairs_hook=OrderedDict)
    except Exception:
        data = json.loads(blob, object_pairs_hook=OrderedDict)
    if not isinstance(data, dict):
        raise ValueError("Template JSON must be an object with field names as keys.")
    return data

def _norm(label: str) -> str:
    return (label or "").strip().lower()

def build_dynamic_record_from_inputs(inputs: Dict[str, str]) -> Tuple[Dict, Optional[str], Optional[str]]:
    rec = {}
    pwd = None; pwd2 = None; username_value = None
    for label, value in inputs.items():
        n = _norm(label)
        if n == "password":
            pwd = value or ""; continue
        if n in ("repeat password","repeat-password","repeat_password"):
            pwd2 = value or ""; continue
        if n == "username":
            username_value = (value or "").strip()
        rec[label] = (value or "").strip()
    if (pwd is not None) or (pwd2 is not None):
        if (pwd or "") != (pwd2 or ""):
            return {}, username_value, "Passwords do not match."
        rec["password_sha256"] = hash_password_sha256(pwd or "")
    return rec, username_value, None

def list_users(supabase, bucket: str, object_path: str) -> List[Dict]:
    return load_users_as_list(supabase, bucket, object_path)

def find_user_by_username(users: List[Dict], username: str) -> Optional[Dict]:
    uname = (username or "").strip().lower()
    for u in users:
        u_un = (u.get("username") or "").strip().lower()
        if u_un == uname:
            return u
        for k, v in u.items():
            if _norm(k) == "username" and (str(v or "").strip().lower() == uname):
                return u
    return None

def append_user_record(supabase, bucket: str, object_path: str, record: Dict) -> None:
    users = list_users(supabase, bucket, object_path)
    users.append(record)
    remove_users_json_if_exists(supabase, bucket, object_path)
    upload_users_json(supabase, bucket, object_path, users)

def save_single_user_file(supabase, bucket: str, filename: str, record: Dict) -> str:
    return upload_single_user_json(supabase, bucket, filename, record)

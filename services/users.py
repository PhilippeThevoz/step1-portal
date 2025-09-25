import hashlib
from typing import Dict, List, Optional
from load_users_as_list import load_users_as_list
from remove_users_json_if_exists import remove_users_json_if_exists
from upload_users_json import upload_users_json
from upload_single_user_json import upload_single_user_json

def hash_password_sha256(password: str) -> str:
    return hashlib.sha256((password or "").encode("utf-8")).hexdigest()

def verify_password_sha256(password: str, stored_hash: str) -> bool:
    return hash_password_sha256(password) == (stored_hash or "")

def build_user_record(name: str,birth_date: str,nationality: str,address: str,email: str,mobile: str,username: str,password_hash: Optional[str] = None,) -> Dict:
    rec = {
        "name": (name or "").strip(),
        "birth_date": (birth_date or "").strip(),
        "nationality": (nationality or "").strip(),
        "address": (address or "").strip(),
        "email": (email or "").strip(),
        "mobile": (mobile or "").strip(),
        "username": (username or "").strip(),
    }
    if password_hash:
        rec["password_sha256"] = password_hash
    return rec

def list_users(supabase, bucket: str, object_path: str) -> List[Dict]:
    return load_users_as_list(supabase, bucket, object_path)

def find_user_by_username(users: List[Dict], username: str) -> Optional[Dict]:
    uname = (username or "").strip().lower()
    return next((u for u in users if (u.get("username") or "").strip().lower() == uname), None)

def append_user_record(supabase, bucket: str, object_path: str, record: Dict) -> None:
    users = list_users(supabase, bucket, object_path)
    users.append(record)
    remove_users_json_if_exists(supabase, bucket, object_path)
    upload_users_json(supabase, bucket, object_path, users)

def save_single_user_file(supabase, bucket: str, filename: str, record: Dict) -> str:
    return upload_single_user_json(supabase, bucket, filename, record)

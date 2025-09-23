import json
from typing import List, Dict
from download_users_json import download_users_json

def load_users_as_list(supabase, bucket: str, object_path: str) -> List[Dict]:
    """Load Users.json as list; return [] if missing/invalid."""
    raw = download_users_json(supabase, bucket, object_path)
    if not raw:
        return []
    try:
        obj = json.loads(raw.decode("utf-8"))
        return obj if isinstance(obj, list) else [obj]
    except Exception:
        return []

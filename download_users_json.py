from typing import Optional

def download_users_json(supabase, bucket: str, object_path: str) -> Optional[bytes]:
    """
    Return the Users.json bytes if present, else None.
    Compatible with supabase-py client variations.
    """
    try:
        blob = supabase.storage.from_(bucket).download(object_path)
        print("download_user_json")
        if isinstance(blob, (bytes, bytearray)):
            return bytes(blob)
        if isinstance(blob, dict) and "data" in blob:
            return blob["data"]
    except Exception:
        pass
    return None

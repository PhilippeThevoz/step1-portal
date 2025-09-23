import json

def upload_users_json(supabase, bucket: str, object_path: str, records: list[dict]) -> None:
    """
    Write the entire list as JSON to Users.json.
    Pass raw bytes to avoid client .encode() pitfalls.
    """
    print("upload_users_json")
    data_bytes = json.dumps(records, ensure_ascii=False, indent=2).encode("utf-8")
    supabase.storage.from_(bucket).upload(
        object_path,
        data_bytes,
        {"contentType": "application/json; charset=utf-8"},
    )

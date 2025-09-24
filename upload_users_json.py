import json

def upload_users_json(supabase, bucket: str, object_path: str, records: list[dict]) -> None:
    data_bytes = json.dumps(records, ensure_ascii=False, indent=2).encode("utf-8")
    supabase.storage.from_(bucket).upload(
        object_path,
        data_bytes,
        {"contentType": "application/json; charset=utf-8"},
    )

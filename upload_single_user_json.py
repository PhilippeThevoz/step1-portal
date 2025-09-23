import json

def upload_single_user_json(supabase, bucket: str, filename: str, record: dict) -> str:
    """
    Saves the given 'record' as a standalone JSON file named 'filename' in the given bucket.
    If 'filename' has no .json extension, one is added.
    Returns the final object path used in storage.
    """
    # Ensure .json extension
    path = filename if filename.lower().endswith(".json") else f"{filename}.json"

    data_bytes = json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8")

    # Overwrite if exists (remove first to avoid upsert edge cases)
    try:
        supabase.storage.from_(bucket).remove([path])
    except Exception:
        pass

    supabase.storage.from_(bucket).upload(
        path,
        data_bytes,
        {"contentType": "application/json; charset=utf-8"},
    )

    return path

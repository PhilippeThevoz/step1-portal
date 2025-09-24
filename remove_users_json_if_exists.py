def remove_users_json_if_exists(supabase, bucket: str, object_path: str) -> None:
    try:
        supabase.storage.from_(bucket).remove([object_path])
    except Exception:
        pass

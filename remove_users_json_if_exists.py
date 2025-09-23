def remove_users_json_if_exists(supabase, bucket: str, object_path: str) -> None:
    """Best-effort removal before re-upload (avoids upsert edge cases)."""
    try:
        supabase.storage.from_(bucket).remove([object_path])
    except Exception:
        # Ignore if it doesn't exist or any non-critical error
        pass

from pathlib import Path

from django.conf import settings


def upload_bytes(path: str, content: bytes, content_type: str):
    if settings.SUPABASE_URL and settings.SUPABASE_SECRET_KEY:
        from supabase import create_client
        create_client(settings.SUPABASE_URL, settings.SUPABASE_SECRET_KEY).storage.from_(settings.SUPABASE_BUCKET).upload(path, content, file_options={"content-type": content_type, "upsert": "false"})
        return path
    local_path = settings.BASE_DIR / "media" / path
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(content)
    return path


def download_bytes(path: str) -> bytes:
    if settings.SUPABASE_URL and settings.SUPABASE_SECRET_KEY:
        from supabase import create_client
        return create_client(settings.SUPABASE_URL, settings.SUPABASE_SECRET_KEY).storage.from_(settings.SUPABASE_BUCKET).download(path)
    return (settings.BASE_DIR / "media" / path).read_bytes()


def delete_paths(paths: list[str]):
    if not paths:
        return
    if settings.SUPABASE_URL and settings.SUPABASE_SECRET_KEY:
        from supabase import create_client
        create_client(settings.SUPABASE_URL, settings.SUPABASE_SECRET_KEY).storage.from_(settings.SUPABASE_BUCKET).remove(paths)
        return
    media_root = (settings.BASE_DIR / "media").resolve()
    for path in paths:
        local_path = (media_root / path).resolve()
        if not local_path.is_relative_to(media_root):
            raise ValueError(f"Unsafe upload path: {path}")
        local_path.unlink(missing_ok=True)

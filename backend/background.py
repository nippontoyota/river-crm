"""Public-log-safe entry point for the production Actions workflow."""
import io
import logging
import os
import re
import sys
import traceback
import uuid


def main():
    mode = sys.argv[1] if len(sys.argv) == 2 else ''
    if mode not in {'preflight', 'process', 'storage-check'}:
        print('FAIL invalid_background_mode')
        return 1
    # Do not silently use SQLite, local upload storage or development signing keys.
    required = ('DATABASE_URL', 'DJANGO_SECRET_KEY', 'SUPABASE_URL', 'SUPABASE_SECRET_KEY', 'SUPABASE_UPLOAD_BUCKET')
    if any(not os.environ.get(key) for key in required):
        print('FAIL required_background_configuration_missing')
        return 1
    # Optional keys must be absent, not empty, to retain production fallback behavior.
    for key in ('JWT_SIGNING_KEY', 'INTAKE_FINGERPRINT_KEY'):
        if not os.environ.get(key):
            os.environ.pop(key, None)
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    logging.disable(logging.CRITICAL)
    try:
        import django
        django.setup()
        from django.conf import settings
        from django.core.management import call_command
        from django.db import connection
        if connection.vendor != 'postgresql' or settings.DEBUG or settings.INTAKE_EXECUTION_MODE != 'database' or settings.CELERY_TASK_ALWAYS_EAGER or not settings.INTAKE_ENABLED:
            print('FAIL background_runtime_configuration')
            return 1
        # Scheduled processing may check migrations, never apply them.
        call_command('migrate', check=True, stdout=io.StringIO(), stderr=io.StringIO())
        if mode == 'preflight':
            call_command('intake_check_credentials')
        elif mode == 'process':
            call_command('intake_process_pending', automatic_meta=True, reminders=True, max_seconds=240)
        else:
            from uploads.storage import delete_paths, download_bytes, upload_bytes
            path = f'preflight/{uuid.uuid4()}.txt'
            content = b'CRM shared storage check\n'
            try:
                upload_bytes(path, content, 'text/plain')
                if download_bytes(path) != content:
                    raise ValueError('storage_roundtrip_failed')
            finally:
                delete_paths([path])
            print('PASS shared storage upload/download/delete')
    except (Exception, SystemExit) as error:
        # Startup, SQL and SDK errors can contain secrets or customer data.
        print('FAIL background_run_failed; check runtime, migration status and access. Details redacted.')
        # Types and source line numbers allow diagnosis without exception messages,
        # SQL, arguments, locals or customer answers in this public repository.
        for _ in range(4):
            category = type(error).__name__
            if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,80}', category):
                category = 'redacted'
            frames = []
            for frame, line in traceback.walk_tb(error.__traceback__):
                filename = os.path.basename(frame.f_code.co_filename)
                if re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*\.py', filename):
                    frames.append(f'{filename}:{line}')
            print(f'FAIL category={category} source={",".join(frames[-3:])}')
            error = error.__cause__ or error.__context__
            if error is None:
                break
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

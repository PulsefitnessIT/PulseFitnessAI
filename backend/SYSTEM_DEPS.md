# System (apt) dependencies

Python deps live in `requirements.txt`. These OS-level packages must be installed
on the container/host **in addition** to pip — they cannot be installed via pip.

```bash
apt-get install -y libmagic1 file
```

## Why
- `libmagic1` (+ the `file` command/data) — required by `python-magic` to sniff
  uploaded file MIME types from raw bytes. Used by
  `backend/utils/file_validation.py::validate_upload()` which guards every
  upload endpoint against polyglot / disguised-extension attacks
  (e.g. an HTML file served as `.png`).

  **Failure mode if missing**: the validator fails closed and *every* upload
  returns `HTTP 415 "File validation backend unavailable"`. Symptoms in the
  app: equipment photos can't upload, fault attachments fail, CSV imports
  refuse to run, CRM documents block. There is no warning at startup other
  than a single log line:

      python-magic unavailable — uploads will fail: <ImportError>

  Restore by running the apt install above and restarting the backend.

## Verifying
```bash
python3 -c "import magic; print(magic.from_buffer(b'%PDF-1.4', mime=True))"
# expected: application/pdf
```

If you see `ImportError: failed to find libmagic`, libmagic is missing.

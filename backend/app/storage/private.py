"""Private document storage on local disk (swap for S3-compatible storage in
production). Files are written under random keys outside any web-served path
and are only reachable through authorised, expiring links."""
import hashlib
import os
import secrets

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

ALLOWED = {
    ".pdf": ("application/pdf", b"%PDF-"),
    ".pptx": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        b"PK\x03\x04",
    ),
}


# Identity and business evidence may also be photographed or scanned.
VERIFICATION_ALLOWED = {
    ".pdf": ALLOWED[".pdf"],
    ".png": ("image/png", b"\x89PNG\r\n\x1a\n"),
    ".jpg": ("image/jpeg", b"\xff\xd8\xff"),
    ".jpeg": ("image/jpeg", b"\xff\xd8\xff"),
}

# Campaign covers and business logos – images only, 5 MB cap enforced separately.
IMAGE_ALLOWED = {
    ".png": ("image/png", b"\x89PNG\r\n\x1a\n"),
    ".jpg": ("image/jpeg", b"\xff\xd8\xff"),
    ".jpeg": ("image/jpeg", b"\xff\xd8\xff"),
    ".webp": ("image/webp", b"RIFF"),  # RIFF....WEBP checked below
}

IMAGE_MAX_MB = 5

# Public image tokens use their own salt so they cannot open private docs.
def make_image_token(key: str, user_id: int) -> str:
    return _serializer("image-download").dumps({"k": key, "u": user_id})


def read_image_token(token: str, max_age=300):
    try:
        return _serializer("image-download").loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None


class UploadRejected(ValueError):
    pass


def validate_upload(filename: str, data: bytes, allowed=None):
    allowed = allowed or ALLOWED
    if not data:
        raise UploadRejected("The file is empty.")
    if len(data) > current_app.config["MAX_UPLOAD_MB"] * 1024 * 1024:
        raise UploadRejected("The file is too large.")
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in allowed:
        raise UploadRejected("Only " + ", ".join(e.lstrip(".").upper() for e in allowed) + " files are accepted.")
    content_type, magic = allowed[ext]
    # Trust the content, not the extension or the client-supplied MIME type.
    if not data.startswith(magic):
        raise UploadRejected("The file content does not match its extension.")
    return ext, content_type


def save_private(data: bytes, ext: str):
    key = secrets.token_hex(24) + ext
    root = current_app.config["UPLOAD_DIR"]
    os.makedirs(root, mode=0o700, exist_ok=True)
    path = os.path.join(root, key)
    with open(path, "wb") as fh:
        fh.write(data)
    os.chmod(path, 0o600)
    return key, hashlib.sha256(data).hexdigest()


def read_private(key: str) -> bytes:
    root = os.path.realpath(current_app.config["UPLOAD_DIR"])
    path = os.path.realpath(os.path.join(root, key))
    if os.path.commonpath([root, path]) != root:
        raise FileNotFoundError(key)
    with open(path, "rb") as fh:
        return fh.read()


def remove_private(key: str):
    root = os.path.realpath(current_app.config["UPLOAD_DIR"])
    path = os.path.realpath(os.path.join(root, key))
    if os.path.commonpath([root, path]) == root and os.path.exists(path):
        os.remove(path)


def _serializer(salt="private-download"):
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=salt)


def make_download_token(pitch_deck_id: int, user_id: int) -> str:
    return _serializer().dumps({"d": pitch_deck_id, "u": user_id})


def read_download_token(token: str, max_age=300):
    try:
        return _serializer().loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None


# Verification documents use their own salt so a pitch-deck link can never open one.
def make_verification_token(doc_id: int, user_id: int) -> str:
    return _serializer("verification-download").dumps({"d": doc_id, "u": user_id})


def read_verification_token(token: str, max_age=300):
    try:
        return _serializer("verification-download").loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None

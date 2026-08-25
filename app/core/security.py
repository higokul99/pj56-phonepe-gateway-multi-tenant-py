import hashlib
import hmac
import json
import secrets
from typing import Any, Dict, Optional
from cryptography.fernet import Fernet, InvalidToken
from app.config import get_settings


def get_fernet_cipher(custom_key: Optional[str] = None) -> Fernet:
    """Returns a Fernet cipher instance using the master encryption key or provided key."""
    settings = get_settings()
    key = custom_key or settings.MASTER_ENCRYPTION_KEY
    if isinstance(key, str):
        key = key.encode("utf-8")
    return Fernet(key)


def encrypt_secret(plain_text: str, custom_key: Optional[str] = None) -> str:
    """Encrypts a secret string at rest using Fernet symmetric encryption."""
    if not plain_text:
        return ""
    cipher = get_fernet_cipher(custom_key)
    encrypted_bytes = cipher.encrypt(plain_text.encode("utf-8"))
    return encrypted_bytes.decode("utf-8")


def decrypt_secret(encrypted_text: str, custom_key: Optional[str] = None) -> str:
    """Decrypts an encrypted secret string using Fernet symmetric encryption."""
    if not encrypted_text:
        return ""
    cipher = get_fernet_cipher(custom_key)
    try:
        decrypted_bytes = cipher.decrypt(encrypted_text.encode("utf-8"))
        return decrypted_bytes.decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Failed to decrypt secret: invalid key or corrupted data") from exc


def generate_api_key(environment: str = "live") -> tuple[str, str, str]:
    """
    Generates a secure API key, its SHA-256 hash for database storage, and a prefix for logs/dashboard.
    Returns: (raw_key, key_hash, key_prefix)
    """
    prefix = f"pg_{environment[:4]}_"
    random_part = secrets.token_hex(24)
    raw_key = f"{prefix}{random_part}"
    key_hash = hash_api_key(raw_key)
    key_prefix = raw_key[:12]  # e.g. "pg_live_a1b2"
    return raw_key, key_hash, key_prefix


def hash_api_key(raw_key: str) -> str:
    """Returns the SHA-256 hex digest of the raw API key."""
    return hashlib.sha256(raw_key.strip().encode("utf-8")).hexdigest()


def generate_webhook_secret() -> str:
    """Generates a high-entropy secret for signing outbound webhooks to tenants."""
    return f"whsec_{secrets.token_hex(24)}"


def sign_payload(payload: Dict[str, Any] | str, secret: str) -> str:
    """
    Generates an HMAC-SHA256 signature for a webhook payload using the tenant's webhook_secret.
    """
    if isinstance(payload, dict):
        payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    else:
        payload_bytes = payload.encode("utf-8")

    secret_bytes = secret.encode("utf-8")
    signature = hmac.new(secret_bytes, payload_bytes, hashlib.sha256).hexdigest()
    return signature


def verify_signature(payload: Dict[str, Any] | str, signature: str, secret: str) -> bool:
    """
    Verifies an HMAC-SHA256 signature using constant-time comparison.
    """
    expected_signature = sign_payload(payload, secret)
    return secrets.compare_digest(expected_signature, signature)


def verify_admin_key(provided_key: Optional[str]) -> bool:
    """Validates the master admin API key using constant-time comparison."""
    if not provided_key:
        return False
    settings = get_settings()
    return secrets.compare_digest(settings.ADMIN_API_KEY, provided_key.strip())

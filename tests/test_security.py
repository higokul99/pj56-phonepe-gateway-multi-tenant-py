import pytest
from app.core.security import (
    decrypt_secret,
    encrypt_secret,
    generate_api_key,
    generate_webhook_secret,
    hash_api_key,
    sign_payload,
    verify_admin_key,
    verify_signature,
)


def test_encryption_and_decryption():
    secret = "phonepe_client_secret_xyz123!@#"
    encrypted = encrypt_secret(secret)
    assert encrypted != secret
    assert len(encrypted) > 20

    decrypted = decrypt_secret(encrypted)
    assert decrypted == secret


def test_api_key_generation_and_hashing():
    raw_key, key_hash, key_prefix = generate_api_key(environment="live")
    assert raw_key.startswith("pg_live_")
    assert key_prefix == raw_key[:12]
    assert len(key_hash) == 64  # SHA-256 hex string

    # Ensure hash matches deterministic hashing
    assert hash_api_key(raw_key) == key_hash


def test_webhook_signing_and_verification():
    secret = generate_webhook_secret()
    payload = {
        "event": "payment.completed",
        "data": {
            "merchant_order_id": "ORD-12345",
            "amount": 50000,
            "status": "COMPLETED",
        },
    }

    sig = sign_payload(payload, secret)
    assert len(sig) == 64  # HMAC-SHA256 hex

    # Positive verification
    assert verify_signature(payload, sig, secret) is True

    # Tampered payload fails
    tampered_payload = {
        "event": "payment.completed",
        "data": {
            "merchant_order_id": "ORD-12345",
            "amount": 100,  # tampered
            "status": "COMPLETED",
        },
    }
    assert verify_signature(tampered_payload, sig, secret) is False

    # Wrong secret fails
    wrong_secret = generate_webhook_secret()
    assert verify_signature(payload, sig, wrong_secret) is False


def test_admin_key_verification():
    assert verify_admin_key("test_admin_secret_key") is True
    assert verify_admin_key("wrong_key") is False
    assert verify_admin_key("") is False
    assert verify_admin_key(None) is False

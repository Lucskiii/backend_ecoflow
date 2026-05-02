from datetime import datetime, timezone

import jwt
from app.config import get_settings
from app.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_password_creates_non_plaintext_hash() -> None:
    password = "super-secret-password"

    password_hash = hash_password(password)

    assert password_hash != password
    assert isinstance(password_hash, str)
    assert len(password_hash) > 20


def test_verify_password_returns_true_for_matching_password() -> None:
    password = "match-me"
    password_hash = hash_password(password)

    assert verify_password(password, password_hash) is True


def test_verify_password_returns_false_for_wrong_password() -> None:
    password_hash = hash_password("correct-password")

    assert verify_password("wrong-password", password_hash) is False


def test_create_access_token_contains_subject_and_valid_expiry() -> None:
    get_settings.cache_clear()
    subject = "customer-123"
    before = datetime.now(timezone.utc)

    token = create_access_token(subject)
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    after = datetime.now(timezone.utc)

    assert payload["sub"] == subject
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    remaining_seconds = (exp - after).total_seconds()
    expected_seconds = settings.jwt_expire_minutes * 60
    assert before < exp
    assert expected_seconds - 2 <= remaining_seconds <= expected_seconds + 2


def test_decode_access_token_returns_payload_from_created_token() -> None:
    subject = "abc"
    token = create_access_token(subject)

    payload = decode_access_token(token)

    assert payload["sub"] == subject
    assert "exp" in payload

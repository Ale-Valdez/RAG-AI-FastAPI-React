from app.infrastructure.auth.passwords import Argon2PasswordHasher


def test_argon2_password_hasher_verify() -> None:
    hasher = Argon2PasswordHasher()
    password_hash = hasher.hash("correct-horse")
    assert hasher.verify("correct-horse", password_hash) is True
    assert hasher.verify("wrong-password", password_hash) is False

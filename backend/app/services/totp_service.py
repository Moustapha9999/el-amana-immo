import pyotp

from app.core.secret_box import open_secret, seal


def generate_secret() -> str:
    return pyotp.random_base32()


def store_secret(plaintext: str) -> str:
    """Chiffre le secret TOTP avant persistance."""
    sealed = seal(plaintext)
    return sealed or plaintext


def load_secret(stored: str | None) -> str | None:
    return open_secret(stored)


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="BEA DIGITAL")


def verify_code(secret: str | None, code: str) -> bool:
    plain = load_secret(secret)
    if not plain or not code:
        return False
    totp = pyotp.TOTP(plain)
    return totp.verify(code.strip(), valid_window=1)

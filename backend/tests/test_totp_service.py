from app.services.totp_service import generate_secret, store_secret, verify_code


def test_totp_generate_and_verify():
    secret = generate_secret()
    import pyotp

    code = pyotp.TOTP(secret).now()
    assert verify_code(secret, code)


def test_totp_verify_sealed():
    secret = generate_secret()
    sealed = store_secret(secret)
    import pyotp

    code = pyotp.TOTP(secret).now()
    assert verify_code(sealed, code)

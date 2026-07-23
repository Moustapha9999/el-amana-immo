from app.services.inventaire_service import normalize_scan_code


def test_normalize_immo_prefix():
    assert normalize_scan_code("  IMMO:ABC-001  ") == "ABC-001"


def test_normalize_plain_code():
    assert normalize_scan_code("ABC-001") == "ABC-001"

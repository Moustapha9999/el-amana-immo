from app.services.reporting_export import ecritures_to_excel


def test_ecritures_excel_empty():
    data = ecritures_to_excel([])
    assert data[:2] == b"PK"

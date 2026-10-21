from io import BytesIO

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_upload_endpoint_accepts_image_file():
    image_bytes = b"\x89PNG\r\n\x1a\n" + b"0" * 64

    response = client.post(
        "/api/upload",
        files={"file": ("sample.png", BytesIO(image_bytes), "image/png")},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["filename"] == "sample.png"
    assert "text" in payload

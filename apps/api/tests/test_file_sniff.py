from app.services.uploads import sniff_mime


def test_sniff_known_headers() -> None:
    assert sniff_mime(b"%PDF-1.7 rest", ".pdf") == "application/pdf"
    assert sniff_mime(b"\x89PNG\r\n\x1a\nrest", ".png") == "image/png"
    assert sniff_mime(b"\xff\xd8\xff\xe0", ".jpg") == "image/jpeg"
    assert sniff_mime(b"not a pdf", ".pdf") is None
    assert sniff_mime(b"%PDF", ".exe") is None

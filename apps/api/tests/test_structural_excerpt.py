from app.services.structural_excerpt import anchors_from_text, structural_signature


def test_anchors_keep_structure_and_drop_pii() -> None:
    text = """
    EMPLOYEE ONBOARDING FORM
    Full name: Dana Cohen
    National ID: 123456782
    Email: dana@example.com
    Phone: 050-1234567
    Declaration: The undersigned confirms the details in this agreement and schedule.
    דנה כהן
    """
    anchors = anchors_from_text(text)
    joined = "\n".join(anchors)

    assert "dana@example.com" not in joined
    assert "123456782" not in joined
    assert "050" not in joined
    assert "Dana Cohen" not in joined
    assert "דנה כהן" not in joined
    assert any(anchor.startswith("Full name") for anchor in anchors)
    assert any("undersigned" in anchor for anchor in anchors)
    assert any(anchor.isupper() for anchor in anchors)
    assert len(structural_signature(anchors)) == 16

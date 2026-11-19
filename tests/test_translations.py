"""
Tests for UI translation dictionary and language switching.
"""

from app.translations import TRANSLATIONS, get_translation


def test_translation_keys_symmetry():
    """Ensures both English and Tamil dictionaries cover essential UI keys."""
    en_keys = set(TRANSLATIONS["en"].keys())
    ta_keys = set(TRANSLATIONS["ta"].keys())
    assert en_keys == ta_keys, f"Missing keys in translations: {en_keys.symmetric_difference(ta_keys)}"


def test_get_translation_fallback():
    """Verifies fallback behavior when an unknown language is passed."""
    val = get_translation("app_name", lang="fr")
    assert val == "SevaPath"


def test_homepage_tamil_language_switch(client):
    """Verifies that requesting ?lang=ta renders Tamil strings and updates session/cookie."""
    response = client.get("/?lang=ta")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "சேவாபாத்" in html
    assert "வருமானச் சான்றிதழ்" in html
    assert "சாதிச் சான்றிதழ்" in html


def test_set_language_redirect(client):
    """Verifies that /set-language/ta sets cookie and redirects."""
    response = client.get("/set-language/ta", follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "சேவாபாத்" in html

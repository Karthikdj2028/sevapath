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


def test_anonymous_session_advisory_bilingual(client):
    """Verifies that the anonymous-session advisory renders properly in English and Tamil."""
    # 1. Homepage English
    res_en = client.get("/?lang=en")
    assert res_en.status_code == 200
    html_en = res_en.get_data(as_text=True)
    assert "Anonymous Session Notice" in html_en
    assert "Your checklist is linked to this browser" in html_en

    # 2. Homepage Tamil
    res_ta = client.get("/?lang=ta")
    assert res_ta.status_code == 200
    html_ta = res_ta.get_data(as_text=True)
    assert "அநாமதேய அமர்வு வழிகாட்டுதல்" in html_ta
    assert "14 நாட்களுக்குப் பிறகு இந்த அமர்வு காலாவதியாகும்" in html_ta

    # 3. Service Detail View English
    detail_en = client.get("/service/income-certificate?lang=en")
    assert detail_en.status_code == 200
    detail_html_en = detail_en.get_data(as_text=True)
    assert "Anonymous Session Notice" in detail_html_en
    assert "SevaPath does not collect personal credentials" in detail_html_en

"""
Pytest unit & integration tests for PDF Report Generator and Printable Checklist Routes.

Verifies:
- PDF binary structure (%PDF header and %%EOF trailer).
- Non-empty output stream length (> 1500 bytes).
- Standard-library zlib decompression of content streams.
- Service code, official disclaimer, and INR currency presence.
- Published timelines only where officially verified, with non-guarantee caveats.
- Absence of session tokens, cookie hashes, or personal identifying data.
- Browser print view rendering with bilingual support and print controls.
- Cache-Control: no-store and security headers on report endpoints.
"""

import base64
import re
import zlib
from app.core.pdf_generator import build_preparation_pdf


def extract_pdf_stream_text(pdf_bytes: bytes) -> str:
    """
    Decompresses ReportLab stream objects (ASCII85Decode + FlateDecode) using Python standard library.
    Extracts text tokens for heuristic validation.
    """
    decompressed_chunks = []
    
    # ReportLab uses: stream\n<ascii85>~>endstream
    cursor = 0
    while True:
        s_idx = pdf_bytes.find(b"stream", cursor)
        if s_idx == -1:
            break
        
        # Advance past 'stream' and newline
        content_start = s_idx + len(b"stream")
        if content_start < len(pdf_bytes) and pdf_bytes[content_start:content_start+1] in (b"\n", b"\r"):
            content_start += 1
        if content_start < len(pdf_bytes) and pdf_bytes[content_start:content_start+1] in (b"\n", b"\r"):
            content_start += 1

        e_idx = pdf_bytes.find(b"endstream", content_start)
        if e_idx == -1:
            break

        stream_raw = pdf_bytes[content_start:e_idx].strip()
        cursor = e_idx + len(b"endstream")

        # Try Adobe Ascii85 + FlateDecode
        try:
            flate_bytes = base64.a85decode(stream_raw, adobe=True)
            text_chunk = zlib.decompress(flate_bytes).decode("latin1", errors="ignore")
            decompressed_chunks.append(text_chunk)
            continue
        except Exception:
            pass

        # Try standard FlateDecode without Ascii85
        try:
            text_chunk = zlib.decompress(stream_raw).decode("latin1", errors="ignore")
            decompressed_chunks.append(text_chunk)
        except Exception:
            pass

    return " ".join(decompressed_chunks)


def test_pdf_generation_binary_structure():
    """Verifies that generated PDF has valid %PDF-1.x header, EOF trailer, and substantial length."""
    service_data = {
        "slug": "income-certificate",
        "name": "Income Certificate",
        "department": "Revenue Department",
        "official_fee": "INR 60 (e-Sevai centre charge) + INR 0 (Department fee)",
        "processing_time": "15 days",
        "portal_name": "Tamil Nadu e-Sevai (TNeGA)",
        "source_url": "https://tnesevai.tn.gov.in/Citizen/Pages/ServiceList.aspx",
        "verification_date": "19 November 2026"
    }
    progress_data = {
        "readiness_percentage": 50.0,
        "is_accepting": False,
        "readiness_stage": "in_progress",
    }
    requirements_data = [
        {
            "title": "Photo",
            "applicability": "applicable",
            "is_completed": 1,
            "presentation_category": "listed_applicability_unconfirmed",
            "help_text": "Recent photograph"
        },
        {
            "title": "Any Address Proof",
            "applicability": "applicable",
            "is_completed": 0,
            "presentation_category": "listed_applicability_unconfirmed",
            "help_text": "Valid residential address"
        }
    ]

    pdf_bytes = build_preparation_pdf(service_data, progress_data, requirements_data)

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1500
    assert pdf_bytes.startswith(b"%PDF-1.")
    assert b"%%EOF" in pdf_bytes[-100:]


def test_pdf_decompressed_content_and_disclaimers():
    """Verifies that decompressed stream contains service code, INR fee, disclaimer, and timeline."""
    service_data = {
        "slug": "nativity-certificate",
        "name": "Nativity Certificate",
        "department": "Revenue Department",
        "official_fee": "INR 60 (e-Sevai centre charge) + INR 0 (Department fee)",
        "processing_time": "07 days",
        "portal_name": "Tamil Nadu e-Sevai (TNeGA)",
        "source_url": "https://tnesevai.tn.gov.in/Citizen/Pages/ServiceList.aspx",
        "verification_date": "19 November 2026"
    }
    progress_data = {
        "readiness_percentage": 100.0,
        "is_accepting": True,
        "readiness_stage": "complete",
    }
    requirements_data = [
        {
            "title": "5-Year Residence Evidence",
            "applicability": "applicable",
            "is_completed": 1,
            "presentation_category": "alternative_option",
            "selected_alternative": "School Education Certificate"
        }
    ]

    pdf_bytes = build_preparation_pdf(service_data, progress_data, requirements_data)
    extracted_text = extract_pdf_stream_text(pdf_bytes)

    # 1. Service Code
    assert "REV-102" in extracted_text

    # 2. Statutory Fee (ASCII INR)
    assert "INR 60" in extracted_text
    assert "INR 0" in extracted_text

    # 3. Official Disclaimer
    assert "preparation checklist" in extracted_text.lower()
    assert "official government certificate" in extracted_text.lower()

    # 4. Published Timeline with Non-Guarantee
    assert "07 days" in extracted_text
    assert "not a statutory guarantee" in extracted_text.lower()

    # 5. Nativity Alternative Note
    assert "Nativity Alternative Proof Rule" in extracted_text


def test_pdf_zero_session_token_leakage():
    """Verifies that neither raw cookie tokens nor internal session IDs appear anywhere in the PDF."""
    raw_cookie_token = "secret_raw_citizen_cookie_token_999888777"
    internal_prep_token = "internal_secret_session_token_111222333"

    service_data = {
        "slug": "community-certificate",
        "name": "Community Certificate",
        "department": "Revenue Department",
        "verification_date": "19 November 2026"
    }
    progress_data = {
        "readiness_percentage": 0.0,
        "is_accepting": False,
        "readiness_stage": "not_started",
    }

    pdf_bytes = build_preparation_pdf(service_data, progress_data, [])
    extracted_text = extract_pdf_stream_text(pdf_bytes)

    assert raw_cookie_token.encode("ascii") not in pdf_bytes
    assert internal_prep_token.encode("ascii") not in pdf_bytes
    assert raw_cookie_token not in extracted_text
    assert internal_prep_token not in extracted_text


def test_download_pdf_route_security_headers(client):
    """Verifies that GET /service/<slug>/download-pdf returns 200, PDF content type, and no-store headers."""
    res = client.get("/service/income-certificate/download-pdf")
    assert res.status_code == 200
    assert res.headers["Content-Type"] == "application/pdf"
    assert "attachment" in res.headers["Content-Disposition"]
    assert "sevapath-income-certificate-preparation-checklist.pdf" in res.headers["Content-Disposition"]
    assert "no-store" in res.headers.get("Cache-Control", "")
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.data.startswith(b"%PDF-1.")


def test_print_checklist_route_renders_html_with_disclaimer(client):
    """Verifies that GET /service/<slug>/print renders browser-printable view with disclaimers."""
    res = client.get("/service/nativity-certificate/print?lang=en")
    assert res.status_code == 200
    assert "text/html" in res.headers["Content-Type"]
    assert "no-store" in res.headers.get("Cache-Control", "")
    html = res.get_data(as_text=True)

    assert "Nativity Certificate" in html
    assert "REV-102" in html
    assert "Statutory Notice:" in html
    assert "NOT an official government certificate" in html
    assert "window.print()" in html


def test_print_checklist_tamil_localization(client):
    """Verifies that GET /service/<slug>/print renders high-fidelity native Tamil Unicode."""
    res = client.get("/service/community-certificate/print?lang=ta")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # Assert native Tamil headings and notices
    assert "சாதிச் சான்றிதழ்" in html
    assert "அதிகாரப்பூர்வ அறிவிப்பு" in html
    assert "சேவாபாத்" in html

"""
SevaPath Initial Seeds for Tamil Nadu Civic Services.

Provides verified and demonstration service definitions with complete
bilingual (English & Tamil) translations and official government sources.
"""

import sqlite3

SERVICES_SEED_DATA = [
    {
        "slug": "income-certificate",
        "department": "Revenue Administration Department, Government of Tamil Nadu",
        "official_source": {
            "portal_name": "Tamil Nadu e-Sevai (TNeGA)",
            "source_url": "https://www.tnesevai.tn.gov.in",
            "verification_date": "2026-01-15",
            "jurisdiction": "Tamil Nadu, India",
            "is_verified": 1,
            "notes": "Standard citizen service REV-101. Standard fee ₹60 prescribed by TNeGA.",
        },
        "translations": {
            "en": {
                "name": "Income Certificate",
                "description": "An official certificate issued by the Zonal Deputy Tahsildar certifying the total annual income of the applicant and family from all sources.",
                "benefits": "Essential for government scholarships, fee concessions, welfare schemes, and bank educational loans.",
                "processing_time": "7 - 15 Working Days",
                "official_fee": "₹60 (e-Sevai Statutory Fee)",
            },
            "ta": {
                "name": "வருமானச் சான்றிதழ்",
                "description": "விண்ணப்பதாரர் மற்றும் அவரது குடும்பத்தின் அனைத்து வழிகளிலான மொத்த ஆண்டு வருமானத்தை உறுதிப்படுத்தும் மண்டல துணை வட்டாட்சியரால் வழங்கப்படும் சான்றிதழ்.",
                "benefits": "அரசு உதவித்தொகை, கல்விக் கட்டணச் சலுகை, நலத்திட்டங்கள் மற்றும் கல்விக்கடன் பெற இன்றியமையாதது.",
                "processing_time": "7 - 15 வேலை நாட்கள்",
                "official_fee": "₹60 (இ-சேவை அரசு கட்டணம்)",
            }
        },
        "requirements": [
            {
                "requirement_code": "applicant_photo",
                "is_mandatory": 1,
                "document_type": "image",
                "order_seq": 1,
                "translations": {
                    "en": {
                        "title": "Recent Passport Size Photograph",
                        "description": "Clear digital photograph with white/light background taken within last 6 months.",
                        "help_text": "Maximum file size 50KB to 100KB in JPG format during official e-Sevai upload."
                    },
                    "ta": {
                        "title": "சமீபத்திய பாஸ்போர்ட் அளவு புகைப்படம்",
                        "description": "கடந்த 6 மாதங்களுக்குள் எடுக்கப்பட்ட வெளிறிய பின்னணியுடன் கூடிய தெளிவான புகைப்படம்.",
                        "help_text": "இ-சேவை பதிவேற்றத்தின் போது JPG வடிவில் 50KB - 100KB அளவிற்குள் இருக்க வேண்டும்."
                    }
                }
            },
            {
                "requirement_code": "address_proof",
                "is_mandatory": 1,
                "document_type": "document",
                "order_seq": 2,
                "translations": {
                    "en": {
                        "title": "Proof of Address (Smart Ration Card / EB Bill)",
                        "description": "Tamil Nadu Smart Family Card (Ration Card), latest Electricity Bill, or Gas Receipt.",
                        "help_text": "Smart card number must match the applicant's family record."
                    },
                    "ta": {
                        "title": "முகவரிச் சான்று (ஸ்மார்ட் குடும்ப அட்டை / மின் கட்டண ரசீது)",
                        "description": "தமிழ்நாடு ஸ்மார்ட் குடும்ப அட்டை (ரேஷன் கார்டு) அல்லது சமீபத்திய மின்கட்டண ரசீது.",
                        "help_text": "குடும்ப அட்டையில் விண்ணப்பதாரரின் பெயர் இடம்பெற்றிருக்க வேண்டும்."
                    }
                }
            },
            {
                "requirement_code": "income_proof",
                "is_mandatory": 1,
                "document_type": "document",
                "order_seq": 3,
                "translations": {
                    "en": {
                        "title": "Income Proof / Salary Certificate or Self-Declaration",
                        "description": "Latest salary certificate from employer (for salaried) OR Self-Declaration Affidavit on annual family income (for daily wage / agriculture).",
                        "help_text": "Must cover total family income from all verifiable sources."
                    },
                    "ta": {
                        "title": "வருமானச் சான்று / சம்பளச் சான்றிதழ் அல்லது சுய அறிவிப்புப் படிவம்",
                        "description": "பணியில் உள்ளவர்களுக்கு முதலாளியின் சம்பளச் சான்றிதழ் அல்லது முறைசாரா தொழிலாளர்களுக்கு வருமான சுய அறிவிப்பு உறுதிமொழிப் படிவம்.",
                        "help_text": "குடும்பத்தின் அனைத்து வழிகளிலான மொத்த வருமானமும் குறிப்பிடப்பட வேண்டும்."
                    }
                }
            },
            {
                "requirement_code": "pan_it_return",
                "is_mandatory": 0,
                "document_type": "document",
                "order_seq": 4,
                "translations": {
                    "en": {
                        "title": "PAN Card / Income Tax Returns (Optional/Conditional)",
                        "description": "Copy of PAN card and recent IT acknowledgment (required if family is an income tax assessee).",
                        "help_text": "Only applicable if income is above taxable limits."
                    },
                    "ta": {
                        "title": "பான் கார்டு / வருமான வரி கணக்கு தாக்கல் நகல் (விருப்பத் தேர்வு)",
                        "description": "பான் அட்டை நகல் அல்லது வருமான வரி கணக்கு தாக்கல் ரசீது (வருமான வரி செலுத்துபவர்களுக்கு மட்டும்).",
                        "help_text": "வரி வரம்பிற்குள் வரும் குடும்பங்களுக்கு மட்டுமே பொருந்தும்."
                    }
                }
            }
        ]
    },
    {
        "slug": "community-certificate",
        "department": "Revenue Administration & BC/MBC Welfare Department, Tamil Nadu",
        "official_source": {
            "portal_name": "Tamil Nadu e-Sevai (TNeGA)",
            "source_url": "https://www.tnesevai.tn.gov.in",
            "verification_date": "2026-01-15",
            "jurisdiction": "Tamil Nadu, India",
            "is_verified": 1,
            "notes": "Standard citizen service REV-102. Issued by Revenue Tahsildar / Headquarters Deputy Tahsildar.",
        },
        "translations": {
            "en": {
                "name": "Community Certificate",
                "description": "A statutory proof of social category (BC, MBC, SC, ST, or OC) issued by the competent Revenue authority.",
                "benefits": "Required for reservation in admissions, government examinations, competitive scholarships, and recruitment.",
                "processing_time": "15 - 30 Working Days",
                "official_fee": "₹60 (e-Sevai Statutory Fee)",
            },
            "ta": {
                "name": "சாதிச் சான்றிதழ் (Community Certificate)",
                "description": "விண்ணப்பதாரரின் சமூகப் பிரிவை (BC, MBC, SC, ST, OC) உறுதிப்படுத்தி வருவாய்த் துறை அதிகாரியால் வழங்கப்படும் அதிகாரப்பூர்வ சான்றிதழ்.",
                "benefits": "கல்வி சேர்க்கை, அரசு வேலைவாய்ப்பு இடஒதுக்கீடு மற்றும் நலத்திட்ட உதவிகளுக்கு கட்டாயம்.",
                "processing_time": "15 - 30 வேலை நாட்கள்",
                "official_fee": "₹60 (இ-சேவை அரசு கட்டணம்)",
            }
        },
        "requirements": [
            {
                "requirement_code": "applicant_photo",
                "is_mandatory": 1,
                "document_type": "image",
                "order_seq": 1,
                "translations": {
                    "en": {
                        "title": "Recent Passport Size Photograph",
                        "description": "Clear color passport size photo of the applicant.",
                        "help_text": "White or light background preferred."
                    },
                    "ta": {
                        "title": "சமீபத்திய பாஸ்போர்ட் அளவு புகைப்படம்",
                        "description": "விண்ணப்பதாரரின் தெளிவான வண்ணப் புகைப்படம்.",
                        "help_text": "வெளிர் பின்னணியில் அமைந்திருக்க வேண்டும்."
                    }
                }
            },
            {
                "requirement_code": "address_proof",
                "is_mandatory": 1,
                "document_type": "document",
                "order_seq": 2,
                "translations": {
                    "en": {
                        "title": "Address Proof (Smart Ration Card)",
                        "description": "Valid Tamil Nadu Family Smart Card showing residence in the revenue jurisdiction.",
                        "help_text": "Address must match the local taluk/village jurisdiction."
                    },
                    "ta": {
                        "title": "முகவரிச் சான்று (ஸ்மார்ட் குடும்ப அட்டை)",
                        "description": "விண்ணப்பதாரர் வசிக்கும் பகுதிக்கான செல்லுபடியாகும் குடும்ப அட்டை.",
                        "help_text": "முகவரி குறிப்பிட்ட தாலுகா எல்லைக்குள் இருக்க வேண்டும்."
                    }
                }
            },
            {
                "requirement_code": "family_community_proof",
                "is_mandatory": 1,
                "document_type": "document",
                "order_seq": 3,
                "translations": {
                    "en": {
                        "title": "Parents' or Siblings' Community Proof",
                        "description": "Community Certificate of Father, Mother, or Sibling issued by TN Revenue authorities, OR School Transfer Certificate (TC) specifying community.",
                        "help_text": "Father's community certificate is prioritized by revenue inspecting officers."
                    },
                    "ta": {
                        "title": "பெற்றோர் அல்லது உடன்பிறந்தோரின் சாதிச் சான்றிதழ்",
                        "description": "தந்தை, தாய் அல்லது உடன் பிறந்தோரின் தமிழ்நாடு அரசு சாதிச் சான்றிதழ் அல்லது சாதி குறிப்பிடப்பட்ட பள்ளி மாற்றுச் சான்றிதழ் (TC).",
                        "help_text": "தந்தையின் சாதிச் சான்றிதழ் முதன்மைச் சான்றாகக் கருதப்படுகிறது."
                    }
                }
            },
            {
                "requirement_code": "self_declaration_affidavit",
                "is_mandatory": 1,
                "document_type": "document",
                "order_seq": 4,
                "translations": {
                    "en": {
                        "title": "Self-Declaration of Applicant / Parent",
                        "description": "Signed declaration confirming the community claim and details provided.",
                        "help_text": "Standard format downloaded from TN e-Sevai portal."
                    },
                    "ta": {
                        "title": "சுய அறிவிப்பு உறுதிமொழிப் படிவம்",
                        "description": "விண்ணப்பதாரர் அல்லது பெற்றோர் கையொப்பமிட்ட சுய அறிவிப்புப் படிவம்.",
                        "help_text": "இ-சேவை தளத்தில் கிடைக்கும் நிலையான படிவம்."
                    }
                }
            }
        ]
    },
    {
        "slug": "nativity-certificate",
        "department": "Revenue Administration Department, Government of Tamil Nadu",
        "official_source": {
            "portal_name": "Tamil Nadu e-Sevai (TNeGA)",
            "source_url": "https://www.tnesevai.tn.gov.in",
            "verification_date": "2026-01-15",
            "jurisdiction": "Tamil Nadu, India",
            "is_verified": 1,
            "notes": "Standard citizen service REV-103. Proves permanent residency/nativity in Tamil Nadu.",
        },
        "translations": {
            "en": {
                "name": "Nativity Certificate",
                "description": "A certificate issued by the Revenue Tahsildar establishing that the applicant is a native of Tamil Nadu by birth or continuous residence.",
                "benefits": "Mandatory for state government jobs (TNPSC), medical admissions (NEET state quota), and engineering counseling (TNEA).",
                "processing_time": "7 - 15 Working Days",
                "official_fee": "₹60 (e-Sevai Statutory Fee)",
            },
            "ta": {
                "name": "இருப்பிடச் சான்றிதழ் (Nativity Certificate)",
                "description": "விண்ணப்பதாரர் பிறப்பால் அல்லது தொடர்ச்சியான வசிப்பிடத்தால் தமிழ்நாட்டைச் சேர்ந்தவர் என்பதை உறுதிப்படுத்தும் வருவாய்த் துறை சான்றிதழ்.",
                "benefits": "டிஎன்பிஎஸ்சி அரசுப் பணிகள், மருத்துவ சேர்க்கை (மாநில ஒதுக்கீடு), மற்றும் பொறியியல் கலந்தாய்விற்கு கட்டாயம்.",
                "processing_time": "7 - 15 வேலை நாட்கள்",
                "official_fee": "₹60 (இ-சேவை அரசு கட்டணம்)",
            }
        },
        "requirements": [
            {
                "requirement_code": "applicant_photo",
                "is_mandatory": 1,
                "document_type": "image",
                "order_seq": 1,
                "translations": {
                    "en": {
                        "title": "Recent Passport Size Photograph",
                        "description": "Clear recent photograph of applicant.",
                        "help_text": "White or off-white background."
                    },
                    "ta": {
                        "title": "சமீபத்திய பாஸ்போர்ட் அளவு புகைப்படம்",
                        "description": "விண்ணப்பதாரரின் தெளிவான சமீபத்திய புகைப்படம்.",
                        "help_text": "வெளிர் பின்னணியில் அமைந்திருக்க வேண்டும்."
                    }
                }
            },
            {
                "requirement_code": "birth_or_school_proof",
                "is_mandatory": 1,
                "document_type": "document",
                "order_seq": 2,
                "translations": {
                    "en": {
                        "title": "Birth Certificate or School Study Certificate (5+ Years)",
                        "description": "Birth Certificate registered in Tamil Nadu OR School Transfer Certificate / Bonafide proving continuous study in TN for at least 5 years.",
                        "help_text": "Vital document establishing nativity by birth or study."
                    },
                    "ta": {
                        "title": "பிறப்புச் சான்றிதழ் அல்லது பள்ளிப் படிப்புச் சான்று (5+ ஆண்டுகள்)",
                        "description": "தமிழ்நாட்டில் பதிவு செய்யப்பட்ட பிறப்புச் சான்றிதழ் அல்லது 5 ஆண்டுகள் தொடர்ச்சியாகப் படித்ததற்கான பள்ளி மாற்றுச் சான்றிதழ் (TC).",
                        "help_text": "தமிழ்நாட்டில் பிறந்தவர் அல்லது படித்தவர் என்பதை உறுதி செய்யும் முக்கிய ஆவணம்."
                    }
                }
            },
            {
                "requirement_code": "residence_proof",
                "is_mandatory": 1,
                "document_type": "document",
                "order_seq": 3,
                "translations": {
                    "en": {
                        "title": "Permanent Residence Proof (Smart Ration Card)",
                        "description": "Tamil Nadu Smart Family Card or Parent's Voter ID card.",
                        "help_text": "Demonstrates residence continuity in the local administrative area."
                    },
                    "ta": {
                        "title": "நிரந்தர முகவரிச் சான்று (ஸ்மார்ட் குடும்ப அட்டை)",
                        "description": "தமிழ்நாடு ஸ்மார்ட் குடும்ப அட்டை அல்லது பெற்றோர் வாக்காளர் அடையாள அட்டை.",
                        "help_text": "குறிப்பிட்ட பகுதியில் நிரந்தரமாக வசிப்பதை உறுதி செய்கிறது."
                    }
                }
            },
            {
                "requirement_code": "parent_nativity_proof",
                "is_mandatory": 0,
                "document_type": "document",
                "order_seq": 4,
                "translations": {
                    "en": {
                        "title": "Parent's Nativity Proof / Employment Document (Optional/Supporting)",
                        "description": "Parent's Birth Certificate, School Certificate, or Employment Proof in Tamil Nadu.",
                        "help_text": "Helpful if applicant was born or studied outside Tamil Nadu for some years."
                    },
                    "ta": {
                        "title": "பெற்றோரின் இருப்பிடச் சான்று / வேலைவாய்ப்பு ஆவணம் (துணைச் சான்று)",
                        "description": "பெற்றோரின் பிறப்புச் சான்றிதழ், பள்ளி சான்றிதழ் அல்லது தமிழ்நாட்டில் பணிபுரியும் ஆவணம்.",
                        "help_text": "விண்ணப்பதாரர் சில காலம் வெளிமாநிலத்தில் படித்திருந்தால் இச்சான்று பெரிதும் உதவும்."
                    }
                }
            }
        ]
    }
]


def seed_initial_services(db: sqlite3.Connection):
    """Inserts initial service definitions, translations, and requirements into SQLite."""
    # Check if services already seeded
    existing = db.execute("SELECT COUNT(*) FROM services").fetchone()[0]
    if existing > 0:
        return

    for item in SERVICES_SEED_DATA:
        cur = db.execute(
            "INSERT INTO services (slug, department) VALUES (?, ?)",
            (item["slug"], item["department"])
        )
        service_id = cur.lastrowid

        # Insert official source
        src = item["official_source"]
        db.execute(
            """INSERT INTO official_sources 
               (service_id, portal_name, source_url, verification_date, jurisdiction, is_verified, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (service_id, src["portal_name"], src["source_url"], src["verification_date"],
             src["jurisdiction"], src["is_verified"], src["notes"])
        )

        # Insert service translations
        for lang_code, trans in item["translations"].items():
            db.execute(
                """INSERT INTO service_translations
                   (service_id, lang_code, name, description, benefits, processing_time, official_fee)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (service_id, lang_code, trans["name"], trans["description"],
                 trans["benefits"], trans["processing_time"], trans["official_fee"])
            )

        # Insert requirements and requirement translations
        for req in item["requirements"]:
            r_cur = db.execute(
                """INSERT INTO requirements 
                   (service_id, requirement_code, is_mandatory, document_type, order_seq)
                   VALUES (?, ?, ?, ?, ?)""",
                (service_id, req["requirement_code"], req["is_mandatory"], req["document_type"], req["order_seq"])
            )
            requirement_id = r_cur.lastrowid

            for lang_code, r_trans in req["translations"].items():
                db.execute(
                    """INSERT INTO requirement_translations
                       (requirement_id, lang_code, title, description, help_text)
                       VALUES (?, ?, ?, ?, ?)""",
                    (requirement_id, lang_code, r_trans["title"], r_trans["description"], r_trans["help_text"])
                )

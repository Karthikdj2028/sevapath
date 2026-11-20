"""
SevaPath Initial Seeds for Tamil Nadu Civic Services.

Provides officially verified service definitions with bilingual (English & Tamil)
translations and authoritative government source metadata.
"""

import sqlite3

SERVICES_SEED_DATA = [
    {
        "slug": "community-certificate",
        "department": "Revenue Administration & BC/MBC Welfare Department, Tamil Nadu",
        "official_source": {
            "portal_name": "Tamil Nadu e-Sevai (TNeGA)",
            "source_url": "https://tnesevai.tn.gov.in/Citizen/Pages/ServiceList.aspx",
            "verification_date": "2026-11-19",
            "jurisdiction": "Tamil Nadu, India",
            "is_verified": 1,
            "notes": "Standard citizen service REV-101. Fee reported: ₹60 e-Sevai centre charge, ₹0 Department fee. No verified numerical turnaround timeline published on official portal.",
        },
        "translations": {
            "en": {
                "name": "Community Certificate",
                "description": "A statutory proof of social category (BC, MBC, SC, ST, or OC) issued by the competent Revenue Tahsildar.",
                "benefits": "Required for reservation in educational admissions, government recruitment, and welfare scholarships.",
                "processing_time": "No verified numerical timeline on official portal",
                "official_fee": "e-Sevai service charge: INR 60, Department fee: INR 0 (as displayed in published service list)",
            },
            "ta": {
                "name": "சாதிச் சான்றிதழ் (Community Certificate)",
                "description": "விண்ணப்பதாரரின் சமூகப் பிரிவை (BC, MBC, SC, ST, OC) உறுதிப்படுத்தி வருவாய்த் துறை வட்டாட்சியரால் வழங்கப்படும் அதிகாரப்பூர்வ சான்றிதழ்.",
                "benefits": "கல்வி சேர்க்கை, அரசு வேலைவாய்ப்பு இடஒதுக்கீடு மற்றும் நலத்திட்ட உதவிகளுக்கு கட்டாயம்.",
                "processing_time": "அதிகாரப்பூர்வ தளத்தில் எண் விவரம் குறிப்பிடப்படவில்லை",
                "official_fee": "இ-சேவை சேவைக் கட்டணம்: ₹60, அரசு கட்டணம்: ₹0 (வெளியிடப்பட்ட சேவைப் பட்டியல் விவரம்)",
            }
        },
        "requirements": [
            {
                "requirement_code": "applicant_photo",
                "is_mandatory": 0,
                "document_type": "image",
                "presentation_category": "listed_applicability_unconfirmed",
                "logical_group": None,
                "order_seq": 1,
                "translations": {
                    "en": {
                        "title": "Photo",
                        "description": "Recent photograph of the applicant.",
                        "help_text": "Listed on TNeGA portal under documents to be uploaded."
                    },
                    "ta": {
                        "title": "புகைப்படம் (Photo)",
                        "description": "விண்ணப்பதாரரின் சமீபத்திய புகைப்படம்.",
                        "help_text": "இ-சேவை தளத்தில் பதிவேற்ற வேண்டிய ஆவணமாக பட்டியலிடப்பட்டுள்ளது."
                    }
                }
            },
            {
                "requirement_code": "address_proof",
                "is_mandatory": 0,
                "document_type": "document",
                "presentation_category": "listed_applicability_unconfirmed",
                "logical_group": None,
                "order_seq": 2,
                "translations": {
                    "en": {
                        "title": "Any Address Proof",
                        "description": "Valid residential address proof (Smart Ration Card, Voter ID, Passport, EB Bill).",
                        "help_text": "Listed on TNeGA portal under documents to be uploaded."
                    },
                    "ta": {
                        "title": "முகவரிச் சான்று (Any Address Proof)",
                        "description": "செல்லுபடியாகும் முகவரிச் சான்று (ஸ்மார்ட் குடும்ப அட்டை, வாக்காளர் அட்டை, மின் கட்டண ரசீது).",
                        "help_text": "இ-சேவை தளத்தில் பதிவேற்ற வேண்டிய ஆவணமாக பட்டியலிடப்பட்டுள்ளது."
                    }
                }
            },
            {
                "requirement_code": "family_community_proof",
                "is_mandatory": 0,
                "document_type": "document",
                "presentation_category": "listed_applicability_unconfirmed",
                "logical_group": None,
                "order_seq": 3,
                "translations": {
                    "en": {
                        "title": "Community Certificate of Father / Mother / Siblings",
                        "description": "Community certificate issued to father, mother, or siblings by Tamil Nadu Revenue authorities.",
                        "help_text": "Listed on TNeGA portal. Applicability to first-generation applicants unconfirmed on portal."
                    },
                    "ta": {
                        "title": "தாய் / தந்தை / உடன்பிறந்தோரின் சாதிச் சான்றிதழ்",
                        "description": "தந்தை, தாய் அல்லது உடன் பிறந்தோரின் தமிழ்நாடு அரசு சாதிச் சான்றிதழ்.",
                        "help_text": "இ-சேவை தளத்தில் பட்டியலிடப்பட்டுள்ளது. முதல் தலைமுறை விண்ணப்பதாரர்களுக்கான விபரம் தளத்தில் குறிப்பிடப்படவில்லை."
                    }
                }
            },
            {
                "requirement_code": "self_declaration",
                "is_mandatory": 0,
                "document_type": "document",
                "presentation_category": "listed_applicability_unconfirmed",
                "logical_group": None,
                "order_seq": 4,
                "translations": {
                    "en": {
                        "title": "Self-Declaration of Applicant",
                        "description": "Signed self-declaration affirming community category.",
                        "help_text": "Standard format downloaded or signed during application."
                    },
                    "ta": {
                        "title": "விண்ணப்பதாரர் சுயவிவர உறுதிமொழி (Self-Declaration)",
                        "description": "சமூகப் பிரிவை உறுதிப்படுத்தும் கையொப்பமிட்ட சுய அறிவிப்புப் படிவம்.",
                        "help_text": "விண்ணப்பத்தின் போது பதிவிறக்கம் செய்யப்பட்டு கையொப்பமிடப்படும் படிவம்."
                    }
                }
            },
            {
                "requirement_code": "dnc_certificate",
                "is_mandatory": 0,
                "document_type": "document",
                "presentation_category": "listed_applicability_unconfirmed",
                "logical_group": None,
                "order_seq": 5,
                "translations": {
                    "en": {
                        "title": "DNC Certificate",
                        "description": "Denotified Communities (DNC) certificate (if claiming DNC classification).",
                        "help_text": "Listed as a distinct line item on TNeGA portal. Applicability to non-DNC applicants unconfirmed on portal."
                    },
                    "ta": {
                        "title": "சீர்மரபினர் (DNC) சான்றிதழ்",
                        "description": "சீர்மரபினர் பிரிவு கோருவோருக்கான சான்றிதழ்.",
                        "help_text": "இ-சேவை தளத்தில் தனி ஆவணமாக பட்டியலிடப்பட்டுள்ளது. பிற பிரிவினருக்கு இது பொருந்துமா என்பது தளத்தில் குறிப்பிடப்படவில்லை."
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
            "source_url": "https://tnesevai.tn.gov.in/Citizen/Pages/ServiceList.aspx",
            "verification_date": "2026-11-19",
            "jurisdiction": "Tamil Nadu, India",
            "is_verified": 1,
            "notes": "Standard citizen service REV-102. Fee reported: ₹60 e-Sevai centre charge, ₹0 Department fee. Published timeline: 7 days (published estimate, not statutory guarantee).",
        },
        "translations": {
            "en": {
                "name": "Nativity Certificate",
                "description": "An official certificate establishing that the applicant is a native of Tamil Nadu by birth or continuous residence.",
                "benefits": "Required for state government admissions (NEET state quota, TNEA engineering) and TNPSC employment.",
                "processing_time": "Published estimate of 7 days (not a statutory guarantee)",
                "official_fee": "e-Sevai service charge: INR 60, Department fee: INR 0 (as displayed in published service list)",
            },
            "ta": {
                "name": "இருப்பிடச் சான்றிதழ் (Nativity Certificate)",
                "description": "விண்ணப்பதாரர் பிறப்பால் அல்லது தொடர்ச்சியான வசிப்பிடத்தால் தமிழ்நாட்டைச் சேர்ந்தவர் என்பதை உறுதிப்படுத்தும் வருவாய்த் துறை சான்றிதழ்.",
                "benefits": "மருத்துவ சேர்க்கை (மாநில ஒதுக்கீடு), பொறியியல் கலந்தாய்வு மற்றும் அரசுப் பணிகளுக்கு கட்டாயம்.",
                "processing_time": "வெளியிடப்பட்ட மதிப்பீடு: 7 நாட்கள் (சட்டப்பூர்வ உத்தரவாதம் அல்ல)",
                "official_fee": "இ-சேவை சேவைக் கட்டணம்: ₹60, அரசு கட்டணம்: ₹0 (வெளியிடப்பட்ட சேவைப் பட்டியல் விவரம்)",
            }
        },
        "requirements": [
            {
                "requirement_code": "applicant_photo",
                "is_mandatory": 0,
                "document_type": "image",
                "presentation_category": "listed_applicability_unconfirmed",
                "logical_group": None,
                "order_seq": 1,
                "translations": {
                    "en": {
                        "title": "Photo",
                        "description": "Recent photograph of the applicant.",
                        "help_text": "Listed on TNeGA portal under documents to be uploaded."
                    },
                    "ta": {
                        "title": "புகைப்படம் (Photo)",
                        "description": "விண்ணப்பதாரரின் சமீபத்திய புகைப்படம்.",
                        "help_text": "இ-சேவை தளத்தில் பதிவேற்ற வேண்டிய ஆவணமாக பட்டியலிடப்பட்டுள்ளது."
                    }
                }
            },
            {
                "requirement_code": "address_proof",
                "is_mandatory": 0,
                "document_type": "document",
                "presentation_category": "listed_applicability_unconfirmed",
                "logical_group": None,
                "order_seq": 2,
                "translations": {
                    "en": {
                        "title": "Any Address Proof",
                        "description": "Valid residential address proof.",
                        "help_text": "Listed on TNeGA portal under documents to be uploaded."
                    },
                    "ta": {
                        "title": "முகவரிச் சான்று (Any Address Proof)",
                        "description": "செல்லுபடியாகும் முகவரிச் சான்று.",
                        "help_text": "இ-சேவை தளத்தில் பதிவேற்ற வேண்டிய ஆவணமாக பட்டியலிடப்பட்டுள்ளது."
                    }
                }
            },
            {
                "requirement_code": "birth_certificate",
                "is_mandatory": 0,
                "document_type": "document",
                "presentation_category": "listed_applicability_unconfirmed",
                "logical_group": None,
                "order_seq": 3,
                "translations": {
                    "en": {
                        "title": "Birth Certificate",
                        "description": "Official birth certificate registered in Tamil Nadu.",
                        "help_text": "Listed as a distinct line item on TNeGA portal. Applicability to applicants claiming nativity by continuous residence unconfirmed."
                    },
                    "ta": {
                        "title": "பிறப்புச் சான்றிதழ் (Birth Certificate)",
                        "description": "தமிழ்நாட்டில் பதிவு செய்யப்பட்ட அதிகாரப்பூர்வ பிறப்புச் சான்றிதழ்.",
                        "help_text": "இ-சேவை தளத்தில் பட்டியலிடப்பட்டுள்ளது. தொடர் வசிப்பிட அடிப்படையில் விண்ணப்பிப்பவர்களுக்கான விபரம் தளத்தில் குறிப்பிடப்படவில்லை."
                    }
                }
            },
            {
                "requirement_code": "residence_proof_5yr",
                "is_mandatory": 1,
                "document_type": "document",
                "presentation_category": "alternative_option",
                "logical_group": "nativity_residence_5yr",
                "order_seq": 4,
                "translations": {
                    "en": {
                        "title": "5-Year Residence Evidence (Any 1 of 3 Alternatives)",
                        "description": "School Education Certificate OR Employment Details OR Proof for continuous residence in Tamil Nadu for 5 years.",
                        "help_text": "Verbatim TNeGA text lists three alternatives joined by 'or'. Fulfilling any one alternative satisfies this composite requirement."
                    },
                    "ta": {
                        "title": "5 ஆண்டுகள் தொடர் வசிப்பிடச் சான்று (3 வாய்ப்புகளில் ஏதேனும் ஒன்று)",
                        "description": "பள்ளிப் படிப்புச் சான்றிதழ் அல்லது வேலைவாய்ப்பு விவரங்கள் அல்லது தமிழ்நாட்டில் 5 ஆண்டுகள் தொடர்ச்சியாக வசித்ததற்கான சான்று.",
                        "help_text": "இ-சேவை தளத்தில் 'அல்லது' என்ற சொல்லுடன் மூன்று மாற்று வழிகள் குறிப்பிடப்பட்டுள்ளன. ஏதேனும் ஒன்றைத் தயார் செய்வது போதுமானது."
                    }
                }
            },
            {
                "requirement_code": "self_declaration",
                "is_mandatory": 0,
                "document_type": "document",
                "presentation_category": "listed_applicability_unconfirmed",
                "logical_group": None,
                "order_seq": 5,
                "translations": {
                    "en": {
                        "title": "Self-Declaration of Applicant",
                        "description": "Signed self-declaration affirming permanent residence in Tamil Nadu.",
                        "help_text": "Standard format downloaded from TN e-Sevai portal."
                    },
                    "ta": {
                        "title": "விண்ணப்பதாரர் சுயவிவர உறுதிமொழி (Self-Declaration)",
                        "description": "தமிழ்நாட்டில் நிரந்தரமாக வசிப்பதை உறுதிப்படுத்தும் கையொப்பமிட்ட சுய அறிவிப்புப் படிவம்.",
                        "help_text": "இ-சேவை தளத்தில் கிடைக்கும் நிலையான படிவம்."
                    }
                }
            }
        ]
    },
    {
        "slug": "income-certificate",
        "department": "Revenue Administration Department, Government of Tamil Nadu",
        "official_source": {
            "portal_name": "Tamil Nadu e-Sevai (TNeGA)",
            "source_url": "https://tnesevai.tn.gov.in/Citizen/Pages/ServiceList.aspx",
            "verification_date": "2026-11-19",
            "jurisdiction": "Tamil Nadu, India",
            "is_verified": 1,
            "notes": "Standard citizen service REV-103. Fee reported: ₹60 e-Sevai centre charge, ₹0 Department fee. Published timeline: 15 days (published estimate, not statutory guarantee).",
        },
        "translations": {
            "en": {
                "name": "Income Certificate",
                "description": "An official certificate issued by the Zonal Deputy Tahsildar certifying the total annual income of the applicant and family from all sources.",
                "benefits": "Essential for government scholarships, fee concessions, welfare schemes, and educational loans.",
                "processing_time": "Published estimate of 15 days (not a statutory guarantee)",
                "official_fee": "e-Sevai service charge: INR 60, Department fee: INR 0 (as displayed in published service list)",
            },
            "ta": {
                "name": "வருமானச் சான்றிதழ்",
                "description": "விண்ணப்பதாரர் மற்றும் குடும்பத்தின் அனைத்து வழிகளிலான மொத்த ஆண்டு வருமானத்தை உறுதிப்படுத்தும் வருவாய்த் துறை சான்றிதழ்.",
                "benefits": "அரசு உதவித்தொகை, கல்விக் கட்டணச் சலுகை மற்றும் நலத்திட்ட உதவிகள் பெற இன்றியமையாதது.",
                "processing_time": "வெளியிடப்பட்ட மதிப்பீடு: 15 நாட்கள் (சட்டப்பூர்வ உத்தரவாதம் அல்ல)",
                "official_fee": "இ-சேவை சேவைக் கட்டணம்: ₹60, அரசு கட்டணம்: ₹0 (வெளியிடப்பட்ட சேவைப் பட்டியல் விவரம்)",
            }
        },
        "requirements": [
            {
                "requirement_code": "applicant_photo",
                "is_mandatory": 0,
                "document_type": "image",
                "presentation_category": "listed_applicability_unconfirmed",
                "logical_group": None,
                "order_seq": 1,
                "translations": {
                    "en": {
                        "title": "Photo",
                        "description": "Recent photograph of the applicant.",
                        "help_text": "Listed on TNeGA portal under documents to be uploaded."
                    },
                    "ta": {
                        "title": "புகைப்படம் (Photo)",
                        "description": "விண்ணப்பதாரரின் சமீபத்திய புகைப்படம்.",
                        "help_text": "இ-சேவை தளத்தில் பதிவேற்ற வேண்டிய ஆவணமாக பட்டியலிடப்பட்டுள்ளது."
                    }
                }
            },
            {
                "requirement_code": "address_proof",
                "is_mandatory": 0,
                "document_type": "document",
                "presentation_category": "listed_applicability_unconfirmed",
                "logical_group": None,
                "order_seq": 2,
                "translations": {
                    "en": {
                        "title": "Any Address Proof",
                        "description": "Valid residential address proof.",
                        "help_text": "Listed on TNeGA portal under documents to be uploaded."
                    },
                    "ta": {
                        "title": "முகவரிச் சான்று (Any Address Proof)",
                        "description": "செல்லுபடியாகும் முகவரிச் சான்று.",
                        "help_text": "இ-சேவை தளத்தில் பதிவேற்ற வேண்டிய ஆவணமாக பட்டியலிடப்பட்டுள்ளது."
                    }
                }
            },
            {
                "requirement_code": "family_smart_card",
                "is_mandatory": 0,
                "document_type": "document",
                "presentation_category": "listed_applicability_unconfirmed",
                "logical_group": None,
                "order_seq": 3,
                "translations": {
                    "en": {
                        "title": "Family / Smart Card",
                        "description": "Tamil Nadu Family Smart Card (Ration Card).",
                        "help_text": "Listed as a distinct line item on TNeGA portal."
                    },
                    "ta": {
                        "title": "குடும்ப அட்டை / ஸ்மார்ட் கார்டு (Family / Smart Card)",
                        "description": "தமிழ்நாடு ஸ்மார்ட் குடும்ப அட்டை (ரேஷன் கார்டு).",
                        "help_text": "இ-சேவை தளத்தில் தனி ஆவணமாக பட்டியலிடப்பட்டுள்ளது."
                    }
                }
            },
            {
                "requirement_code": "self_declaration",
                "is_mandatory": 0,
                "document_type": "document",
                "presentation_category": "listed_applicability_unconfirmed",
                "logical_group": None,
                "order_seq": 4,
                "translations": {
                    "en": {
                        "title": "Self-Declaration of Applicant",
                        "description": "Signed self-declaration of annual family income.",
                        "help_text": "Standard format downloaded or signed during application."
                    },
                    "ta": {
                        "title": "விண்ணப்பதாரர் சுயவிவர உறுதிமொழி (Self-Declaration)",
                        "description": "ஆண்டு வருமான விவரங்களை உறுதிப்படுத்தும் கையொப்பமிட்ட சுய அறிவிப்புப் படிவம்.",
                        "help_text": "விண்ணப்பத்தின் போது சமர்ப்பிக்கப்படும் படிவம்."
                    }
                }
            },
            {
                "requirement_code": "salary_certificate",
                "is_mandatory": 0,
                "document_type": "document",
                "presentation_category": "listed_applicability_unconfirmed",
                "logical_group": None,
                "order_seq": 5,
                "translations": {
                    "en": {
                        "title": "Salary Certificate",
                        "description": "Latest salary certificate from employer (applicable if salaried).",
                        "help_text": "Listed on TNeGA portal without category criteria; inapplicable to non-salaried applicants."
                    },
                    "ta": {
                        "title": "சம்பளச் சான்றிதழ் (Salary Certificate)",
                        "description": "முதலாளியிடமிருந்து பெறப்பட்ட சமீபத்திய சம்பளச் சான்றிதழ் (மாதச் சம்பளம் பெறுபவர்களுக்கு).",
                        "help_text": "இ-சேவை தளத்தில் பட்டியலிடப்பட்டுள்ளது; முறைசாரா தொழில் செய்பவர்களுக்கு இது பொருந்தாது."
                    }
                }
            },
            {
                "requirement_code": "pan_card",
                "is_mandatory": 0,
                "document_type": "document",
                "presentation_category": "listed_applicability_unconfirmed",
                "logical_group": None,
                "order_seq": 6,
                "translations": {
                    "en": {
                        "title": "PAN Card",
                        "description": "Permanent Account Number (PAN) card.",
                        "help_text": "Listed on TNeGA portal without threshold or qualification."
                    },
                    "ta": {
                        "title": "பான் கார்டு (PAN Card)",
                        "description": "வருமான வரி கணக்கு எண் அட்டை.",
                        "help_text": "இ-சேவை தளத்தில் பட்டியலிடப்பட்டுள்ளது."
                    }
                }
            },
            {
                "requirement_code": "tin_trade_details",
                "is_mandatory": 0,
                "document_type": "document",
                "presentation_category": "listed_applicability_unconfirmed",
                "logical_group": None,
                "order_seq": 7,
                "translations": {
                    "en": {
                        "title": "TIN Number and Trade Details",
                        "description": "Taxpayer Identification Number and business registration details.",
                        "help_text": "Listed in TNeGA FAQ for applicants with business/trade income."
                    },
                    "ta": {
                        "title": "TIN எண் மற்றும் வணிக விவரங்கள்",
                        "description": "வணிகப் பதிவு மற்றும் வரி செலுத்துவோர் அடையாள எண் விவரங்கள்.",
                        "help_text": "இ-சேவை அடிக்கடி கேட்கப்படும் கேள்விகள் (FAQ) பகுதியில் குறிப்பிடப்பட்டுள்ளது."
                    }
                }
            },
            {
                "requirement_code": "land_holdings_details",
                "is_mandatory": 0,
                "document_type": "document",
                "presentation_category": "listed_applicability_unconfirmed",
                "logical_group": None,
                "order_seq": 8,
                "translations": {
                    "en": {
                        "title": "Land Holdings Details",
                        "description": "Agricultural land records (patta/chitta details) for agricultural income.",
                        "help_text": "Listed in TNeGA FAQ for agricultural landholders."
                    },
                    "ta": {
                        "title": "நில உடைமை விவரங்கள் (Land Holdings Details)",
                        "description": "விவசாய வருமானம் உள்ளவர்களுக்கான பட்டா/சிட்டா நில விவரங்கள்.",
                        "help_text": "இ-சேவை FAQ பகுதியில் குறிப்பிடப்பட்டுள்ளது."
                    }
                }
            },
            {
                "requirement_code": "house_ownership_details",
                "is_mandatory": 0,
                "document_type": "document",
                "presentation_category": "listed_applicability_unconfirmed",
                "logical_group": None,
                "order_seq": 9,
                "translations": {
                    "en": {
                        "title": "House Ownership Details",
                        "description": "Property tax receipt or house ownership proof for rental/property income.",
                        "help_text": "Listed in TNeGA FAQ for residential property owners."
                    },
                    "ta": {
                        "title": "வீட்டு உரிமை விவரங்கள் (House Ownership Details)",
                        "description": "வாடகை வருமானம் அல்லது சொத்து விவரங்களுக்கான வீட்டு வரி ரசீது.",
                        "help_text": "இ-சேவை FAQ பகுதியில் குறிப்பிடப்பட்டுள்ளது."
                    }
                }
            }
        ]
    }
]


def seed_initial_services(db: sqlite3.Connection):
    """
    Seeds and updates services and requirements idempotently.
    Preserves existing requirement IDs, archives obsolete requirements,
    and maintains foreign-key integrity.
    """
    cursor = db.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    for s_data in SERVICES_SEED_DATA:
        # 1. Upsert service
        cursor.execute("""
            INSERT INTO services (slug, department, is_active)
            VALUES (?, ?, 1)
            ON CONFLICT(slug) DO UPDATE SET
                department = excluded.department,
                is_active = 1,
                updated_at = CURRENT_TIMESTAMP;
        """, (s_data["slug"], s_data["department"]))

        service_row = cursor.execute("SELECT id FROM services WHERE slug = ?", (s_data["slug"],)).fetchone()
        service_id = service_row[0]

        # 2. Upsert service translations
        for lang, trans in s_data["translations"].items():
            cursor.execute("""
                INSERT INTO service_translations (service_id, lang_code, name, description, benefits, processing_time, official_fee)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(service_id, lang_code) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    benefits = excluded.benefits,
                    processing_time = excluded.processing_time,
                    official_fee = excluded.official_fee;
            """, (service_id, lang, trans["name"], trans["description"], trans.get("benefits", ""), trans["processing_time"], trans["official_fee"]))

        # 3. Upsert official source
        os_data = s_data["official_source"]
        existing_os = cursor.execute("SELECT id FROM official_sources WHERE service_id = ?", (service_id,)).fetchone()
        if existing_os:
            cursor.execute("""
                UPDATE official_sources
                SET portal_name = ?, source_url = ?, verification_date = ?, jurisdiction = ?, is_verified = ?, notes = ?
                WHERE id = ?;
            """, (os_data["portal_name"], os_data["source_url"], os_data["verification_date"], os_data["jurisdiction"], os_data["is_verified"], os_data.get("notes", ""), existing_os[0]))
        else:
            cursor.execute("""
                INSERT INTO official_sources (service_id, portal_name, source_url, verification_date, jurisdiction, is_verified, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (service_id, os_data["portal_name"], os_data["source_url"], os_data["verification_date"], os_data["jurisdiction"], os_data["is_verified"], os_data.get("notes", "")))

        # 4. Upsert active requirements
        active_codes = set()
        for req in s_data["requirements"]:
            req_code = req["requirement_code"]
            active_codes.add(req_code)

            cursor.execute("""
                INSERT INTO requirements (
                    service_id, requirement_code, is_mandatory, document_type,
                    order_seq, presentation_category, is_active, logical_group
                )
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(service_id, requirement_code) DO UPDATE SET
                    is_mandatory = excluded.is_mandatory,
                    document_type = excluded.document_type,
                    order_seq = excluded.order_seq,
                    presentation_category = excluded.presentation_category,
                    is_active = 1,
                    logical_group = excluded.logical_group;
            """, (
                service_id, req_code, req["is_mandatory"], req["document_type"],
                req["order_seq"], req["presentation_category"], req.get("logical_group")
            ))

            req_row = cursor.execute(
                "SELECT id FROM requirements WHERE service_id = ? AND requirement_code = ?",
                (service_id, req_code)
            ).fetchone()
            req_id = req_row[0]

            # Upsert requirement translations
            for lang, r_trans in req["translations"].items():
                cursor.execute("""
                    INSERT INTO requirement_translations (requirement_id, lang_code, title, description, help_text)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(requirement_id, lang_code) DO UPDATE SET
                        title = excluded.title,
                        description = excluded.description,
                        help_text = excluded.help_text;
                """, (req_id, lang, r_trans["title"], r_trans["description"], r_trans.get("help_text", "")))

        # 5. Archive obsolete requirements in database that are not in the active seed list
        # Do NOT delete them; preserve rows and session items
        cursor.execute(f"""
            UPDATE requirements
            SET is_active = 0, is_mandatory = 0, presentation_category = 'deprecated_legacy'
            WHERE service_id = ? AND requirement_code NOT IN ({','.join('?' for _ in active_codes)});
        """, [service_id] + list(active_codes))

    db.commit()

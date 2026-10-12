from rxdx_qna.chunking import build_chunks, clean_title, load_records
from rxdx_qna.index import DATA_PATH

CHUNKS = build_chunks(load_records(DATA_PATH))


def test_every_doctor_is_one_chunk():
    assert sum(c.kind == "doctor" for c in CHUNKS) == 254


def test_chunk_ids_are_unique():
    ids = [c.id for c in CHUNKS]
    assert len(ids) == len(set(ids))


def test_site_chrome_is_stripped():
    chrome = ("TAT Attention!", "Enquiry Form: Doctor Appointment", "No Fields Found.")
    for c in CHUNKS:
        if c.kind != "contact":
            assert not any(s in c.text for s in chrome), c.id


def test_contact_chunk_replaces_the_chrome_banner():
    banner = "NOTE If your inquiry is urgent"
    assert not any(banner in c.text for c in CHUNKS)
    contact = next(c for c in CHUNKS if c.id == "contact")
    assert "+91 901 409 1111" in contact.text and "90199 61402" in contact.text


def test_day_ranges_expand():
    c = next(c for c in CHUNKS if c.id == "doctor:dr-pramod-m")
    assert "in-clinic on Monday, Tuesday, Wednesday, Thursday, Friday, Saturday" in c.text


def test_doctor_chunk_carries_schedule():
    c = next(c for c in CHUNKS if c.id == "doctor:dr-deepthi-bawa")
    assert "in-clinic on Tuesday, Wednesday, Thursday" in c.text
    assert "Malleshwaram" in c.text


def test_missing_days_are_said_plainly():
    assert not any("on no published days" in c.text for c in CHUNKS)


def test_titles_lose_site_suffixes():
    assert clean_title("Dermatology Archives - RxDx Clinics") == "Dermatology"
    assert clean_title("Home Visit &#038; Setup - RxDx Clinics") == "Home Visit & Setup"


def test_mislabelled_profiles_use_the_url_name():
    c = next(c for c in CHUNKS if c.id == "doctor:dr-diya-shah")
    assert c.title == "Dr Diya Shah" and "Akhil Xavier Joseph" not in c.text
    assert "confirm with the clinic" in c.text
    titles = [c.title for c in CHUNKS if c.kind == "doctor"]
    assert len(titles) == len(set(titles))  # "Dr Sireesh V" was on 11 pages

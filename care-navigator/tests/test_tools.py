import json

import pytest

from navigator.tools import TOOLS, Toolbox, ToolError

T = Toolbox()


def find(**kw):
    args = {"speciality": None, "branch": None, "day": None, "mode": "any", "language": None, "name": None, **kw}
    return json.loads(T.run("find_doctors", args))


def test_schemas_are_strict_and_fully_required():
    for tool in TOOLS:
        s = tool["input_schema"]
        assert tool["strict"] is True and s["additionalProperties"] is False
        assert set(s["required"]) == set(s["properties"]), tool["name"]


def test_find_filters_and_reports_resolution():
    r = find(speciality="Dermatology", branch="Whitefield", day="Monday")
    assert r["branch_resolved_to"] == "RxDx Whitefield"
    assert "dr-madhu-r" in [d["slug"] for d in r["doctors"]]
    for d in r["doctors"]:
        assert all("Monday" in a["in_clinic_days"] + a["teleconsultation_days"] for a in d["availability"])


def test_results_are_capped_but_total_is_honest():
    r = find(speciality="Orthopaedics")
    assert len(r["doctors"]) == 8 and r["total_matches"] > 8


def test_language_filter():
    for d in find(language="Kannada", speciality="Paediatrics")["doctors"]:
        assert "Kannada" in d["languages"]


def test_unknown_branch_is_an_error_listing_real_branches():
    with pytest.raises(ToolError, match="RxDx Jakkur"):
        find(branch="Hebbal")


def test_unknown_speciality_gets_a_hint():
    r = find(speciality="Astrology")
    assert r["total_matches"] == 0 and "list_specialities" in r["note"]


def test_mislabelled_profile_carries_a_warning():
    d = json.loads(T.run("get_doctor", {"slug": "dr-diya-shah"}))
    assert d["name"] == "Dr Diya Shah" and "confirm" in d["warning"]


def test_booking_validates_availability():
    with pytest.raises(ToolError, match="not listed in-clinic"):
        T.run("prepare_booking_request", {"slug": "dr-madhu-r", "branch": "Whitefield", "day": "Tuesday", "mode": "in_clinic", "reason": "rash"})
    ok = json.loads(T.run("prepare_booking_request", {"slug": "dr-madhu-r", "branch": "Whitefield", "day": "Monday", "mode": "in_clinic", "reason": "rash"}))
    assert ok["status"].startswith("draft") and ok["whatsapp_link"].startswith("https://wa.me/919019961402?text=")


def test_unknown_tool_is_an_error():
    with pytest.raises(ToolError):
        T.run("delete_everything", {})


def test_every_doctor_result_has_review_search_links_not_ratings():
    from urllib.parse import unquote
    for d in find(speciality="Dermatology")["doctors"]:
        links = d["review_search_links"]
        assert set(links) == {"google", "practo"}
        assert all(u.startswith("https://www.google.com/search?q=") for u in links.values())
        assert "site:practo.com" in unquote(links["practo"])
        assert not any(k in d for k in ("rating", "stars", "review_count"))
    madhu = json.loads(T.run("get_doctor", {"slug": "dr-madhu-r"}))
    assert unquote(madhu["review_search_links"]["google"]).endswith('"Madhu R" RxDx Bengaluru reviews')

from navigator.directory import Directory, expand_days, name_disagrees_with_url, name_from_slug, roots

D = Directory()


def test_counts():
    assert (len(D.doctors), len(D.branches), len(D.specialities)) == (254, 14, 49)


def test_day_ranges_expand_and_wrap():
    assert expand_days(["Monday to Wednesday"]) == ["Monday", "Tuesday", "Wednesday"]
    assert expand_days(["Saturday to Monday"]) == ["Monday", "Saturday", "Sunday"]
    assert expand_days(["Tuesday", "Thursday"]) == ["Tuesday", "Thursday"]


def test_every_clinic_spelling_resolves_except_known_gaps():
    unresolved = {d.slug for d in D.doctors.values() if not any(s.branch for s in d.sittings)}
    assert len(unresolved) == 12  # source gap: these profiles name no branch


def test_roots_unify_spellings_and_word_forms():
    assert roots("Dermatologist") == roots("Dermatology")
    assert roots("Obstetrics & Gynecology") == roots("Obstetrician and Gynaecologist")
    assert roots("Pediatrics") == roots("Paediatrician")


def test_ent_is_not_a_substring_match():
    assert "ent" not in roots("appointment treatment")


def test_branch_resolution():
    assert D.resolve_branch("Malleswaram") == D.resolve_branch("Malleshwaram") == "rxdx-samanvay-malleswaram"
    assert D.resolve_branch("RR Nagar") == "rxdx-clinics-rajarajeshwari-nagar"
    assert D.resolve_branch("Bellandur") == "rxdx-clinics-apr-villas"
    assert D.resolve_branch("Hebbal") is None


def test_mislabelled_profiles_take_their_name_from_the_url():
    flagged = {d.slug for d in D.doctors.values() if d.needs_verification}
    assert len(flagged) == 21
    d = D.doctors["dr-diya-shah"]
    assert d.name == "Dr Diya Shah" and d.title == "" and d.overview == ""
    # "Dr Sireesh V" was stamped on 11 pages; after the fix no name repeats.
    names = [d.name for d in D.doctors.values()]
    assert len(names) == len(set(names))


def test_spelling_variants_and_seo_slugs_are_not_flagged():
    assert not name_disagrees_with_url("Dr Rajya Lakshmi", "dr-rajyalaxmi")
    assert not name_disagrees_with_url("Mr B L Suhas", "sports-massage-therapist-bl-suhas")
    assert not name_disagrees_with_url("Dr Aparna Sharma Doddamani", "dr-aparna-sharma-doddamani-pediatrician-malleshwaram")
    assert name_disagrees_with_url("Dr Sireesh V", "dr-lakshmi-v")


def test_name_from_slug():
    assert name_from_slug("dr-sukesh-m-s") == "Dr Sukesh M S"
    assert name_from_slug("ms-anushree-menon-pt") == "Ms Anushree Menon (PT)"


def test_find_is_exact():
    names = [d.name for d, _ in D.find(speciality="Dermatology", branch="rxdx-whitefield", day="Monday")]
    assert "Dr Madhu R" in names
    for d, sittings in D.find(speciality="ENT", day="Saturday"):
        assert "ent" in d._roots
        assert all("Saturday" in s.in_clinic + s.teleconsultation for s in sittings)


def test_published_days_sort_first():
    results = D.find(speciality="Dermatology")
    has_days = [any(s.in_clinic or s.teleconsultation for s in sit) for _, sit in results]
    assert has_days == sorted(has_days, reverse=True)

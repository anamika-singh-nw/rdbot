"""The RxDx doctor directory as structured, queryable data.

Retrieval over text (the rag-qna project) is the wrong tool for "which ENT doctor is in
Whitefield on a Saturday": that is a filter over fields, and a filter can be exact. This
module normalises the scrape into those fields; `tools.py` exposes them to the model.

The source is hand-maintained WordPress, so normalisation carries most of the weight:
- 25 spellings of 14 clinics ("RxDx CHANDY Clinic, Siddapura" / "RxDx Clinics, CHANDY,
  Siddapura") resolve through `BRANCH_MATCHERS`, ported from the website rebuild.
- Days arrive as lists or ranges ("Monday to Saturday").
- Speciality names vary (Gynecology/Gynaecology, Orthopedics/Orthopaedics, Paediatrician/
  Paediatrics). Matching compares word *roots*, so the -ology/-ologist family works without
  enumeration, and compares whole roots, never substrings — "ENT" must not match inside
  "appointment".
"""

from __future__ import annotations

import difflib
import html
import json
import re
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "rxdx.json"

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

BRANCH_MATCHERS: list[tuple[re.Pattern, str]] = [
    (re.compile(p, re.I), slug)
    for p, slug in [
        (r"whitefield", "rxdx-whitefield"),
        (r"kadugodi", "rxdx-kadugodi"),
        (r"chandy|siddapura", "rxdx-chandy-siddapura"),
        (r"samanvay|malleshwaram|malleswaram", "rxdx-samanvay-malleswaram"),
        (r"sarjapur|dommasandra", "rxdx-sarjapur-rd-dommasandra"),
        (r"nm medical|domlur", "rxdx-nm-medical-domlur"),
        (r"jakkur", "rxdx-jakkur"),
        (r"alpine", "rxdx-alpine-eco"),
        (r"apr villas|bellandur", "rxdx-clinics-apr-villas"),
        (r"rajarajeshwari|rr nagar", "rxdx-clinics-rajarajeshwari-nagar"),
        (r"electronic city", "electronic-city"),
        (r"budigere", "rxdx-clinics-budigere-cross"),
        (r"prestige|waterford", "prestige-waterford"),
        (r"gopalan|habitat", "rxdx-clinics-gopalan-habitat"),
    ]
]

# US → Indian/British spellings, applied before rooting so both sides meet.
SPELLING = [
    (r"gynec", "gynaec"),
    (r"pediatr", "paediatr"),
    (r"orthoped", "orthopaed"),
    (r"anesthe", "anaesthe"),
    (r"hematol", "haematol"),
    (r"otorhinolaryngolog\w*", "ent"),
]
SUFFIXES = ("ologists", "ologist", "ology", "ological", "icians", "ician", "ics", "ical", "ic", "ists", "ist", "s")
STOP = {"and", "of", "the", "consultant", "senior", "specialist", "clinic", "medicine", "doctor", "services", "service", "wellness"}


def root(word: str) -> str:
    for suf in SUFFIXES:
        if word.endswith(suf) and len(word) - len(suf) >= 3:
            return word[: -len(suf)]
    return word


def roots(text: str) -> set[str]:
    text = html.unescape(text).lower()
    for pat, rep in SPELLING:
        text = re.sub(pat, rep, text)
    return {root(w) for w in re.findall(r"[a-z]+", text) if w not in STOP}


def branch_for(clinic: str) -> str | None:
    for pat, slug in BRANCH_MATCHERS:
        if pat.search(clinic):
            return slug
    return None


def expand_days(entries: list[str]) -> list[str]:
    found: set[str] = set()
    for entry in entries:
        span = re.fullmatch(r"\s*(\w+day)\s*(?:to|-|–)\s*(\w+day)\s*", entry, re.I)
        ends = [s.capitalize() for s in span.groups()] if span else []
        if ends and all(e in DAYS for e in ends):
            i, last = DAYS.index(ends[0]), DAYS.index(ends[1])
            found.add(DAYS[i])
            while i != last:  # wraps, so "Saturday to Monday" works too
                i = (i + 1) % 7
                found.add(DAYS[i])
            continue
        found.update(d for d in DAYS if d.lower() in entry.lower())
    return [d for d in DAYS if d in found]


def _letters(s: str) -> str:
    return "".join(re.findall(r"[a-z]", re.sub(r"\b(dr|ms|mr|mrs|pt)\b", "", s.lower())))


def name_from_slug(slug: str) -> str:
    words = slug.split("-")
    honorific = {"dr": "Dr", "ms": "Ms", "mr": "Mr", "mrs": "Mrs"}.get(words[0])
    rest = [w.upper() if len(w) == 1 else w.capitalize() for w in (words[1:] if honorific else words)]
    rest = ["(PT)" if w == "Pt" else w for w in rest]
    return " ".join(([honorific] if honorific else []) + rest)


def name_disagrees_with_url(name: str, slug: str) -> bool:
    """19 scraped profiles carry another consultant's name and job title — the scraper took
    the wrong heading ("Dr Sireesh V" alone sits on 11 pages). The URL slug is the reliable
    identity. Fuzzy, so spelling variants (Rajyalaxmi / Rajya Lakshmi) are not flagged."""
    if difflib.SequenceMatcher(None, _letters(name), _letters(slug.replace("-", " "))).ratio() >= 0.75:
        return False
    # SEO slugs add words ("…-pediatrician-malleshwaram") but still contain the whole name.
    words = {w for w in re.findall(r"[a-z]+", name.lower()) if len(w) > 1} - {"dr", "ms", "mr", "mrs", "pt"}
    return not (words and words <= set(slug.split("-")))


def clean_title(title: str) -> str:
    title = html.unescape(title)
    title = re.sub(r"\s*[-|]\s*RxDx Clinics\s*$", "", title)
    return re.sub(r"\s+Archives$", "", title).strip()


@dataclass
class Sitting:
    """One doctor at one branch: which days, in which mode."""

    branch: str | None
    clinic_label: str
    in_clinic: list[str]
    teleconsultation: list[str]


@dataclass
class Doctor:
    slug: str
    name: str
    title: str
    departments: list[str]
    qualification: str
    experience_years: str
    languages: list[str]
    consultation_types: list[str]
    sittings: list[Sitting]
    url: str
    overview: str
    needs_verification: bool = False
    _roots: set[str] = field(default_factory=set, repr=False)

    @property
    def offers_teleconsultation(self) -> bool:
        """Many profiles list Teleconsultation as offered without publishing its days."""
        return "Teleconsultation" in self.consultation_types or any(s.teleconsultation for s in self.sittings)

    def available(self, day: str | None, mode: str, branch: str | None) -> list[Sitting]:
        out = []
        for s in self.sittings:
            if branch and s.branch != branch and mode != "teleconsultation":
                continue
            days = {"in_clinic": s.in_clinic, "teleconsultation": s.teleconsultation}.get(
                mode, s.in_clinic + s.teleconsultation
            )
            if day is None or day in days:
                out.append(s)
        return out


class Directory:
    def __init__(self, path: Path = DATA_PATH):
        records = json.loads(path.read_text())["records"]
        self.branches = {
            r["slug"]: clean_title(r["title"]) for r in records if r["kind"] == "branch"
        }
        self.specialities = sorted(clean_title(r["title"]) for r in records if r["kind"] == "specialty")
        self.doctors = {r["slug"]: self._doctor(r) for r in records if r["kind"] == "doctor"}

    def _doctor(self, r: dict) -> Doctor:
        depts = [d.strip() for d in re.split(r",(?![^(]*\))", r.get("department") or "") if d.strip()]
        sittings = [
            Sitting(
                branch=branch_for(s.get("clinic") or ""),
                clinic_label=s.get("clinic") or "",
                in_clinic=expand_days(s.get("inClinic") or []),
                teleconsultation=expand_days(s.get("teleconsultation") or []),
            )
            for s in r.get("schedules") or []
        ]
        suspect = name_disagrees_with_url(r["name"], r["slug"])
        d = Doctor(
            slug=r["slug"],
            name=name_from_slug(r["slug"]) if suspect else r["name"],
            title="" if suspect else r.get("jobTitle") or "",
            departments=depts,
            qualification=r.get("qualification") or "",
            experience_years=r.get("experienceYears") or "",
            languages=r.get("languages") or [],
            consultation_types=r.get("consultationTypes") or [],
            sittings=sittings,
            url=r["url"],
            # The overview on a mislabelled page describes the other doctor too.
            overview="" if suspect else (r.get("overview") or "").strip(),
            needs_verification=suspect,
        )
        d._roots = roots(" ".join(depts) + " " + d.title)
        return d

    @cached_property
    def _branch_roots(self) -> dict[str, set[str]]:
        return {slug: roots(slug.replace("-", " ") + " " + title) - {"rxdx"} for slug, title in self.branches.items()}

    def resolve_branch(self, text: str) -> str | None:
        """Branch slug for a free-text place ("Malleswaram", "RR Nagar", "rxdx-jakkur")."""
        if text in self.branches:
            return text
        slug = branch_for(text)
        if slug:
            return slug
        want = roots(text) - {"rxdx"}
        best = max(self._branch_roots.items(), key=lambda kv: len(want & kv[1]), default=None)
        return best[0] if best and want & best[1] else None

    def matches_speciality(self, doctor: Doctor, speciality: str) -> bool:
        want = roots(speciality)
        return bool(want) and want <= doctor._roots

    def find(
        self,
        speciality: str | None = None,
        branch: str | None = None,
        day: str | None = None,
        mode: str = "any",
        language: str | None = None,
        name: str | None = None,
    ) -> list[tuple[Doctor, list[Sitting]]]:
        out = []
        for d in self.doctors.values():
            if speciality and not self.matches_speciality(d, speciality):
                continue
            if language and not any(language.lower() == l.lower() for l in d.languages):
                continue
            if name and not set(re.findall(r"[a-z]+", name.lower())) - {"dr", "ms", "mr"} <= set(
                re.findall(r"[a-z]+", d.name.lower())
            ):
                continue
            if mode == "teleconsultation" and not d.offers_teleconsultation:
                continue
            # Online with no day asked: offered-but-unpublished days still count.
            filter_mode = "any" if (mode == "teleconsultation" and not day) else mode
            sittings = d.available(day, filter_mode, branch)
            if (branch or day) and not sittings:
                continue
            out.append((d, sittings if (branch or day) else d.sittings))
        # Doctors with published days first: a doctor you can't plan a visit to is the worse answer.
        out.sort(key=lambda t: (not any(s.in_clinic or s.teleconsultation for s in t[1]), t[0].name))
        return out

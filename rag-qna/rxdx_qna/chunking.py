"""Turn the scraped rxdx.in records into retrievable chunks.

The scrape is one JSON file of four record kinds — doctor, specialty, branch, page. Each
kind needs different handling:

- A doctor is one chunk. The profile is short (≤ ~2k chars) and a question about a doctor
  almost always needs the whole thing: who they are *and* where/when they sit.
- Pages are long and mixed, so they are split into overlapping windows of body lines.
- Every non-doctor page carries the same site chrome — enquiry forms, the "TAT Attention!"
  banner, the latest five blog teasers. Left in, that chrome dominates retrieval: any
  question mentioning "appointment" pulls 76 near-identical chunks. Lines that repeat across
  many records are dropped as boilerplate, and the contact details they carried are kept
  once, in a single synthesised `contact` chunk.
"""

from __future__ import annotations

import difflib
import html
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

# A line seen in at least this many records is site chrome, not content.
BOILERPLATE_MIN_RECORDS = 10
PAGE_WINDOW_CHARS = 1200
PAGE_OVERLAP_LINES = 2

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

CONTACT_TEXT = (
    "How to contact RxDx Clinics. For urgent enquiries call +91 901 409 1111. "
    "WhatsApp chat is available between 8 am and 8 pm on +91 90199 61402. "
    "Email info@rxdx.in. Online enquiry forms (doctor appointment, lab and radiology tests, "
    "vaccination, facility services) are answered within 6 hours on a best-effort basis. "
    "Some doctors are available on-call only: fill in the form to receive a callback, or call "
    "901 409 1111, WhatsApp 9019961402 or email info@rxdx.in."
)


@dataclass
class Chunk:
    id: str
    kind: str
    title: str
    url: str
    text: str

    def to_dict(self) -> dict:
        return asdict(self)


def clean_title(title: str) -> str:
    title = html.unescape(title)
    title = re.sub(r"\s*[-|]\s*RxDx Clinics\s*$", "", title)
    title = re.sub(r"\s+Archives$", "", title)
    return title.strip()


def _days(days: list[str]) -> str:
    """Normalise to week order. A few profiles write ranges ("Monday to Saturday")."""
    found: set[str] = set()
    for entry in days:
        span = re.fullmatch(r"\s*(\w+)\s+to\s+(\w+)\s*", entry)
        if span and span[1] in DAYS and span[2] in DAYS:
            found.update(DAYS[DAYS.index(span[1]) : DAYS.index(span[2]) + 1])
        else:
            found.update(d for d in DAYS if d in entry)
    ordered = [d for d in DAYS if d in found]
    return ", ".join(ordered) if ordered else ", ".join(days)


def _letters(s: str) -> str:
    return "".join(re.findall(r"[a-z]", re.sub(r"\b(dr|ms|mr|mrs|pt)\b", "", s.lower())))


def name_from_slug(slug: str) -> str:
    words = slug.split("-")
    honorific = {"dr": "Dr", "ms": "Ms", "mr": "Mr", "mrs": "Mrs"}.get(words[0])
    rest = [w.upper() if len(w) == 1 else w.capitalize() for w in (words[1:] if honorific else words)]
    rest = ["(PT)" if w == "Pt" else w for w in rest]
    return " ".join(([honorific] if honorific else []) + rest)


def name_disagrees_with_url(name: str, slug: str) -> bool:
    """19 scraped profiles carry another consultant's name, job title and overview — the
    scraper took the wrong heading ("Dr Sireesh V" alone sits on 11 pages). The URL slug is
    the reliable identity. Fuzzy, so spelling variants (Rajyalaxmi / Rajya Lakshmi) pass."""
    if difflib.SequenceMatcher(None, _letters(name), _letters(slug.replace("-", " "))).ratio() >= 0.75:
        return False
    # SEO slugs add words ("…-pediatrician-malleshwaram") but still contain the whole name.
    words = {w for w in re.findall(r"[a-z]+", name.lower()) if len(w) > 1} - {"dr", "ms", "mr", "mrs", "pt"}
    return not (words and words <= set(slug.split("-")))


def doctor_chunk(r: dict) -> Chunk:
    if name_disagrees_with_url(r["name"], r["slug"]):
        r = {**r, "name": name_from_slug(r["slug"]), "jobTitle": None, "overview": (
            "Note: this profile on rxdx.in is inconsistent (it shows another consultant's name), "
            "so only the department and schedule are given here. Please confirm with the clinic."
        )}
    lines = [f"{r['name']} — {r.get('jobTitle') or 'Consultant'} at RxDx Clinics."]
    if r.get("department"):
        lines.append(f"Department / speciality: {r['department']}.")
    if r.get("qualification"):
        lines.append(f"Qualifications: {r['qualification']}.")
    if r.get("experienceYears"):
        lines.append(f"Experience: {r['experienceYears']} years.")
    if r.get("languages"):
        lines.append(f"Languages spoken: {', '.join(r['languages'])}.")
    if r.get("consultationTypes"):
        lines.append(f"Consultation types: {', '.join(r['consultationTypes'])}.")
    for s in r.get("schedules") or []:
        parts = [f"Available at {s.get('clinic') or 'RxDx'}"]
        if s.get("inClinic"):
            parts.append(f"in-clinic on {_days(s['inClinic'])}")
        if s.get("teleconsultation"):
            parts.append(f"teleconsultation on {_days(s['teleconsultation'])}")
        if len(parts) == 1:
            parts.append("days not published (call to confirm)")
        lines.append(", ".join(parts) + ".")
    if not r.get("schedules"):
        lines.append("Schedule: not published on the website — call to check availability.")
    if r.get("councilNumber"):
        lines.append(f"Medical council registration: {r['councilNumber']}.")
    if r.get("overview"):
        lines.append(r["overview"].strip())
    return Chunk(
        id=f"doctor:{r['slug']}",
        kind="doctor",
        title=r["name"],
        url=r["url"],
        text="\n".join(lines),
    )


def _windows(lines: list[str]) -> list[list[str]]:
    """Group lines into ~PAGE_WINDOW_CHARS windows, overlapping by a couple of lines so a
    heading is not separated from the paragraph it introduces."""
    out: list[list[str]] = []
    cur: list[str] = []
    size = 0
    for line in lines:
        if cur and size + len(line) > PAGE_WINDOW_CHARS:
            out.append(cur)
            cur = cur[-PAGE_OVERLAP_LINES:]
            size = sum(map(len, cur))
        cur.append(line)
        size += len(line)
    if cur and (not out or cur != out[-1][-len(cur):]):
        out.append(cur)
    return out


def listing_chunk(r: dict, body: list[str]) -> Chunk | None:
    """Branch and speciality archives are, once the chrome is gone, a list of consultants."""
    title = clean_title(r["title"])
    if not body:
        return None
    noun = "branch" if r["kind"] == "branch" else "speciality"
    text = f"Consultants listed under the {title} {noun} at RxDx Clinics: " + "; ".join(body) + "."
    return Chunk(id=f"{r['kind']}:{r['slug']}", kind=r["kind"], title=title, url=r["url"], text=text)


def build_chunks(records: list[dict]) -> list[Chunk]:
    line_freq = Counter(
        line for r in records if r["kind"] != "doctor" for line in set(r.get("body") or [])
    )

    def keep(line: str) -> bool:
        line = line.strip()
        return bool(line) and line_freq[line] < BOILERPLATE_MIN_RECORDS and line != "No Fields Found."

    chunks: list[Chunk] = [
        Chunk(id="contact", kind="contact", title="Contact RxDx Clinics", url="https://rxdx.in/contact-us/", text=CONTACT_TEXT)
    ]
    for r in records:
        if r["kind"] == "doctor":
            chunks.append(doctor_chunk(r))
            continue
        body = [html.unescape(l.strip()) for l in (r.get("body") or []) if keep(l)]
        if r["kind"] in ("branch", "specialty"):
            c = listing_chunk(r, body)
            if c:
                chunks.append(c)
            continue
        title = clean_title(r["title"])
        for i, window in enumerate(_windows(body)):
            chunks.append(
                Chunk(
                    id=f"page:{r['slug']}#{i}",
                    kind="page",
                    title=title,
                    url=r["url"],
                    text=f"{title}\n" + "\n".join(window),
                )
            )
    return chunks


def load_records(path: Path) -> list[dict]:
    return json.loads(path.read_text())["records"]

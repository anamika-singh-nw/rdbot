"""Tools the navigator agent can call, and their executor.

Every fact the agent states about a doctor — name, branch, day — must come back through one
of these functions, so it is exact by construction. The model's job is the judgement around
them: turning "my son keeps getting ear infections" into Paediatric ENT, widening the search
when nothing matches, and explaining the trade-offs.

Schemas are `strict`, so arguments always validate. Strict schemas cannot have optional
properties, so "not specified" is an explicit null.
"""

from __future__ import annotations

import json
import re
from urllib.parse import quote

from .directory import DAYS, Directory, Doctor, Sitting

MAX_RESULTS = 8
WHATSAPP = "919019961402"
PHONE = "+91 901 409 1111"

_nullable = lambda t, **kw: {"type": [t, "null"], **kw}  # noqa: E731

TOOLS = [
    {
        "name": "list_specialities",
        "description": "List the specialities RxDx offers. Call this when unsure which speciality name to search for.",
        "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        "strict": True,
    },
    {
        "name": "list_branches",
        "description": "List RxDx clinic branches (Bengaluru) with how many consultants sit at each.",
        "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        "strict": True,
    },
    {
        "name": "find_doctors",
        "description": (
            "Search the RxDx doctor directory. All filters are optional (pass null) and combine with AND. "
            "Returns at most 8 doctors with the branches and days they are actually available, plus the total "
            "match count. If a search returns nothing, relax one filter at a time (day first, then branch) and "
            "tell the user what you relaxed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "speciality": _nullable("string", description="Speciality, e.g. 'Dermatology', 'Paediatric ENT', 'Orthopaedics'."),
                "branch": _nullable("string", description="Branch or area name, e.g. 'Whitefield', 'Malleswaram'."),
                "day": _nullable("string", enum=[*DAYS, None], description="Day of the week the patient can come."),
                "mode": {"type": "string", "enum": ["in_clinic", "teleconsultation", "any"]},
                "language": _nullable("string", description="Language the doctor should speak, e.g. 'Kannada'."),
                "name": _nullable("string", description="All or part of the doctor's name."),
            },
            "required": ["speciality", "branch", "day", "mode", "language", "name"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "get_doctor",
        "description": "Full profile for one doctor by slug (from find_doctors): qualifications, experience, overview.",
        "input_schema": {
            "type": "object",
            "properties": {"slug": {"type": "string"}},
            "required": ["slug"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "prepare_booking_request",
        "description": (
            "Draft a booking request the patient can send to RxDx on WhatsApp. This does NOT book anything — "
            "the clinic confirms. Only call it once the patient has chosen a doctor, branch, day and mode. "
            "Fails if the doctor is not available at that branch on that day."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string"},
                "branch": _nullable("string", description="Branch; null for teleconsultation."),
                "day": {"type": "string", "enum": DAYS},
                "mode": {"type": "string", "enum": ["in_clinic", "teleconsultation"]},
                "reason": {"type": "string", "description": "One line in the patient's words; no diagnosis."},
            },
            "required": ["slug", "branch", "day", "mode", "reason"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


def review_links(name: str) -> dict[str, str]:
    """Search links for a doctor's public reviews — searches, not ratings.

    No rating is fetched or shown: matching a rating to a doctor by name is unreliable
    (namesakes, initials), and a wrong rating on a doctor misleads patients. The quoted
    name plus "RxDx"/"Bengaluru" narrows the search; the patient judges the results.
    Practo is reached through a site-restricted Google search because its own search URLs
    are not stable.
    """
    bare = re.sub(r"^(Dr|Ms|Mr|Mrs)\.?\s+", "", name).replace("(PT)", "").strip()
    return {
        "google": "https://www.google.com/search?q=" + quote(f'"{bare}" RxDx Bengaluru reviews'),
        "practo": "https://www.google.com/search?q=" + quote(f'site:practo.com "{bare}" Bangalore'),
    }


class ToolError(Exception):
    """Returned to the model as an `is_error` tool result so it can correct course."""


class Toolbox:
    def __init__(self, directory: Directory | None = None):
        self.d = directory or Directory()

    def run(self, name: str, args: dict) -> str:
        fn = getattr(self, f"_{name}", None)
        if fn is None or name not in {t["name"] for t in TOOLS}:
            raise ToolError(f"Unknown tool {name!r}.")
        return json.dumps(fn(**args), ensure_ascii=False)

    # --- formatting -------------------------------------------------------------------

    def _branch_name(self, slug: str | None, fallback: str) -> str:
        return self.d.branches.get(slug, fallback) if slug else fallback

    def _sitting(self, s: Sitting) -> dict:
        return {
            "branch": self._branch_name(s.branch, s.clinic_label),
            "branch_id": s.branch,
            "in_clinic_days": s.in_clinic or "not published — call to check",
            "teleconsultation_days": s.teleconsultation,
        }

    def _summary(self, doc: Doctor, sittings: list[Sitting]) -> dict:
        out = {
            "slug": doc.slug,
            "name": doc.name,
            "title": doc.title or None,
            "departments": doc.departments,
            "languages": doc.languages,
            "availability": [self._sitting(s) for s in sittings],
            "profile_url": doc.url,
            "review_search_links": review_links(doc.name),
        }
        if doc.needs_verification:
            out["warning"] = (
                "This doctor's page on rxdx.in shows another consultant's name; name taken from the page URL. "
                "Tell the patient to confirm with the clinic."
            )
        return out

    # --- tools ------------------------------------------------------------------------

    def _list_specialities(self) -> dict:
        return {"specialities": self.d.specialities}

    def _list_branches(self) -> dict:
        counts = {slug: 0 for slug in self.d.branches}
        for doc in self.d.doctors.values():
            for slug in {s.branch for s in doc.sittings if s.branch}:
                counts[slug] += 1
        return {"branches": [{"id": s, "name": n, "consultants": counts[s]} for s, n in self.d.branches.items()]}

    def _find_doctors(self, speciality, branch, day, mode, language, name) -> dict:
        branch_id = None
        if branch:
            branch_id = self.d.resolve_branch(branch)
            if branch_id is None:
                raise ToolError(
                    f"No RxDx branch matches {branch!r}. Branches: {'; '.join(self.d.branches.values())}."
                )
        results = self.d.find(speciality, branch_id, day, mode, language, name)
        out = {
            "total_matches": len(results),
            "doctors": [self._summary(doc, sittings) for doc, sittings in results[:MAX_RESULTS]],
        }
        if branch_id:
            out["branch_resolved_to"] = self.d.branches[branch_id]
        if speciality and not results and not any(
            self.d.matches_speciality(doc, speciality) for doc in self.d.doctors.values()
        ):
            out["note"] = f"No doctor lists {speciality!r}. Check list_specialities for the exact names."
        return out

    def _get_doctor(self, slug: str) -> dict:
        doc = self.d.doctors.get(slug)
        if doc is None:
            raise ToolError(f"No doctor with slug {slug!r}. Use find_doctors to get slugs.")
        return {
            **self._summary(doc, doc.sittings),
            "qualification": doc.qualification or None,
            "experience_years": doc.experience_years or None,
            "consultation_types": doc.consultation_types,
            "overview": doc.overview or None,
        }

    def _prepare_booking_request(self, slug, branch, day, mode, reason) -> dict:
        doc = self.d.doctors.get(slug)
        if doc is None:
            raise ToolError(f"No doctor with slug {slug!r}.")
        if mode == "in_clinic":
            branch_id = self.d.resolve_branch(branch or "")
            if branch_id is None:
                raise ToolError("An in-clinic request needs a valid branch.")
            if not doc.available(day, "in_clinic", branch_id):
                raise ToolError(
                    f"{doc.name} is not listed in-clinic at {self.d.branches[branch_id]} on {day}. "
                    "Check availability with find_doctors and offer the patient a day that works."
                )
            where = f"in-clinic at {self.d.branches[branch_id]}"
        else:
            if not doc.available(day, "teleconsultation", None):
                raise ToolError(f"{doc.name} has no teleconsultation listed on {day}.")
            where = "by teleconsultation"
        message = (
            f"Hello RxDx, I'd like to request an appointment with {doc.name} {where} on {day}. "
            f"Reason: {reason.strip()}. Please confirm a time. Thank you."
        )
        return {
            "status": "draft — not booked; RxDx confirms the time",
            "message": message,
            "whatsapp_link": f"https://wa.me/{WHATSAPP}?text={quote(message)}",
            "phone": PHONE,
            "profile_url": doc.url,
        }

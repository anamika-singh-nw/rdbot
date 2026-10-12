"""Emergency screen that runs before the model sees the message.

RxDx clinics are outpatient clinics. Someone describing a heart attack or a stroke must be
told to call 108 *first* — not handed a cardiologist's Tuesday slot. This is deterministic
on purpose: the response to "crushing chest pain" should not depend on sampling.

It errs towards firing. A false alarm costs one extra sentence; a miss can cost a life.
Negated mentions ("no chest pain") are skipped so routine follow-ups are not derailed.
"""

from __future__ import annotations

import re

RED_FLAGS: list[tuple[str, str]] = [
    ("chest pain", r"chest (pain|tightness|pressure)|crushing (pain|chest)|heart attack"),
    ("breathing", r"(can'?t|cannot|unable to|struggling to|difficulty|trouble) breath|short(ness)? of breath|gasping|choking"),
    ("stroke signs", r"stroke|face (is )?droop|slurred speech|sudden (weakness|numbness)|can'?t move (my|his|her) (arm|leg)"),
    ("unconscious / seizure", r"unconscious|not waking|passed out|fainted|unresponsive|seizure|convulsion|\bfits?\b"),
    ("severe bleeding", r"(heavy|severe|won'?t stop|uncontrolled) bleeding|bleeding (heavily|a lot)|vomit(ing)? blood|coughing (up )?blood"),
    ("self-harm", r"suicid|kill (my|him|her)self|end (my|his|her) life|self[- ]harm|overdos"),
    ("poisoning", r"poison|swallowed (bleach|chemicals?|pills)"),
    ("severe allergic reaction", r"anaphyla|throat (is )?(closing|swelling)|swollen (tongue|lips) .*breath"),
    ("serious injury", r"head injury|hit (my|his|her) head|broken bone .*(sticking|out)|severe burn|(road|bad|serious) accident"),
    ("infant fever", r"(newborn|infant|\d+ ?(week|day)s? old).*(fever|temperature)"),
]
_NEGATION = re.compile(r"\b(no|not|without|never|denies)\b[^.,;]{0,25}$")

EMERGENCY_REPLY = (
    "This sounds like it may need urgent care. Please call **108** (ambulance) or go to the "
    "nearest hospital emergency department now — RxDx clinics are outpatient clinics and are not "
    "equipped for emergencies."
)
SELF_HARM_REPLY = (
    "I'm really sorry you're going through this. If you are in immediate danger, call **112** or "
    "go to the nearest emergency department. You can talk to someone right now at **Tele-MANAS, "
    "14416** (free, 24×7, in many Indian languages)."
)


def screen(message: str) -> tuple[str, str] | None:
    """Return (category, reply) if the message describes an emergency, else None."""
    text = message.lower()
    for category, pattern in RED_FLAGS:
        for m in re.finditer(pattern, text):
            if _NEGATION.search(text[max(0, m.start() - 40) : m.start()]):
                continue
            return category, SELF_HARM_REPLY if category == "self-harm" else EMERGENCY_REPLY
    return None

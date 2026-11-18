"""The professions an office can be, and which processes each one works with.

An office picks its profession once; the catalog, the new-case dialog, and the words on the
screens follow it ("לקוח" in a law office, "מטופל" in a clinic). A process may serve more than
one profession: Form 101 is paperwork for law offices and accountants alike.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.catalog.dental import DENTAL_KEYS


@dataclass(frozen=True)
class Profession:
    key: str
    label_he: str
    # How the office speaks of the person it serves, and of one file.
    client_he: str
    case_he: str


PROFESSIONS: dict[str, Profession] = {
    "law": Profession("law", "משרד עורכי דין", "לקוח", "תיק"),
    "accounting": Profession("accounting", "משרד רואי חשבון", "לקוח", "תיק"),
    "dental_clinic": Profession("dental_clinic", "מרפאת שיניים", "מטופל", "תיק מטופל"),
}
DEFAULT_PROFESSION = "law"

_PROCESS_PROFESSIONS: dict[str, tuple[str, ...]] = {
    "bl_6101": ("law",),
    "real_estate": ("law",),
    "onboarding": ("law", "accounting"),
    "employee_onboarding": ("law", "accounting"),
    **{key: ("dental_clinic",) for key in DENTAL_KEYS},
}


def profession(key: str | None) -> Profession:
    return PROFESSIONS.get(key or "", PROFESSIONS[DEFAULT_PROFESSION])


def professions_of(process_key: str) -> tuple[str, ...]:
    """Which professions use this process. A process with no entry is open to every office."""
    return _PROCESS_PROFESSIONS.get(process_key, tuple(PROFESSIONS))

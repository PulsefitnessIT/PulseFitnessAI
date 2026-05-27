"""Iter 220s — Unified RIDDOR Decision Engine.

This module owns the *legal classification* logic for whether an
incident is reportable under the UK Reporting of Injuries, Diseases
and Dangerous Occurrences Regulations 2013 (RIDDOR).

The engine is intentionally **conservative**: when the answer to any
qualifying question is ambiguous (``None``) the result is
``potential``, not ``non_riddor``, so a human always gets the call to
review. The engine NEVER auto-submits to HSE — that remains a
deliberate manager-signed-off act.

The wizard mirrors the HSE F2508 decision flow:

1. Was there a fatality arising from a work-related accident?
2. Did the person sustain a "specified injury" (fracture other than
   fingers/thumbs/toes, amputation, permanent loss of sight, crush
   injury to head/torso, serious >10% burn, scalping requiring
   hospital, loss of consciousness from head injury or asphyxia,
   injury from working in enclosed space)?
3. Was a worker incapacitated for **more than 7 consecutive days**
   (excluding the day of the accident, including weekends)?
4. Was a non-worker (member of public / customer / visitor) taken
   directly to hospital from the scene for treatment?
5. Was there a **dangerous occurrence** (machinery collapse, pressure
   system failure, electrical short causing fire, etc.)?
6. Was a reportable **occupational disease** diagnosed (occupational
   dermatitis, hand-arm vibration syndrome, carpal tunnel, occupational
   asthma, severe cramp of the hand or forearm, occupational cancer,
   tendonitis or tenosynovitis, biological-agent exposure)?
7. Was there a **gas-related incident** (gas distribution / fitting
   leading to death, loss of consciousness or hospital treatment)?

Plus two context questions that determine whether RIDDOR is *engaged*
at all:

8. Did the incident arise out of, or in connection with, work?
9. Was the affected person an employee, contractor, or member of the
   public on work premises at the time?

Outputs:

* ``status`` — ``non_riddor`` | ``potential`` | ``confirmed``
* ``reasons`` — list of human-readable strings explaining the
  classification (these go straight into the incident detail page +
  the printed RIDDOR PDF cover sheet)
* ``deadline_days`` — statutory reporting window:
    - Fatality / specified injury / dangerous occurrence / gas → 10 days
    - Over-7-day injury → 15 days (from date of accident, F2508)
    - Occupational disease → 10 days from diagnosis
* ``form`` — HSE form template (``F2508`` for accidents/dangerous,
  ``F2508A`` for diseases, ``F2508G`` for gas)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


WizardAnswer = Optional[bool]  # True / False / None (don't-know)


@dataclass
class RiddorVerdict:
    status: str                # non_riddor | potential | confirmed
    reasons: list[str]
    deadline_days: int | None  # statutory days from incident
    form: str | None           # F2508 / F2508A / F2508G
    qualifying_questions: list[str]  # Q identifiers that triggered

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "reasons": list(self.reasons),
            "deadline_days": self.deadline_days,
            "form": self.form,
            "qualifying_questions": list(self.qualifying_questions),
        }


def assess(answers: dict) -> RiddorVerdict:
    """Run the RIDDOR decision wizard.

    ``answers`` is a dict mapping wizard question keys to a Python
    bool (or ``None`` for don't-know). Unknown keys are ignored;
    missing keys are treated as ``False`` (the assessor implicitly
    answered "no").

    Recognised keys (all booleans / None):

    * ``fatality``
    * ``specified_injury``
    * ``over_7_day_incapacitation``
    * ``non_worker_to_hospital``
    * ``dangerous_occurrence``
    * ``occupational_disease``
    * ``gas_incident``
    * ``arose_from_work`` (context)
    * ``person_at_work`` (context)
    """
    if not isinstance(answers, dict):
        answers = {}

    # Context gates — without "arose from work" RIDDOR doesn't engage
    # at all (e.g. a member tripping over their own shoelaces in the
    # changing room isn't reportable). When the context flag is
    # explicitly False, we always return non_riddor, no matter what
    # else they ticked.
    if answers.get("arose_from_work") is False:
        return RiddorVerdict(
            status="non_riddor",
            reasons=[
                "Incident did not arise out of, or in connection with, work — "
                "RIDDOR does not apply (Regulation 4)."
            ],
            deadline_days=None,
            form=None,
            qualifying_questions=[],
        )

    triggers: list[tuple[str, str, int, str]] = []  # (q_id, reason, deadline_days, form)
    unknown: list[str] = []

    def _tick(key: str, reason: str, deadline: int, form: str) -> None:
        # Treat *missing* keys as implicit "no" (assessor hasn't ticked
        # it). An explicit ``None`` in the dict means "don't know" and
        # surfaces as a potential RIDDOR for human review.
        if key not in answers:
            return
        v = answers[key]
        if v is True:
            triggers.append((key, reason, deadline, form))
        elif v is None:
            unknown.append(key)

    _tick(
        "fatality",
        "Death of a person from a work-related accident "
        "(Reg 6) — report immediately and within 10 days.",
        10, "F2508",
    )
    _tick(
        "specified_injury",
        "Specified injury to a worker (fracture other than digits, "
        "amputation, sight loss, crush, serious burn, scalping, loss "
        "of consciousness, enclosed-space injury) (Reg 4) — F2508 within 10 days.",
        10, "F2508",
    )
    _tick(
        "over_7_day_incapacitation",
        "Worker incapacitated for more than 7 consecutive days "
        "(excluding day of accident) (Reg 4) — F2508 within 15 days.",
        15, "F2508",
    )
    _tick(
        "non_worker_to_hospital",
        "Non-worker (member of the public / customer / visitor) "
        "taken from the scene to hospital for treatment (Reg 5) — "
        "F2508 within 10 days.",
        10, "F2508",
    )
    _tick(
        "dangerous_occurrence",
        "Dangerous occurrence as listed in Schedule 2 (machinery "
        "collapse, pressure system failure, electrical short causing "
        "fire/explosion, etc.) (Reg 7) — F2508 within 10 days.",
        10, "F2508",
    )
    _tick(
        "occupational_disease",
        "Reportable occupational disease diagnosed by a doctor "
        "(occupational dermatitis, HAVS, carpal tunnel, asthma, "
        "tendonitis, occupational cancer, biological exposure) "
        "(Reg 8/9) — F2508A within 10 days of diagnosis.",
        10, "F2508A",
    )
    _tick(
        "gas_incident",
        "Gas distribution / fitting incident causing death, loss "
        "of consciousness or hospital treatment (Reg 11) — "
        "F2508G within 14 days.",
        14, "F2508G",
    )

    if triggers:
        # Confirmed RIDDOR — take the tightest deadline + the
        # appropriate form. F2508 is the most common; only flip to
        # F2508A/G if NONE of the F2508 triggers fired (i.e. this is
        # purely a disease/gas incident).
        deadline = min(t[2] for t in triggers)
        forms = {t[3] for t in triggers}
        form = "F2508" if "F2508" in forms else next(iter(forms))
        return RiddorVerdict(
            status="confirmed",
            reasons=[t[1] for t in triggers],
            deadline_days=deadline,
            form=form,
            qualifying_questions=[t[0] for t in triggers],
        )
    if unknown:
        # No outright yeses but at least one don't-know → escalate
        # to "potential" so a human reviews.
        readable = ", ".join(_humanise(k) for k in unknown)
        return RiddorVerdict(
            status="potential",
            reasons=[
                f"At least one RIDDOR qualifying question is unresolved "
                f"({readable}). Escalate to the H&S lead for review before "
                f"the 10-day statutory window closes."
            ],
            deadline_days=10,
            form="F2508",
            qualifying_questions=unknown,
        )
    return RiddorVerdict(
        status="non_riddor",
        reasons=["No RIDDOR qualifying triggers identified."],
        deadline_days=None,
        form=None,
        qualifying_questions=[],
    )


_HUMAN = {
    "fatality": "fatality",
    "specified_injury": "specified injury",
    "over_7_day_incapacitation": "over-7-day incapacitation",
    "non_worker_to_hospital": "non-worker hospital treatment",
    "dangerous_occurrence": "dangerous occurrence",
    "occupational_disease": "occupational disease",
    "gas_incident": "gas incident",
    "arose_from_work": "work-relatedness",
    "person_at_work": "person at work",
}


def _humanise(key: str) -> str:
    return _HUMAN.get(key, key.replace("_", " "))


# Public list of wizard questions surfaced to the frontend so the
# Riddor wizard can stay declarative. Each row carries a stable key,
# a human-readable prompt, and tighter help-text used for the
# tooltip / "What counts?" disclosure.
WIZARD_QUESTIONS: list[dict] = [
    {
        "key": "arose_from_work",
        "prompt": "Did the incident arise out of or in connection with work?",
        "help": (
            "RIDDOR only applies to incidents linked to a work activity. "
            "A member slipping in the changing room because of wet flooring "
            "(work-related) counts; a member fainting from a personal "
            "medical condition typically does not."
        ),
        "kind": "context",
    },
    {
        "key": "person_at_work",
        "prompt": "Was the affected person at work (employee, contractor, or on work premises)?",
        "help": (
            "Members and visitors on your premises count as non-workers; "
            "their incidents are reportable only if they're taken to "
            "hospital for treatment."
        ),
        "kind": "context",
    },
    {
        "key": "fatality",
        "prompt": "Was there a fatality?",
        "help": "Any death of a person arising from a work-related accident.",
        "kind": "qualifying",
    },
    {
        "key": "specified_injury",
        "prompt": "Did the person suffer a specified injury?",
        "help": (
            "Specified injuries include fractures (other than fingers, thumbs, "
            "toes), amputations, permanent loss of sight, crush injuries to the "
            "head/torso, serious burns covering >10% of the body or to the "
            "eyes/respiratory system/vital organs, scalping requiring hospital, "
            "loss of consciousness caused by head injury or asphyxia, and "
            "injuries from working in enclosed spaces."
        ),
        "kind": "qualifying",
    },
    {
        "key": "over_7_day_incapacitation",
        "prompt": "Was a worker incapacitated for more than 7 consecutive days?",
        "help": (
            "Count consecutive days (including weekends and rest days) the "
            "person could not perform their normal duties. Do NOT count the "
            "day of the accident itself. If unsure, mark as 'don't know' — "
            "the system will follow up at day 8."
        ),
        "kind": "qualifying",
    },
    {
        "key": "non_worker_to_hospital",
        "prompt": "Was a non-worker (member of the public) taken directly to hospital for treatment?",
        "help": (
            "If a member of the public was injured at your premises and "
            "transported from the scene to hospital for treatment of that "
            "injury, the incident is reportable — regardless of whether "
            "they were ultimately admitted."
        ),
        "kind": "qualifying",
    },
    {
        "key": "dangerous_occurrence",
        "prompt": "Did a dangerous occurrence happen, even if no one was hurt?",
        "help": (
            "Specified events from RIDDOR Schedule 2: collapse / overturning "
            "of machinery, pressure system failure, electrical short circuit "
            "or overload causing fire or explosion, biological agent release, "
            "etc. The full Schedule 2 list is linked from the wizard footer."
        ),
        "kind": "qualifying",
    },
    {
        "key": "occupational_disease",
        "prompt": "Has a doctor diagnosed a reportable occupational disease?",
        "help": (
            "Occupational dermatitis, hand-arm vibration syndrome, carpal "
            "tunnel syndrome, occupational asthma, occupational cancer, "
            "severe cramp of hand or forearm, tendonitis / tenosynovitis, "
            "or any disease caused by biological-agent exposure."
        ),
        "kind": "qualifying",
    },
    {
        "key": "gas_incident",
        "prompt": "Was there a gas-related incident?",
        "help": (
            "Gas distribution or gas fitting incidents that caused death, "
            "loss of consciousness, or hospital treatment. Reportable under "
            "Regulation 11 within 14 days (F2508G)."
        ),
        "kind": "qualifying",
    },
]

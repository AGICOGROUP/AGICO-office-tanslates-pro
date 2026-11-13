"""Shared, structural checks for decisions that leave picture text unchanged.

These checks cannot establish whether a picture was classified honestly; visual
review remains required. A free-form explanation never grants a new exemption.
"""

RETAIN_CODES = frozenset({
    "photo_exempt_site", "photo_exempt_building", "photo_exempt_equipment",
    "photo_exempt_people", "photo_exempt_crowd", "photo_exempt_scene",
    "already_target", "no_text", "logo_only",
})
UNREADABLE_CODE = "unreadable_text"


def retention_error(record, decision):
    if decision not in {"skip_target", "skip_unclear", "retain", "reviewed"}:
        return None
    reason = record.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return "retained image needs a non-empty reason identifying the actual image or labels"
    if decision == "skip_unclear":
        allowed = {UNREADABLE_CODE}
    elif decision in {"retain", "reviewed"}:
        allowed = RETAIN_CODES | {UNREADABLE_CODE}
    else:
        allowed = RETAIN_CODES
    code = record.get("reason_code")
    if not isinstance(code, str) or code not in allowed:
        return "invalid image retention reason_code; use one of " + ", ".join(sorted(allowed))
    return None

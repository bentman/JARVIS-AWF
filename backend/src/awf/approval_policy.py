"""Shared approval policy decisions."""

HIGH_RISK_CLASSES = ("R2", "R3")


def decide_voice_acknowledgement(risk_class: str, *, voice_confirmed: bool) -> dict:
    """Return whether voice-only acknowledgement may decide this risk class."""
    if risk_class in HIGH_RISK_CLASSES:
        return {"decided": False, "requires_on_screen_confirmation": True, "channel": "voice"}
    return {
        "decided": bool(voice_confirmed),
        "requires_on_screen_confirmation": False,
        "channel": "voice",
    }

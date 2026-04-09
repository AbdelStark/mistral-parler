"""Speaker attribution subsystem."""

from .attributor import SpeakerAttributor
from .resolver import SpeakerResolver, format_human_name, normalize_speaker_token

__all__ = [
    "SpeakerAttributor",
    "SpeakerResolver",
    "format_human_name",
    "normalize_speaker_token",
]

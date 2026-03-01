from __future__ import annotations

from exptools2.audio.engines.portaudio import PortAudioDevice
from exptools2.audio.engines.psychtoolbox import (
    PsychtoolboxAudioDevice,
    psychtoolbox_available,
)


def create_audio_device(engine: str = "auto"):
    engine = engine.lower()
    if engine == "psychtoolbox":
        return PsychtoolboxAudioDevice()
    if engine == "portaudio":
        return PortAudioDevice()

    # auto: prefer psychtoolbox, then PortAudio.
    if psychtoolbox_available():
        return PsychtoolboxAudioDevice()
    return PortAudioDevice()

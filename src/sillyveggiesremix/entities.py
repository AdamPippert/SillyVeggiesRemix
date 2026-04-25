import math
from array import array

import pygame


class AudioBank:
    def __init__(self):
        self.enabled = False
        self.sounds = {}

    def init(self):
        try:
            pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
            self.sounds["lasso_fire"] = self._tone(540, 45, 0.25)
            self.sounds["lasso_latch"] = self._tone(760, 65, 0.2)
            self.sounds["capture"] = self._tone(980, 95, 0.23)
            self.sounds["player_hit"] = self._tone(170, 110, 0.3)
            self.sounds["spit"] = self._tone(260, 60, 0.2)
            self.sounds["pickup"] = self._tone(840, 70, 0.2)
            self.enabled = True
        except pygame.error:
            self.enabled = False

    def _tone(self, freq_hz: float, dur_ms: int, volume: float):
        sample_rate = 22050
        samples = int(sample_rate * dur_ms / 1000)
        buf = array("h")
        for i in range(samples):
            t = i / sample_rate
            env = 1.0 - (i / samples)
            val = int(32767 * volume * env * math.sin(2 * math.pi * freq_hz * t))
            buf.append(val)
        return pygame.mixer.Sound(buffer=buf.tobytes())

    def play(self, key: str):
        if self.enabled and key in self.sounds:
            self.sounds[key].play()

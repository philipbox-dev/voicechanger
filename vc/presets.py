"""Parameter schema + preset library."""

# name -> (default, min, max, kind)  kind: f=float, i=int, b=bool, c=choice
PARAMS = {
    "in_gain_db":    (0.0,   -24.0, 24.0, "f"),
    "gate_db":       (-60.0, -80.0,  0.0, "f"),
    "comp":          (True,  0, 1, "b"),

    "pitch":         (0.0,   -24.0, 24.0, "f"),   # semitones
    "formant":       (1.0,    0.50, 2.00, "f"),
    "autotune":      (False, 0, 1, "b"),
    "scale":         ("minor", 0, 0, "c"),
    "root":          (0, 0, 11, "i"),

    "robot":         (False, 0, 1, "b"),
    "whisper":       (False, 0, 1, "b"),
    "denoise":       (False, 0, 1, "b"),

    "hp_hz":         (70.0,   20.0, 2000.0, "f"),
    "lp_hz":         (16000.0, 500.0, 20000.0, "f"),
    "peak_hz":       (1500.0, 200.0, 8000.0, "f"),
    "peak_db":       (0.0,   -18.0, 18.0, "f"),

    "dist_kind":     ("tanh", 0, 0, "c"),
    "dist_drive":    (1.0,    1.0, 30.0, "f"),
    "dist_mix":      (0.0,    0.0,  1.0, "f"),

    "crush_bits":    (16.0,   2.0, 16.0, "f"),
    "crush_ds":      (1,      1,  32,   "i"),
    "crush_mix":     (0.0,    0.0, 1.0,  "f"),

    "ring_freq":     (60.0,   5.0, 2000.0, "f"),
    "ring_mix":      (0.0,    0.0, 1.0, "f"),

    "wah_mix":       (0.0,    0.0, 1.0, "f"),

    "phaser_rate":   (0.4,    0.05, 8.0, "f"),
    "phaser_mix":    (0.0,    0.0, 1.0, "f"),

    "mod_mode":      ("off", 0, 0, "c"),   # off|chorus|flanger|vibrato
    "mod_rate":      (0.8,    0.05, 12.0, "f"),
    "mod_depth":     (3.0,    0.1, 20.0, "f"),
    "mod_mix":       (0.5,    0.0, 1.0, "f"),

    "trem_rate":     (5.0,    0.2, 20.0, "f"),
    "trem_depth":    (0.0,    0.0, 1.0, "f"),

    "echo_time":     (320.0,  30.0, 1500.0, "f"),
    "echo_fb":       (0.35,   0.0, 0.92, "f"),
    "echo_mix":      (0.0,    0.0, 1.0, "f"),

    "rev_room":      (0.72,   0.1, 0.98, "f"),
    "rev_damp":      (0.35,   0.0, 0.95, "f"),
    "rev_mix":       (0.0,    0.0, 1.0, "f"),

    "out_gain_db":   (0.0,   -24.0, 24.0, "f"),
}

CHOICES = {
    "scale": ["chromatic", "major", "minor", "pentatonic"],
    "dist_kind": ["tanh", "hard", "fold", "fuzz"],
    "mod_mode": ["off", "chorus", "flanger", "vibrato"],
}


def defaults():
    return {k: v[0] for k, v in PARAMS.items()}


# --------------------------------------------------------------------------
# preset library: each entry only lists what differs from the defaults
# --------------------------------------------------------------------------
PRESETS = {
    # ---- clean / subtle -------------------------------------------------
    "Clean (bypass)": {},
    "Radio Voice": dict(hp_hz=180, lp_hz=6500, peak_hz=2400, peak_db=6,
                        comp=True, dist_kind="tanh", dist_drive=2.2, dist_mix=0.25,
                        out_gain_db=2),
    "Podcast Warm": dict(hp_hz=90, peak_hz=200, peak_db=4, comp=True,
                         formant=0.97, out_gain_db=3),
    "Studio Wide": dict(mod_mode="chorus", mod_rate=0.35, mod_depth=2.0,
                        mod_mix=0.25, rev_mix=0.14, rev_room=0.6),

    # ---- gender / age ---------------------------------------------------
    "Female": dict(pitch=4.5, formant=1.18, hp_hz=110),
    "Male": dict(pitch=-4.5, formant=0.84, hp_hz=60),
    "Deep Male": dict(pitch=-7, formant=0.78, peak_hz=250, peak_db=4),
    "Little Girl": dict(pitch=7, formant=1.35, hp_hz=140, peak_hz=3000, peak_db=3),
    "Small Child": dict(pitch=9, formant=1.45, hp_hz=160),
    "Old Man": dict(pitch=-2.5, formant=0.9, mod_mode="vibrato", mod_rate=5.5,
                    mod_depth=1.2, mod_mix=1.0, dist_drive=1.6, dist_mix=0.18),
    "Grandma": dict(pitch=3.5, formant=1.12, mod_mode="vibrato", mod_rate=6.0,
                    mod_depth=1.0, mod_mix=1.0),

    # ---- cartoon --------------------------------------------------------
    "Chipmunk": dict(pitch=11, formant=1.5, hp_hz=180),
    "Helium": dict(pitch=6, formant=1.7),
    "Squirrel": dict(pitch=13, formant=1.6, trem_rate=7, trem_depth=0.25),
    "Duck": dict(pitch=5, formant=1.4, ring_freq=95, ring_mix=0.35,
                 dist_kind="fold", dist_drive=3.0, dist_mix=0.35, hp_hz=200),
    "Cartoon Mouse": dict(pitch=14, formant=1.55, echo_time=90, echo_mix=0.2),

    # ---- monsters -------------------------------------------------------
    "Monster": dict(pitch=-9, formant=0.62, dist_kind="tanh", dist_drive=4.0,
                    dist_mix=0.4, rev_mix=0.2, rev_room=0.8),
    "Demon": dict(pitch=-12, formant=0.6, dist_kind="fuzz", dist_drive=6.0,
                  dist_mix=0.5, rev_mix=0.3, rev_room=0.88, echo_mix=0.15,
                  echo_time=140, lp_hz=7000),
    "Giant": dict(pitch=-10, formant=0.7, rev_room=0.92, rev_mix=0.3,
                  echo_time=260, echo_fb=0.3, echo_mix=0.2, lp_hz=6000),
    "Troll": dict(pitch=-6, formant=0.72, dist_drive=3.2, dist_mix=0.35,
                  crush_bits=9, crush_mix=0.2),
    "Ghost": dict(pitch=-3, whisper=True, rev_room=0.95, rev_mix=0.45,
                  echo_time=420, echo_fb=0.5, echo_mix=0.3, mod_mode="vibrato",
                  mod_rate=0.6, mod_depth=6, mod_mix=1.0),
    "Zombie": dict(pitch=-5, formant=0.75, mod_mode="vibrato", mod_rate=3.2,
                   mod_depth=5, mod_mix=1.0, dist_drive=2.5, dist_mix=0.3,
                   lp_hz=4500),

    # ---- robots / sci-fi ------------------------------------------------
    "Robot": dict(robot=True, formant=0.95, hp_hz=120, lp_hz=8000, out_gain_db=6),
    "Hard Robot": dict(robot=True, ring_freq=48, ring_mix=0.4, crush_bits=7,
                       crush_mix=0.4, dist_drive=2.5, dist_mix=0.3, out_gain_db=5),
    "Cyborg": dict(pitch=-2, robot=True, ring_freq=110, ring_mix=0.25,
                   phaser_mix=0.35, rev_mix=0.15, out_gain_db=8),
    "Dalek": dict(ring_freq=32, ring_mix=0.75, dist_kind="hard", dist_drive=4.0,
                  dist_mix=0.5, hp_hz=300, lp_hz=5000, out_gain_db=3),
    "Alien": dict(pitch=4, formant=0.7, ring_freq=210, ring_mix=0.4,
                  phaser_mix=0.5, phaser_rate=1.2, rev_mix=0.25),
    "Space Radio": dict(hp_hz=350, lp_hz=3400, dist_drive=3.5, dist_mix=0.4,
                        crush_bits=8, crush_mix=0.3, ring_freq=1200, ring_mix=0.08,
                        out_gain_db=4),
    "Vader": dict(pitch=-6, formant=0.72, lp_hz=5200, hp_hz=90,
                  dist_drive=2.0, dist_mix=0.25, rev_room=0.75, rev_mix=0.22,
                  peak_hz=400, peak_db=5),
    "AI Assistant": dict(pitch=1, formant=1.05, autotune=True, scale="major",
                         mod_mode="chorus", mod_rate=0.3, mod_depth=1.5,
                         mod_mix=0.3, rev_mix=0.12),

    # ---- spaces ---------------------------------------------------------
    "Cave": dict(rev_room=0.95, rev_damp=0.5, rev_mix=0.5, echo_time=380,
                 echo_fb=0.45, echo_mix=0.3, lp_hz=6000),
    "Stadium": dict(rev_room=0.9, rev_mix=0.4, echo_time=520, echo_fb=0.35,
                    echo_mix=0.35, peak_hz=1800, peak_db=4),
    "Hall": dict(rev_room=0.85, rev_damp=0.3, rev_mix=0.32),
    "Telephone": dict(hp_hz=380, lp_hz=3200, comp=True, dist_drive=1.8,
                      dist_mix=0.2, out_gain_db=4),
    "Megaphone": dict(hp_hz=500, lp_hz=3800, dist_kind="hard", dist_drive=6.0,
                      dist_mix=0.6, peak_hz=1800, peak_db=8, out_gain_db=2),
    "Underwater": dict(lp_hz=900, mod_mode="vibrato", mod_rate=1.4, mod_depth=9,
                       mod_mix=1.0, rev_mix=0.3, rev_room=0.8),
    "Walkie Talkie": dict(hp_hz=420, lp_hz=2900, dist_kind="hard", dist_drive=5,
                          dist_mix=0.5, crush_bits=9, crush_mix=0.35,
                          out_gain_db=4),

    # ---- musical --------------------------------------------------------
    "Autotune Hard": dict(autotune=True, scale="minor", root=0,
                          mod_mode="chorus", mod_rate=0.4, mod_mix=0.2),
    "T-Pain": dict(autotune=True, scale="pentatonic", formant=1.05,
                   mod_mode="chorus", mod_rate=0.5, mod_depth=2.5, mod_mix=0.3,
                   rev_mix=0.18, comp=True),
    "Choir Octave": dict(pitch=-12, mod_mode="chorus", mod_rate=0.25,
                         mod_depth=4, mod_mix=0.45, rev_mix=0.3, rev_room=0.85, out_gain_db=5),
    "Flanger Jet": dict(mod_mode="flanger", mod_rate=0.25, mod_depth=4.0,
                        mod_mix=0.7),
    "Phaser Sweep": dict(phaser_mix=0.8, phaser_rate=0.35),
    "Wah Funk": dict(wah_mix=0.85, out_gain_db=6),
    "Tremolo": dict(trem_rate=6.0, trem_depth=0.7),
    "Lo-Fi 8bit": dict(crush_bits=6, crush_ds=6, crush_mix=0.9, lp_hz=5000,
                       out_gain_db=3),
    "Fuzz Scream": dict(dist_kind="fuzz", dist_drive=12, dist_mix=0.8,
                        peak_hz=2200, peak_db=5, lp_hz=7000),

    # ---- fun ------------------------------------------------------------
    "Whisper": dict(whisper=True, hp_hz=200, out_gain_db=6),
    "Drunk": dict(mod_mode="vibrato", mod_rate=1.1, mod_depth=12, mod_mix=1.0,
                  pitch=-1.5, formant=0.92),
    "Slow Motion": dict(pitch=-4, formant=0.8, mod_mode="vibrato", mod_rate=0.4,
                        mod_depth=8, mod_mix=1.0, lp_hz=5000),
    "Anonymous TV": dict(pitch=-3.5, formant=0.85, ring_freq=42, ring_mix=0.3,
                         dist_drive=2.0, dist_mix=0.25, hp_hz=150, lp_hz=6500),
    "Stadium Announcer": dict(pitch=-2, comp=True, peak_hz=900, peak_db=5,
                              dist_drive=2.0, dist_mix=0.2, echo_time=280,
                              echo_fb=0.3, echo_mix=0.25, rev_mix=0.25,
                              out_gain_db=4),
}

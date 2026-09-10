"""Realtime audio engine: input -> effect chain -> output."""

import threading
import time
import numpy as np
import sounddevice as sd

from . import dsp
from .presets import defaults


class Chain:
    """The full effect chain. Parameters are read fresh on every block."""

    def __init__(self, sr):
        self.sr = sr
        self.p = defaults()
        self.lock = threading.Lock()

        self.gate = dsp.NoiseGate(sr)
        self.comp = dsp.Compressor(sr)
        self.pitch = dsp.PitchShifter(sr)
        self.spectral = dsp.Spectral(sr)
        self.hp = dsp.Biquad(sr)
        self.lp = dsp.Biquad(sr)
        self.peak = dsp.Biquad(sr)
        self.dist = dsp.Distortion()
        self.crush = dsp.BitCrusher(sr)
        self.ring = dsp.RingMod(sr)
        self.wah = dsp.AutoWah(sr)
        self.phaser = dsp.Phaser(sr)
        self.mod = dsp.ModDelay(sr)
        self.trem = dsp.Tremolo(sr)
        self.echo = dsp.Echo(sr)
        self.reverb = dsp.Reverb(sr)
        self.tracker = dsp.PitchTracker(sr)

        self.bypass = False
        self.muted = False
        self.in_level = 0.0
        self.out_level = 0.0
        self._at_ratio = 1.0

    # -- parameter access ---------------------------------------------------
    def set(self, key, value):
        with self.lock:
            self.p[key] = value

    def load(self, preset_params):
        with self.lock:
            self.p = defaults()
            self.p.update(preset_params)

    def snapshot(self):
        with self.lock:
            return dict(self.p)

    def reset(self):
        for m in (self.pitch, self.spectral, self.hp, self.lp, self.peak,
                  self.wah, self.phaser, self.mod, self.echo, self.reverb):
            m.reset()

    # -- processing ---------------------------------------------------------
    def process(self, x):
        p = self.snapshot()
        self.in_level = float(np.sqrt(np.mean(x * x) + 1e-12))
        if self.muted:
            return np.zeros_like(x)
        if self.bypass:
            self.out_level = self.in_level
            return x

        y = x * dsp.db2lin(p["in_gain_db"])

        self.gate.threshold_db = p["gate_db"]
        if p["gate_db"] > -79.0:
            y = self.gate.process(y)
        if p["comp"]:
            y = self.comp.process(y)

        # ---- pitch (with optional autotune) --------------------------------
        ratio = 2.0 ** (p["pitch"] / 12.0)
        if p["autotune"]:
            self.tracker.push(y)
            f0 = self.tracker.estimate()
            if f0 > 0:
                target = dsp.snap_ratio(f0, int(p["root"]), p["scale"])
                self._at_ratio += (target - self._at_ratio) * 0.5
            else:
                self._at_ratio += (1.0 - self._at_ratio) * 0.2
            ratio *= self._at_ratio
        if abs(ratio - 1.0) > 1e-4:
            y = self.pitch.process(y, ratio)

        # ---- spectral (formant / robot / whisper / denoise) -----------------
        sp = self.spectral
        sp.formant = p["formant"]
        sp.robot = bool(p["robot"])
        sp.whisper = bool(p["whisper"])
        sp.spectral_gate_db = -55.0 if p["denoise"] else None
        if sp.active:
            y = sp.process(y)

        # ---- tone -----------------------------------------------------------
        if p["hp_hz"] > 25:
            self.hp.design("hp", p["hp_hz"], 0.707)
            y = self.hp.process(y)
        if p["lp_hz"] < 19000:
            self.lp.design("lp", p["lp_hz"], 0.707)
            y = self.lp.process(y)
        if abs(p["peak_db"]) > 0.2:
            self.peak.design("peak", p["peak_hz"], 1.0, p["peak_db"])
            y = self.peak.process(y)

        # ---- non-linear ------------------------------------------------------
        if p["dist_mix"] > 0.001:
            self.dist.kind = p["dist_kind"]
            self.dist.drive = p["dist_drive"]
            self.dist.mix = p["dist_mix"]
            y = self.dist.process(y)
        if p["crush_mix"] > 0.001:
            self.crush.bits = p["crush_bits"]
            self.crush.downsample = int(p["crush_ds"])
            self.crush.mix = p["crush_mix"]
            y = self.crush.process(y)
        if p["ring_mix"] > 0.001:
            self.ring.freq = p["ring_freq"]
            self.ring.mix = p["ring_mix"]
            y = self.ring.process(y)
        if p["wah_mix"] > 0.001:
            self.wah.mix = p["wah_mix"]
            y = self.wah.process(y)

        # ---- modulation ------------------------------------------------------
        if p["phaser_mix"] > 0.001:
            self.phaser.mix = p["phaser_mix"]
            self.phaser.rate = p["phaser_rate"]
            y = self.phaser.process(y)
        mode = p["mod_mode"]
        if mode != "off":
            m = self.mod
            m.rate = p["mod_rate"]
            m.depth_ms = p["mod_depth"]
            m.mix = p["mod_mix"]
            if mode == "chorus":
                m.base_ms, m.feedback, m.voices = 18.0, 0.0, 3
            elif mode == "flanger":
                m.base_ms, m.feedback, m.voices = 4.0, 0.65, 1
            else:  # vibrato
                m.base_ms, m.feedback, m.voices, m.mix = 8.0, 0.0, 1, 1.0
            y = m.process(y)
        if p["trem_depth"] > 0.001:
            self.trem.rate = p["trem_rate"]
            self.trem.depth = p["trem_depth"]
            y = self.trem.process(y)

        # ---- space -----------------------------------------------------------
        if p["echo_mix"] > 0.001:
            self.echo.time_ms = p["echo_time"]
            self.echo.feedback = p["echo_fb"]
            self.echo.mix = p["echo_mix"]
            y = self.echo.process(y)
        if p["rev_mix"] > 0.001:
            self.reverb.room = p["rev_room"]
            self.reverb.damp = p["rev_damp"]
            self.reverb.mix = p["rev_mix"]
            y = self.reverb.process(y)

        y = y * dsp.db2lin(p["out_gain_db"])
        np.tanh(y * 0.9, out=y)          # soft limiter, no hard clipping
        self.out_level = float(np.sqrt(np.mean(y * y) + 1e-12))
        return y.astype(np.float32)


class Engine:
    def __init__(self, samplerate=48000, blocksize=256):
        self.sr = samplerate
        self.blocksize = blocksize
        self.chain = Chain(samplerate)
        self.stream = None
        self.input_device = None
        self.output_device = None
        self.xruns = 0
        self.cpu = 0.0
        self.error = None

    # -- devices -------------------------------------------------------------
    @staticmethod
    def devices():
        ins, outs = [], []
        for i, d in enumerate(sd.query_devices()):
            label = f"{i}: {d['name']}"
            if d["max_input_channels"] > 0:
                ins.append((i, label))
            if d["max_output_channels"] > 0:
                outs.append((i, label))
        return ins, outs

    @property
    def running(self):
        return self.stream is not None and self.stream.active

    def latency_ms(self):
        base = self.blocksize * 2 / self.sr * 1000.0
        if self.chain.spectral.active:
            base += self.chain.spectral.win / self.sr * 1000.0
        if self.stream is not None:
            try:
                base += sum(self.stream.latency) * 1000.0
            except Exception:
                pass
        return base

    # -- stream --------------------------------------------------------------
    def _callback(self, indata, outdata, frames, t, status):
        if status:
            self.xruns += 1
        t0 = time.perf_counter()
        try:
            x = indata[:, 0].astype(np.float32, copy=False)
            y = self.chain.process(x)
            if y.size != frames:            # safety, should not happen
                z = np.zeros(frames, dtype=np.float32)
                z[:min(frames, y.size)] = y[:frames]
                y = z
            outdata[:, 0] = y
            if outdata.shape[1] > 1:
                outdata[:, 1:] = y[:, None]
        except Exception as exc:            # never kill the audio thread
            self.error = repr(exc)
            outdata[:] = 0.0
        dt = time.perf_counter() - t0
        budget = frames / self.sr
        self.cpu = 0.9 * self.cpu + 0.1 * (dt / budget * 100.0)

    def start(self, input_device=None, output_device=None):
        self.stop()
        self.input_device = input_device if input_device is not None else self.input_device
        self.output_device = output_device if output_device is not None else self.output_device
        self.chain.reset()
        self.error = None
        self.xruns = 0
        out_ch = 1
        if self.output_device is not None:
            try:
                out_ch = min(2, sd.query_devices(self.output_device)["max_output_channels"])
            except Exception:
                out_ch = 1
        self.stream = sd.Stream(
            samplerate=self.sr,
            blocksize=self.blocksize,
            dtype="float32",
            channels=(1, max(out_ch, 1)),
            device=(self.input_device, self.output_device),
            latency="low",
            callback=self._callback,
        )
        self.stream.start()

    def stop(self):
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

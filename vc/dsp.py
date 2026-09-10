"""Realtime DSP building blocks. Everything is mono float32, block based.

Design rules:
  * every processor is sample-exact: N samples in -> N samples out
  * delay-line feedback loops use delays >= max blocksize, so a whole block
    can be computed vectorised without a per-sample python loop
  * parameters may change at any time from the GUI thread (plain attributes)
"""

import numpy as np
from scipy.signal import lfilter

TWO_PI = 2.0 * np.pi


def db2lin(db):
    return float(10.0 ** (db / 20.0))


def clip(x, lo, hi):
    return lo if x < lo else (hi if x > hi else x)


# --------------------------------------------------------------------------
# biquad filters (transposed direct form II, streaming)
# --------------------------------------------------------------------------
class Biquad:
    def __init__(self, sr):
        self.sr = sr
        self.b = np.array([1.0, 0.0, 0.0])
        self.a = np.array([0.0, 0.0])  # a1, a2 (a0 normalised to 1)
        self.z1 = 0.0
        self.z2 = 0.0
        self._cache = None

    def _set(self, b0, b1, b2, a0, a1, a2):
        self.b = np.array([b0 / a0, b1 / a0, b2 / a0])
        self.a = np.array([a1 / a0, a2 / a0])

    def design(self, kind, freq, q=0.707, gain_db=0.0):
        key = (kind, round(freq, 3), round(q, 4), round(gain_db, 3))
        if key == self._cache:
            return
        self._cache = key
        f = clip(freq, 20.0, self.sr * 0.49)
        w = TWO_PI * f / self.sr
        cw, sw = np.cos(w), np.sin(w)
        alpha = sw / (2.0 * max(q, 0.05))
        if kind == "lp":
            b0, b1, b2 = (1 - cw) / 2, 1 - cw, (1 - cw) / 2
            a0, a1, a2 = 1 + alpha, -2 * cw, 1 - alpha
        elif kind == "hp":
            b0, b1, b2 = (1 + cw) / 2, -(1 + cw), (1 + cw) / 2
            a0, a1, a2 = 1 + alpha, -2 * cw, 1 - alpha
        elif kind == "bp":
            b0, b1, b2 = alpha, 0.0, -alpha
            a0, a1, a2 = 1 + alpha, -2 * cw, 1 - alpha
        elif kind == "peak":
            A = 10 ** (gain_db / 40.0)
            b0, b1, b2 = 1 + alpha * A, -2 * cw, 1 - alpha * A
            a0, a1, a2 = 1 + alpha / A, -2 * cw, 1 - alpha / A
        elif kind == "notch":
            b0, b1, b2 = 1.0, -2 * cw, 1.0
            a0, a1, a2 = 1 + alpha, -2 * cw, 1 - alpha
        else:
            raise ValueError(kind)
        self._set(b0, b1, b2, a0, a1, a2)

    def process(self, x):
        # scipy lfilter with state is far faster than a python loop
        b = self.b
        a = np.array([1.0, self.a[0], self.a[1]])
        zi = np.array([self.z1, self.z2])
        y, zf = lfilter(b, a, x, zi=zi)
        self.z1, self.z2 = float(zf[0]), float(zf[1])
        return y.astype(np.float32)

    def reset(self):
        self.z1 = self.z2 = 0.0


class FilterChain:
    """N biquads in series, reconfigurable per block."""

    def __init__(self, sr, n):
        self.stages = [Biquad(sr) for _ in range(n)]

    def process(self, x):
        for s in self.stages:
            x = s.process(x)
        return x

    def reset(self):
        for s in self.stages:
            s.reset()


# --------------------------------------------------------------------------
# noise gate + compressor (input conditioning)
# --------------------------------------------------------------------------
class NoiseGate:
    def __init__(self, sr):
        self.sr = sr
        self.threshold_db = -45.0
        self.attack_ms = 3.0
        self.release_ms = 120.0
        self.env = 0.0
        self.gain = 0.0

    def process(self, x):
        thr = db2lin(self.threshold_db)
        # block-rate envelope: cheap and plenty for a gate
        peak = float(np.max(np.abs(x))) if x.size else 0.0
        a_env = np.exp(-1.0 / (0.005 * self.sr / max(x.size, 1)))
        self.env = max(peak, self.env * a_env)
        target = 1.0 if self.env > thr else 0.0
        n = x.size
        coef_a = 1.0 - np.exp(-n / (self.sr * self.attack_ms / 1000.0 + 1e-9))
        coef_r = 1.0 - np.exp(-n / (self.sr * self.release_ms / 1000.0 + 1e-9))
        coef = coef_a if target > self.gain else coef_r
        new_gain = self.gain + (target - self.gain) * coef
        ramp = np.linspace(self.gain, new_gain, n, dtype=np.float32)
        self.gain = new_gain
        return x * ramp


class Compressor:
    def __init__(self, sr):
        self.sr = sr
        self.threshold_db = -18.0
        self.ratio = 3.0
        self.makeup_db = 3.0
        self.env_db = -80.0

    def process(self, x):
        n = x.size
        rms = float(np.sqrt(np.mean(x * x) + 1e-12))
        lvl = 20.0 * np.log10(rms + 1e-12)
        a = 1.0 - np.exp(-n / (self.sr * 0.010))
        self.env_db += (lvl - self.env_db) * a
        over = self.env_db - self.threshold_db
        gr = 0.0 if over <= 0 else -over * (1.0 - 1.0 / max(self.ratio, 1.0))
        return x * db2lin(gr + self.makeup_db)


# --------------------------------------------------------------------------
# granular (delay line) pitch shifter -- sample exact, low latency
# --------------------------------------------------------------------------
class PitchShifter:
    def __init__(self, sr, grain_ms=42.0):
        self.sr = sr
        self.grain = int(sr * grain_ms / 1000.0)
        self.size = 1 << int(np.ceil(np.log2(self.grain * 4)))
        self.buf = np.zeros(self.size, dtype=np.float32)
        self.w = 0
        self.frac = 0.0  # crossfade position inside the grain, [0, 1)
        self.ratio = 1.0

    def reset(self):
        self.buf[:] = 0.0
        self.frac = 0.0

    def _read(self, idx):
        i0 = np.floor(idx).astype(np.int64)
        f = (idx - i0).astype(np.float32)
        m = self.size - 1
        a = self.buf[i0 & m]
        b = self.buf[(i0 + 1) & m]
        return a + (b - a) * f

    def process(self, x, ratio=None):
        if ratio is not None:
            self.ratio = ratio
        r = self.ratio
        n = x.size
        m = self.size - 1
        idx = (np.arange(n, dtype=np.int64) + self.w) & m
        self.buf[idx] = x
        self.w = (self.w + n) % self.size

        if abs(r - 1.0) < 1e-4:
            self.frac = (self.frac + n * 0.0) % 1.0
            return x.copy()

        # delay grows at (1 - r) samples per sample; wrapped into one grain
        step = (1.0 - r) / self.grain
        f = self.frac + step * np.arange(1, n + 1, dtype=np.float64)
        self.frac = float(f[-1] % 1.0)
        f = np.mod(f, 1.0)

        write_pos = (self.w - n) + np.arange(n, dtype=np.float64)
        base = float(self.grain)
        d1 = base + f * self.grain
        d2 = base + np.mod(f + 0.5, 1.0) * self.grain
        # sin/cos crossfade keeps power constant across the grain splice
        w1 = np.sin(np.pi * f).astype(np.float32)
        w2 = np.cos(np.pi * f).astype(np.float32)
        y = self._read(write_pos - d1 + self.size) * w1 + \
            self._read(write_pos - d2 + self.size) * w2
        return y.astype(np.float32)


# --------------------------------------------------------------------------
# spectral engine: formant shift, robot, whisper, spectral gate
# STFT with sqrt-Hann analysis/synthesis, hop = win/4 -> exact OLA
# --------------------------------------------------------------------------
class Spectral:
    def __init__(self, sr, win=1024):
        self.sr = sr
        self.win = win
        self.hop = win // 4
        w = np.hanning(win + 1)[:win].astype(np.float32)
        self.window = np.sqrt(np.maximum(w, 0)).astype(np.float32)
        self.window *= np.sqrt(2.0 / 3.0)  # COLA normalisation for hop=win/4
        self.in_buf = np.zeros(win, dtype=np.float32)
        self.in_fill = 0
        self.out_buf = np.zeros(win * 2, dtype=np.float32)
        self.out_ready = 0
        self.freqs = np.fft.rfftfreq(win, 1.0 / sr)
        self.nbins = self.freqs.size
        self.rng = np.random.default_rng(12345)
        # parameters
        self.formant = 1.0     # multiplicative formant shift
        self.robot = False
        self.whisper = False
        self.spectral_gate_db = None   # e.g. -60 to denoise
        self.noise_floor = np.zeros(self.nbins, dtype=np.float32)
        self.latency = win

    def reset(self):
        self.in_buf[:] = 0
        self.in_fill = 0
        self.out_buf[:] = 0
        self.out_ready = 0

    @property
    def active(self):
        return (self.robot or self.whisper or abs(self.formant - 1.0) > 1e-3
                or self.spectral_gate_db is not None)

    def _envelope(self, mag):
        """Cepstral spectral envelope (vocal tract shape)."""
        log_mag = np.log(mag + 1e-7)
        ceps = np.fft.rfft(log_mag)
        cut = 32
        ceps[cut:] = 0.0
        env = np.exp(np.fft.irfft(ceps, n=log_mag.size))
        return env.astype(np.float32)

    def _frame(self, frame):
        spec = np.fft.rfft(frame * self.window)
        mag = np.abs(spec)
        phase = np.angle(spec)

        if self.spectral_gate_db is not None:
            thr = db2lin(self.spectral_gate_db) * np.max(mag + 1e-9)
            mag = np.where(mag < thr, mag * 0.05, mag)

        if abs(self.formant - 1.0) > 1e-3:
            env = self._envelope(mag)
            resid = mag / (env + 1e-7)
            src = np.arange(self.nbins) / self.formant
            env2 = np.interp(src, np.arange(self.nbins), env,
                             left=env[0], right=env[-1]).astype(np.float32)
            mag = resid * env2

        if self.robot:
            phase = np.zeros_like(phase)
        elif self.whisper:
            phase = self.rng.uniform(-np.pi, np.pi, self.nbins)

        spec = mag * np.exp(1j * phase)
        out = np.fft.irfft(spec, n=self.win).astype(np.float32)
        if self.robot or self.whisper:
            # rewriting the phase destroys the OLA gain; restore frame energy
            e_in = float(np.sqrt(np.mean(frame * frame) + 1e-12))
            e_out = float(np.sqrt(np.mean(out * out) + 1e-12))
            out *= min(e_in / e_out, 8.0)
        return out * self.window

    def process(self, x):
        n = x.size
        pos = 0
        while pos < n:
            take = min(self.hop - self.in_fill, n - pos)
            self.in_buf[self.win - self.hop + self.in_fill:
                        self.win - self.hop + self.in_fill + take] = x[pos:pos + take]
            self.in_fill += take
            pos += take
            if self.in_fill == self.hop:
                out = self._frame(self.in_buf)
                self.out_buf[self.out_ready:self.out_ready + self.win] += out
                self.out_ready += self.hop
                self.in_buf[:-self.hop] = self.in_buf[self.hop:]
                self.in_fill = 0
        if self.out_ready < n:
            # not enough output yet (startup) -- emit silence, stay aligned
            pad = np.zeros(n, dtype=np.float32)
            k = min(self.out_ready, n)
            pad[:k] = self.out_buf[:k]
            self.out_buf[:-k or None] = self.out_buf[k:] if k else self.out_buf
            self.out_buf[len(self.out_buf) - k:] = 0.0
            self.out_ready -= k
            return pad
        y = self.out_buf[:n].copy()
        self.out_buf[:-n] = self.out_buf[n:]
        self.out_buf[-n:] = 0.0
        self.out_ready -= n
        return y


# --------------------------------------------------------------------------
# modulated delay: chorus / flanger / vibrato
# --------------------------------------------------------------------------
class ModDelay:
    def __init__(self, sr, max_ms=60.0):
        self.sr = sr
        self.size = 1 << int(np.ceil(np.log2(sr * max_ms / 1000.0 + 4)))
        self.buf = np.zeros(self.size, dtype=np.float32)
        self.w = 0
        self.phase = 0.0
        self.rate = 0.8          # Hz
        self.depth_ms = 3.0
        self.base_ms = 12.0
        self.mix = 0.5
        self.feedback = 0.0
        self.voices = 1
        self.spread = 0.33       # LFO phase offset between voices

    def reset(self):
        self.buf[:] = 0.0

    def process(self, x):
        n = x.size
        m = self.size - 1
        t = np.arange(n, dtype=np.float64)
        ph = self.phase + self.rate * t / self.sr
        self.phase = float((self.phase + self.rate * n / self.sr) % 1.0)
        wpos = self.w + np.arange(n, dtype=np.float64)

        # write dry (plus feedback of the previous block's tail) into the line
        idx = (self.w + np.arange(n, dtype=np.int64)) & m
        if self.feedback > 0.0:
            d0 = int(self.sr * self.base_ms / 1000.0)
            fb = self.buf[(idx - d0) & m] * self.feedback
            self.buf[idx] = x + fb
        else:
            self.buf[idx] = x
        self.w = (self.w + n) % self.size

        wet = np.zeros(n, dtype=np.float32)
        for v in range(self.voices):
            lfo = np.sin(TWO_PI * (ph + v * self.spread))
            delay = (self.base_ms + self.depth_ms * lfo) * self.sr / 1000.0
            rd = wpos - delay + self.size
            i0 = np.floor(rd).astype(np.int64)
            f = (rd - i0).astype(np.float32)
            a = self.buf[i0 & m]
            b = self.buf[(i0 + 1) & m]
            wet += (a + (b - a) * f)
        wet /= max(self.voices, 1)
        return (x * (1.0 - self.mix) + wet * self.mix).astype(np.float32)


class Phaser:
    """Cascaded first-order allpasses, coefficient updated per 64-sample slice."""

    SLICE = 64

    def __init__(self, sr, stages=6):
        self.sr = sr
        self.n = stages
        self.zi = [np.zeros(1) for _ in range(stages)]
        self.phase = 0.0
        self.rate = 0.4
        self.depth = 0.7
        self.feedback = 0.4
        self.mix = 0.6
        self.fb = 0.0

    def reset(self):
        self.zi = [np.zeros(1) for _ in range(self.n)]
        self.fb = 0.0

    def process(self, x):
        lo, hi = 300.0, 3000.0
        out = np.empty_like(x)
        pos = 0
        while pos < x.size:
            k = min(self.SLICE, x.size - pos)
            seg = x[pos:pos + k]
            lfo = 0.5 + 0.5 * np.sin(TWO_PI * self.phase)
            self.phase = (self.phase + self.rate * k / self.sr) % 1.0
            f = lo * (hi / lo) ** (lfo * self.depth)
            tw = np.tan(np.pi * f / self.sr)
            a = (1.0 - tw) / (1.0 + tw)
            s = seg + self.fb * self.feedback
            for i in range(self.n):
                s, zf = lfilter([a, 1.0], [1.0, a], s, zi=self.zi[i])
                self.zi[i] = zf
            self.fb = float(s[-1])
            out[pos:pos + k] = seg * (1.0 - self.mix) + s.astype(np.float32) * self.mix
            pos += k
        return out


# --------------------------------------------------------------------------
# echo + reverb (Freeverb-style)
# --------------------------------------------------------------------------
class Echo:
    def __init__(self, sr):
        self.sr = sr
        self.size = 1 << int(np.ceil(np.log2(sr * 2.5)))
        self.buf = np.zeros(self.size, dtype=np.float32)
        self.w = 0
        self.time_ms = 320.0
        self.feedback = 0.38
        self.mix = 0.35
        self.damp = 0.35
        self.lp = 0.0

    def reset(self):
        self.buf[:] = 0.0
        self.lp = 0.0

    def process(self, x):
        n = x.size
        m = self.size - 1
        d = max(int(self.sr * self.time_ms / 1000.0), n + 1)
        idx = (self.w + np.arange(n, dtype=np.int64)) & m
        tap = self.buf[(idx - d) & m]
        # one-pole damping on the feedback path, vectorised approximation
        if self.damp > 0:
            a = float(self.damp)
            tap, zf = lfilter([1 - a], [1.0, -a], tap, zi=[self.lp])
            self.lp = float(zf[0])
            tap = tap.astype(np.float32)
        self.buf[idx] = x + tap * self.feedback
        self.w = (self.w + n) % self.size
        return (x * (1.0 - self.mix * 0.5) + tap * self.mix).astype(np.float32)


class Reverb:
    """Freeverb: 8 parallel combs -> 4 series allpasses. All delays > blocksize."""

    COMBS = [1116, 1188, 1277, 1356, 1422, 1491, 1557, 1617]
    ALLPS = [556, 441, 341, 225]

    def __init__(self, sr):
        self.sr = sr
        k = sr / 44100.0
        self.cd = [max(int(d * k), 600) for d in self.COMBS]
        self.ad = [max(int(d * k), 200) for d in self.ALLPS]
        self.cbuf = [np.zeros(d, dtype=np.float32) for d in self.cd]
        self.cidx = [0] * len(self.cd)
        self.cfilt = [0.0] * len(self.cd)
        self.abuf = [np.zeros(d, dtype=np.float32) for d in self.ad]
        self.aidx = [0] * len(self.ad)
        self.room = 0.72
        self.damp = 0.35
        self.mix = 0.28
        self.width = 1.0

    def reset(self):
        for b in self.cbuf:
            b[:] = 0.0
        for b in self.abuf:
            b[:] = 0.0
        self.cfilt = [0.0] * len(self.cd)

    def process(self, x):
        n = x.size
        inp = x * 0.030
        acc = np.zeros(n, dtype=np.float32)
        for i, d in enumerate(self.cd):
            buf, p = self.cbuf[i], self.cidx[i]
            if d < n:  # should not happen, but stay safe
                continue
            take = np.empty(n, dtype=np.float32)
            idx = (p + np.arange(n)) % d
            take[:] = buf[idx]
            damped, zf = lfilter([1 - self.damp], [1.0, -self.damp], take,
                                 zi=[self.cfilt[i]])
            self.cfilt[i] = float(zf[0])
            buf[idx] = inp + damped.astype(np.float32) * self.room
            self.cidx[i] = (p + n) % d
            acc += take
        for i, d in enumerate(self.ad):
            buf, p = self.abuf[i], self.aidx[i]
            if d < n:
                continue
            idx = (p + np.arange(n)) % d
            delayed = buf[idx].copy()
            out = delayed - acc
            buf[idx] = acc + delayed * 0.5
            self.aidx[i] = (p + n) % d
            acc = out
        return (x * (1.0 - self.mix * 0.4) + acc * self.mix * 3.0).astype(np.float32)


# --------------------------------------------------------------------------
# non-linear + modulation
# --------------------------------------------------------------------------
class Distortion:
    def __init__(self):
        self.drive = 1.0
        self.kind = "tanh"   # tanh | fold | fuzz | hard
        self.mix = 1.0

    def process(self, x):
        d = max(self.drive, 0.01)
        if self.kind == "tanh":
            y = np.tanh(x * d) / np.tanh(d if d > 1 else 1.0)
        elif self.kind == "hard":
            y = np.clip(x * d, -1.0, 1.0)
        elif self.kind == "fold":
            y = np.sin(x * d * 1.6)
        else:  # fuzz
            s = np.sign(x)
            y = s * (1.0 - np.exp(-np.abs(x * d)))
        return (x * (1 - self.mix) + y.astype(np.float32) * self.mix)


class BitCrusher:
    def __init__(self, sr):
        self.sr = sr
        self.bits = 8.0
        self.downsample = 1
        self.hold = 0.0
        self.count = 0
        self.mix = 1.0

    def process(self, x):
        y = x
        ds = int(max(self.downsample, 1))
        if ds > 1:
            n = x.size
            idx = ((np.arange(n) + self.count) // ds) * ds - self.count
            idx = np.clip(idx, 0, n - 1)
            first = idx < 0
            y = x[idx]
            if self.count % ds:
                y[: (ds - self.count % ds) % ds] = self.hold
            self.hold = float(y[-1])
            self.count = (self.count + n) % ds
        if self.bits < 16:
            q = 2.0 ** self.bits
            y = np.round(y * q) / q
        return (x * (1 - self.mix) + y.astype(np.float32) * self.mix)


class RingMod:
    def __init__(self, sr):
        self.sr = sr
        self.freq = 60.0
        self.mix = 1.0
        self.phase = 0.0

    def process(self, x):
        n = x.size
        t = np.arange(n, dtype=np.float64)
        ph = self.phase + self.freq * t / self.sr
        self.phase = float((self.phase + self.freq * n / self.sr) % 1.0)
        car = np.sin(TWO_PI * ph).astype(np.float32)
        return (x * (1 - self.mix) + x * car * self.mix)


class Tremolo:
    def __init__(self, sr):
        self.sr = sr
        self.rate = 5.0
        self.depth = 0.6
        self.phase = 0.0

    def process(self, x):
        n = x.size
        t = np.arange(n, dtype=np.float64)
        ph = self.phase + self.rate * t / self.sr
        self.phase = float((self.phase + self.rate * n / self.sr) % 1.0)
        lfo = 1.0 - self.depth * (0.5 + 0.5 * np.sin(TWO_PI * ph))
        return (x * lfo).astype(np.float32)


class AutoWah:
    def __init__(self, sr):
        self.sr = sr
        self.bq = Biquad(sr)
        self.env = 0.0
        self.sens = 6.0
        self.lo = 300.0
        self.hi = 2600.0
        self.q = 4.0
        self.mix = 0.8

    def reset(self):
        self.bq.reset()
        self.env = 0.0

    def process(self, x):
        rms = float(np.sqrt(np.mean(x * x) + 1e-12))
        self.env += (rms - self.env) * 0.35
        f = self.lo + (self.hi - self.lo) * clip(self.env * self.sens, 0.0, 1.0)
        self.bq.design("bp", f, self.q)
        wet = self.bq.process(x) * 3.2
        return (x * (1 - self.mix) + wet * self.mix).astype(np.float32)


# --------------------------------------------------------------------------
# pitch detection (for autotune)
# --------------------------------------------------------------------------
class PitchTracker:
    def __init__(self, sr, fmin=70.0, fmax=500.0):
        self.sr = sr
        self.fmin = fmin
        self.fmax = fmax
        self.buf = np.zeros(int(sr * 0.045), dtype=np.float32)
        self.f0 = 0.0

    def push(self, x):
        n = min(x.size, self.buf.size)
        self.buf[:-n] = self.buf[n:]
        self.buf[-n:] = x[-n:]

    def estimate(self):
        b = self.buf
        if float(np.sqrt(np.mean(b * b) + 1e-12)) < 0.004:
            self.f0 = 0.0
            return 0.0
        x = b - b.mean()
        n = x.size
        f = np.fft.rfft(x, 2 * n)
        ac = np.fft.irfft(f * np.conj(f))[:n]
        ac /= (ac[0] + 1e-9)
        lo = int(self.sr / self.fmax)
        hi = min(int(self.sr / self.fmin), n - 1)
        if hi <= lo + 2:
            return 0.0
        seg = ac[lo:hi]
        k = int(np.argmax(seg))
        if seg[k] < 0.35:
            self.f0 = 0.0
            return 0.0
        p = lo + k
        # parabolic refinement
        if 0 < p < n - 1:
            a, b2, c = ac[p - 1], ac[p], ac[p + 1]
            d = a - 2 * b2 + c
            if abs(d) > 1e-9:
                p = p + 0.5 * (a - c) / d
        self.f0 = self.sr / p
        return self.f0


SCALES = {
    "chromatic": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
    "major":     [0, 2, 4, 5, 7, 9, 11],
    "minor":     [0, 2, 3, 5, 7, 8, 10],
    "pentatonic": [0, 3, 5, 7, 10],
}
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def snap_ratio(f0, root=0, scale="minor"):
    """Ratio that moves f0 onto the nearest scale degree."""
    if f0 <= 0:
        return 1.0
    midi = 69.0 + 12.0 * np.log2(f0 / 440.0)
    degrees = SCALES.get(scale, SCALES["chromatic"])
    best, bd = midi, 1e9
    base = np.floor(midi)
    for oct_off in (-1, 0, 1):
        for d in degrees:
            cand = np.floor((base - root) / 12.0) * 12 + root + d + 12 * oct_off
            dist = abs(cand - midi)
            if dist < bd:
                bd, best = dist, cand
    return float(2.0 ** ((best - midi) / 12.0))

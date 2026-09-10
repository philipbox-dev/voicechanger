"""PipeWire/PulseAudio virtual microphone so other apps hear the processed voice.

Creates a null sink advertised as `Audio/Source/Virtual`, which PipeWire exposes
to applications as a regular microphone. The engine's output stream is then
moved onto that node with `pactl move-sink-input`.
"""

import json
import os
import subprocess

SINK_NAME = "VoiceChangerSink"      # we play into this
SOURCE_NAME = "VoiceChanger"        # other apps record from this
DESCRIPTION = "Voice Changer (virtual mic)"


def _pactl(*args, json_out=False):
    cmd = ["pactl"] + (["-f", "json"] if json_out else []) + list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(f"pactl failed: {e}")
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "pactl error")
    return json.loads(r.stdout) if json_out else r.stdout.strip()


def available():
    return subprocess.run(["which", "pactl"], capture_output=True).returncode == 0


def _has(name, kind):
    try:
        return any(o.get("name") == name for o in _pactl("list", kind, json_out=True))
    except Exception:
        return False


def exists():
    """True when both halves of the virtual mic are up."""
    return _has(SINK_NAME, "sinks") and _has(SOURCE_NAME, "sources")


def create():
    """Create the virtual mic: a null sink plus a remapped source on its monitor.

    The plain null sink is what `move-sink-input` can target; the remap-source
    turns its monitor into a real capture device that Discord/OBS/Zoom list as
    an ordinary microphone.
    """
    made = []
    if not _has(SINK_NAME, "sinks"):
        made.append(_pactl(
            "load-module", "module-null-sink",
            f"sink_name={SINK_NAME}",
            "sink_properties=device.description=VoiceChanger\\ Sink",
            "channel_map=front-left,front-right",
        ).strip())
    if not _has(SOURCE_NAME, "sources"):
        made.append(_pactl(
            "load-module", "module-remap-source",
            f"master={SINK_NAME}.monitor",
            f"source_name={SOURCE_NAME}",
            "source_properties=device.description=Voice\\ Changer\\ (virtual\\ mic)",
            "channel_map=front-left,front-right",
        ).strip())
    return made


def destroy():
    """Unload every module we created (source first, then sink, then loopbacks)."""
    removed = 0
    try:
        lines = _pactl("list", "short", "modules").splitlines()
    except Exception:
        return 0
    for want in ("module-loopback", "module-remap-source", "module-null-sink"):
        for line in lines:
            parts = line.split("\t")
            if len(parts) >= 2 and parts[1] == want and len(parts) >= 3 and (
                    SINK_NAME in parts[2] or SOURCE_NAME in parts[2]):
                try:
                    _pactl("unload-module", parts[0])
                    removed += 1
                except Exception:
                    pass
    return removed


def sink_index(name=SINK_NAME):
    for s in _pactl("list", "sinks", json_out=True):
        if s.get("name") == name:
            return s.get("index")
    return None


def input_indices():
    """Snapshot of current playback-stream indices (call before starting audio)."""
    try:
        return {si["index"] for si in _pactl("list", "sink-inputs", json_out=True)}
    except Exception:
        return set()


def _own_inputs(before=None):
    """Find this process's playback streams.

    PipeWire's ALSA client does not always publish application.process.id, so we
    fall back to the app name and finally to whatever stream appeared after the
    `before` snapshot was taken.
    """
    import sys as _sys
    pid = str(os.getpid())
    exe = os.path.basename(_sys.executable)
    by_pid, by_name, fresh = [], [], []
    try:
        items = _pactl("list", "sink-inputs", json_out=True)
    except Exception:
        return []
    for si in items:
        props = si.get("properties", {}) or {}
        idx = si["index"]
        if str(props.get("application.process.id")) == pid:
            by_pid.append(idx)
        elif exe in str(props.get("application.name", "")):
            by_name.append(idx)
        if before is not None and idx not in before:
            fresh.append(idx)
    if by_pid:
        return by_pid
    if before is not None and fresh:
        # prefer streams that are both new and look like us
        both = [i for i in fresh if i in by_name]
        return both or fresh
    return by_name


def route_output(sink=SINK_NAME, before=None):
    """Move this process's playback stream onto `sink`. Returns True on success."""
    moved = False
    for idx in _own_inputs(before):
        try:
            _pactl("move-sink-input", str(idx), sink)
            moved = True
        except Exception:
            pass
    return moved


def current_route(before=None):
    """Name of the sink this process is currently playing to, if any."""
    try:
        sinks = {s["index"]: s["name"]
                 for s in _pactl("list", "sinks", json_out=True)}
        own = set(_own_inputs(before))
        for si in _pactl("list", "sink-inputs", json_out=True):
            if si["index"] in own:
                return sinks.get(si.get("sink"), str(si.get("sink")))
    except Exception:
        pass
    return None


def monitor_on(sink=None):
    """Loop the virtual mic back to the speakers so you can hear yourself."""
    target = sink or "@DEFAULT_SINK@"
    return _pactl("load-module", "module-loopback",
                  f"source={SINK_NAME}.monitor", f"sink={target}",
                  "latency_msec=40")


def monitor_off():
    n = 0
    for line in _pactl("list", "short", "modules").splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[1] == "module-loopback" and SINK_NAME in parts[2]:
            _pactl("unload-module", parts[0])
            n += 1
    return n


def list_sinks():
    try:
        return [(s["index"], s["name"], s.get("description", "")) 
                for s in _pactl("list", "sinks", json_out=True)]
    except Exception:
        return []

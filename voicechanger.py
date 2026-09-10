#!/usr/bin/env python3
"""Realtime voice changer -- GUI, CLI and offline file rendering.

  ./voicechanger.py                     graphical control panel
  ./voicechanger.py --list              list audio devices and presets
  ./voicechanger.py --cli --preset Demon --vmic
  ./voicechanger.py --render in.wav out.wav --preset Robot
"""

import argparse
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from vc.engine import Engine
from vc.presets import PRESETS


def cmd_list():
    ins, outs = Engine.devices()
    print("ВХОДЫ (микрофоны):")
    for i, l in ins:
        print("  ", l)
    print("\nВЫХОДЫ:")
    for i, l in outs:
        print("  ", l)
    print(f"\nПРЕСЕТЫ ({len(PRESETS)}):")
    names = list(PRESETS)
    for i in range(0, len(names), 3):
        print("  " + "".join(f"{n:<24}" for n in names[i:i + 3]))


def resolve_preset(name):
    if name in PRESETS:
        return name
    hits = [n for n in PRESETS if n.lower().startswith(name.lower())]
    if not hits:
        hits = [n for n in PRESETS if name.lower() in n.lower()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        sys.exit(f"Пресет не найден: {name!r} (см. --list)")
    sys.exit(f"Неоднозначно: {name!r} -> {', '.join(hits)}")


def cmd_render(args):
    import numpy as np
    import soundfile as sf
    from vc.engine import Chain
    data, sr = sf.read(args.render[0], dtype="float32", always_2d=True)
    x = data.mean(axis=1)
    chain = Chain(sr)
    chain.load(PRESETS[resolve_preset(args.preset)])
    bs = 256
    out = []
    for i in range(0, len(x) - bs, bs):
        out.append(chain.process(x[i:i + bs]))
    sf.write(args.render[1], np.concatenate(out), sr)
    print(f"Записано: {args.render[1]}")


def cmd_cli(args):
    from vc import virtualmic as vmic
    name = resolve_preset(args.preset)
    eng = Engine(blocksize=args.blocksize)
    eng.chain.load(PRESETS[name])

    before = None
    if args.vmic:
        if not vmic.available():
            sys.exit("pactl не найден -- виртуальный микрофон недоступен")
        vmic.create()
        before = vmic.input_indices()
        print("Виртуальный микрофон «VoiceChanger» создан")

    eng.start(args.input, args.output)
    if args.vmic:
        time.sleep(0.6)
        print("Маршрутизация в виртуальный микрофон:",
              "ок" if vmic.route_output(before=before) else "не удалась")
    print(f"Пресет: {name} | задержка ~{eng.latency_ms():.0f} мс | Ctrl+C для выхода")
    try:
        while True:
            time.sleep(0.5)
            print(f"\r  CPU {eng.cpu:5.1f}%  сбоев {eng.xruns}   ", end="", flush=True)
            if eng.error:
                print("\nОшибка обработки:", eng.error)
                eng.error = None
    except KeyboardInterrupt:
        print()
    finally:
        eng.stop()
        if args.vmic and not args.keep_vmic:
            vmic.destroy()
            print("Виртуальный микрофон удалён")


def main():
    ap = argparse.ArgumentParser(description="Realtime voice changer")
    ap.add_argument("--list", action="store_true", help="показать устройства и пресеты")
    ap.add_argument("--cli", action="store_true", help="запуск без графики")
    ap.add_argument("--preset", default="Clean (bypass)")
    ap.add_argument("--input", type=int, default=None, help="номер входного устройства")
    ap.add_argument("--output", type=int, default=None, help="номер выходного устройства")
    ap.add_argument("--blocksize", type=int, default=256)
    ap.add_argument("--vmic", action="store_true", help="создать виртуальный микрофон")
    ap.add_argument("--keep-vmic", action="store_true", help="не удалять его при выходе")
    ap.add_argument("--render", nargs=2, metavar=("IN.wav", "OUT.wav"))
    args = ap.parse_args()

    if args.list:
        cmd_list()
    elif args.render:
        cmd_render(args)
    elif args.cli:
        cmd_cli(args)
    else:
        from vc.gui import main as gui_main
        gui_main()


if __name__ == "__main__":
    main()

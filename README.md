# Voice Changer — реалтайм обработка голоса

Реалтайм войс-чейнджер для Linux/PipeWire: 51 пресет, ~25 регулируемых параметров,
виртуальный микрофон для Discord / OBS / Zoom.

## Запуск

```bash
cd ~/voicechanger
./voicechanger.py                 # окно с пресетами и слайдерами
./voicechanger.py --list          # список устройств и пресетов
./voicechanger.py --cli --preset Demon --vmic     # без графики
./voicechanger.py --render in.wav out.wav --preset Robot   # обработать файл
```

## Виртуальный микрофон

Кнопка **«Создать вирт. микрофон»** (или флаг `--vmic`) заводит устройство
**VoiceChanger** — выбери его как микрофон в Discord/OBS/Zoom, и они услышат
обработанный голос. Программа сама перенаправляет свой выход в него.
Галочка **«Слышать себя»** возвращает звук в наушники для контроля.

Технически: `module-null-sink` (туда пишем) + `module-remap-source` (оттуда
читают приложения). При выходе всё выгружается.

## Горячие клавиши

| Клавиша | Действие |
|---|---|
| `Пробел` | байпас (сухой голос) |
| `↑` / `↓` | предыдущий / следующий пресет |
| `Ctrl+M` | мьют |
| двойной клик по слайдеру | сброс параметра |

## Пресеты

**Чистые:** Clean, Radio Voice, Podcast Warm, Studio Wide
**Пол/возраст:** Female, Male, Deep Male, Little Girl, Small Child, Old Man, Grandma
**Мультяшные:** Chipmunk, Helium, Squirrel, Duck, Cartoon Mouse
**Монстры:** Monster, Demon, Giant, Troll, Ghost, Zombie
**Роботы:** Robot, Hard Robot, Cyborg, Dalek, Alien, Space Radio, Vader, AI Assistant
**Пространства:** Cave, Stadium, Hall, Telephone, Megaphone, Underwater, Walkie Talkie
**Музыкальные:** Autotune Hard, T-Pain, Choir Octave, Flanger Jet, Phaser Sweep,
Wah Funk, Tremolo, Lo-Fi 8bit, Fuzz Scream
**Прочее:** Whisper, Drunk, Slow Motion, Anonymous TV, Stadium Announcer

Свои пресеты сохраняются кнопкой «Сохранить свой» в `~/.config/voicechanger.json`.

## Эффекты в цепочке

шумодав → компрессор → **питч-шифт** (±24 полутона, гранулярный, точность ~2 цента)
→ **автотюн** (chromatic/major/minor/pentatonic) → **сдвиг формант** (кепстральный,
меняет тембр не трогая высоту) → **робот** / **шёпот** / спектральный шумодав
→ HP/LP/пик-эквалайзер → **перегруз** (tanh/hard/fold/fuzz) → **биткрашер**
→ **кольцевая модуляция** → **ва-ва** → **фейзер** → **хорус/флэнжер/вибрато**
→ **тремоло** → **эхо** → **реверб** (Freeverb) → мягкий лимитер

## Производительность

Замерено на этой машине: задержка 48–53 мс (буфер 256), CPU 2–13% одного ядра
в зависимости от пресета, 0 сбоев буфера. Буфер меняется в окне: 64 сэмпла даёт
меньшую задержку, 512 — больший запас прочности.

## Файлы

```
voicechanger.py     точка входа (GUI / CLI / рендер)
vc/dsp.py           DSP-примитивы: фильтры, питч-шифтер, STFT, задержки, реверб
vc/engine.py        цепочка эффектов + аудиопоток
vc/presets.py       схема параметров и библиотека пресетов
vc/gui.py           окно управления
vc/virtualmic.py    виртуальный микрофон через PipeWire
```

Зависимости (уже установлены): numpy, scipy, sounddevice, soundfile, tkinter.

#!/usr/bin/env python3
"""Автопроверка практики «Ролик из отчёта по каналам». Запускается из корня проекта ролика:

    python3 ../claude-code-kit/reels/checks/check_reel.py

Ждёт в проекте раскадровку storyboard.md и файлы рендера в out/: reel-01.mp4 (Reels и TikTok),
reel-01-shorts.mp4 и reel-01-shorts.srt (YouTube Shorts), cover.png. Скрипт только читает файлы:
размеры, частоту кадров и длительность берёт из контейнера MP4, ничего не запускает и не ходит в сеть.
"""
import json
import pathlib
import re
import struct
import sys

KIT_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KIT_ROOT / "kitlib"))
from check import Check, Result, Stop  # noqa: E402

EXP = json.loads((pathlib.Path(__file__).resolve().parent / "expected" / "reel.json").read_text(encoding="utf-8"))
check = Check("Проверка практики «Ролик из отчёта по каналам»")
ctx = {}


# --- MP4: just enough of ISO BMFF to read the video track ---------------------------------------

def _boxes(data, start, end):
    pos = start
    while pos + 8 <= end:
        size, kind = struct.unpack(">I4s", data[pos:pos + 8])
        header = 8
        if size == 1:
            size = struct.unpack(">Q", data[pos + 8:pos + 16])[0]
            header = 16
        elif size == 0:
            size = end - pos
        if size < header or pos + size > end:
            return
        yield kind.decode("latin-1"), pos + header, pos + size
        pos += size


def _child(data, start, end, kind):
    for k, s, e in _boxes(data, start, end):
        if k == kind:
            return s, e
    return None


def _path(data, start, end, *kinds):
    span = (start, end)
    for kind in kinds:
        span = _child(data, span[0], span[1], kind)
        if span is None:
            return None
    return span


def read_mp4(path):
    """Width, height, fps and duration of the first video track, or a reason why not."""
    data = path.read_bytes()
    moov = _child(data, 0, len(data), "moov")
    if moov is None:
        return None, "в файле нет блока moov: это не MP4 или рендер не закончился"
    for kind, s, e in _boxes(data, *moov):
        if kind != "trak":
            continue
        hdlr = _path(data, s, e, "mdia", "hdlr")
        if hdlr is None or data[hdlr[0] + 8:hdlr[0] + 12] != b"vide":
            continue
        tkhd = _child(data, s, e, "tkhd")
        mdhd = _path(data, s, e, "mdia", "mdhd")
        stts = _path(data, s, e, "mdia", "minf", "stbl", "stts")
        if not (tkhd and mdhd and stts):
            return None, "у видеодорожки не хватает служебных блоков"
        width = struct.unpack(">I", data[tkhd[1] - 8:tkhd[1] - 4])[0] >> 16
        height = struct.unpack(">I", data[tkhd[1] - 4:tkhd[1]])[0] >> 16
        version = data[mdhd[0]]
        if version == 1:
            timescale, duration = struct.unpack(">IQ", data[mdhd[0] + 20:mdhd[0] + 32])
        else:
            timescale, duration = struct.unpack(">II", data[mdhd[0] + 12:mdhd[0] + 20])
        count = struct.unpack(">I", data[stts[0] + 4:stts[0] + 8])[0]
        frames = 0
        for i in range(count):
            n, _delta = struct.unpack(">II", data[stts[0] + 8 + i * 8:stts[0] + 16 + i * 8])
            frames += n
        seconds = duration / timescale if timescale else 0
        fps = frames / seconds if seconds else 0
        return {"width": width, "height": height, "fps": fps, "seconds": seconds, "frames": frames,
                "megabytes": len(data) / 1_000_000}, None
    return None, "в файле нет видеодорожки"


def png_size(path):
    head = path.read_bytes()[:24]
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", head[16:24])


# --- SRT ------------------------------------------------------------------------------------------

TIME = re.compile(r"^(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2}):(\d{2}):(\d{2}),(\d{3})$")


def _ms(h, m, s, ms):
    return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + int(ms)


def read_srt(path):
    text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").strip()
    cues, problems = [], []
    for number, block in enumerate(re.split(r"\n\s*\n", text), start=1):
        lines = block.split("\n")
        if len(lines) < 3:
            problems.append(f"реплика {number}: нужны номер, время и хотя бы одна строка текста")
            continue
        if lines[0].strip() != str(number):
            problems.append(f"реплика {number}: номер «{lines[0].strip()}» вместо {number}")
        match = TIME.match(lines[1].strip())
        if not match:
            problems.append(f"реплика {number}: время не в формате 00:00:00,000 --> 00:00:00,000")
            continue
        g = match.groups()
        cues.append({"n": number, "start": _ms(*g[:4]), "end": _ms(*g[4:]), "lines": lines[2:]})
    return cues, problems


def digits(text):
    """Numbers with spaces inside (34 700, 34 700 with a no-break space) glued together."""
    return re.sub(r"(?<=\d)[    ](?=\d{3}\b)", "", text)


def missing_numbers(text):
    """Key numbers absent from the text; each number may be written in several accepted ways (113 or 112,5)."""
    glued = digits(text)
    return [ways[0] for ways in EXP["key_numbers"]
            if not any(re.search(rf"(?<![\d.,]){re.escape(n)}(?![\d])", glued) for n in ways)]


def fmt(n):
    return f"{int(n):,}".replace(",", " ")


# --- criteria -------------------------------------------------------------------------------------

@check.before
def _setup():
    root = pathlib.Path.cwd()
    out = root / "out"
    if not (root / "package.json").exists() and not out.exists():
        lines = ["Здесь нет ни package.json, ни папки out/.",
                 "Запускайте проверку из корня проекта ролика, когда рендер уже сделан."]
        if (root / "scripts" / "build_status.py").exists():
            lines.append("Похоже, это launch-kit: проект ролика живёт в своей папке рядом с ним.")
        raise Stop(*lines)
    ctx["root"], ctx["out"] = root, out
    srt = sorted(out.rglob("reel-01-shorts.srt")) if out.exists() else []
    ctx["srt"] = srt[0] if srt else None
    print(f"Проект: {root.name} · файлов в out/: {sum(1 for p in out.rglob('*') if p.is_file()) if out.exists() else 0}")
    print()


@check.criterion("Раскадровка")
def _storyboard():
    path = ctx["root"] / "storyboard.md"
    if not path.exists():
        return Result(False, fail="Нет storyboard.md",
                      hint="раскадровку пишут до кода: таблица «время — кадр — субтитр» в storyboard.md.")
    text = path.read_text(encoding="utf-8")
    stamps = sorted({int(m) * 60 + int(s) for m, s in re.findall(r"(?<![\d:])(\d{1,2}):(\d{2})(?![\d:])", text)})
    problems = []
    if len(stamps) < EXP["min_scenes"]:
        problems.append(f"таймкодов {len(stamps)}, нужно хотя бы {EXP['min_scenes']} сцены")
    if stamps and stamps[-1] >= EXP["max_seconds"]:
        problems.append(f"последняя сцена начинается на {stamps[-1]} с, а ролик короче {EXP['max_seconds']} с")
    gone = missing_numbers(text)
    if gone:
        problems.append("нет чисел отчёта: " + ", ".join(fmt(n) for n in gone))
    return Result(not problems, pass_=f"Раскадровка: таймкодов {len(stamps)}, числа из отчёта на месте",
                  fail="Раскадровка не готова", details=problems,
                  hint="числа в ролике берут только из channel-summary.csv и campaigns.csv: сверьте их с отчётом.")


def _video_result(name, label):
    path = ctx["out"] / name
    if not path.exists():
        return None, Result(False, fail=f"Нет out/{name}", hint=f"отрендерите {label} в out/{name}.")
    info, error = read_mp4(path)
    if error:
        return None, Result(False, fail=f"out/{name} не читается", details=[error])
    problems = []
    if (info["width"], info["height"]) != (EXP["width"], EXP["height"]):
        problems.append(f"кадр {info['width']}×{info['height']}, нужен {EXP['width']}×{EXP['height']}")
    if abs(info["fps"] - EXP["fps"]) > 0.05:
        problems.append(f"{info['fps']:.2f} кадра в секунду, нужно {EXP['fps']}")
    if not EXP["min_seconds"] <= info["seconds"] <= EXP["max_seconds"] + 0.05:
        problems.append(f"длительность {info['seconds']:.1f} с, нужно от {EXP['min_seconds']} до {EXP['max_seconds']} с")
    if info["megabytes"] > EXP["max_megabytes"]:
        problems.append(f"файл {info['megabytes']:.0f} МБ, предел {EXP['max_megabytes']} МБ")
    return info, Result(not problems,
                        pass_=f"out/{name}: {info['width']}×{info['height']}, {info['fps']:.0f} fps, "
                              f"{info['seconds']:.1f} с, {info['megabytes']:.1f} МБ",
                        fail=f"out/{name} не по формату", details=problems,
                        hint="размер и частоту кадров задают в <Composition>, длительность — в durationInFrames.")


@check.criterion("Ролик для Reels и TikTok")
def _main():
    info, res = _video_result("reel-01.mp4", "версию для Reels и TikTok")
    ctx["main"] = info
    return res


@check.criterion("Версия для Shorts")
def _shorts():
    info, res = _video_result("reel-01-shorts.mp4", "версию для Shorts")
    if not res.ok or not ctx.get("main"):
        return res
    main = ctx["main"]
    if abs(info["seconds"] - main["seconds"]) > 1 / EXP["fps"] + 0.01:
        return Result(False, fail="Версии разной длины",
                      details=[f"reel-01.mp4 длится {main['seconds']:.1f} с, reel-01-shorts.mp4 — {info['seconds']:.1f} с"],
                      hint="версии рендерят из одной композиции, меняется только параметр площадки.")
    same = (ctx["out"] / "reel-01.mp4").read_bytes() == (ctx["out"] / "reel-01-shorts.mp4").read_bytes()
    if same:
        return Result(False, fail="reel-01-shorts.mp4 совпадает с reel-01.mp4 байт в байт",
                      hint="у Shorts своя концовка: ссылка в описании там не кликается, зовут на страницу канала.")
    return res


@check.criterion("Субтитры .srt")
def _srt():
    path = ctx["srt"]
    if path is None:
        return Result(False, fail="Нет reel-01-shorts.srt в out/",
                      hint="файл субтитров для YouTube Studio выпускает рендер версии для Shorts.")
    cues, problems = read_srt(path)
    if not cues:
        return Result(False, fail=f"{path.relative_to(ctx['root'])}: реплик нет", details=problems)
    previous_end = 0
    for cue in cues:
        seconds = (cue["end"] - cue["start"]) / 1000
        if cue["start"] < previous_end:
            problems.append(f"реплика {cue['n']} начинается раньше, чем кончилась предыдущая")
        if not EXP["cue_min_seconds"] <= seconds <= EXP["cue_max_seconds"]:
            problems.append(f"реплика {cue['n']} длится {seconds:.1f} с, нужно от {EXP['cue_min_seconds']:.0f} "
                            f"до {EXP['cue_max_seconds']:.0f} с")
        if len(cue["lines"]) > EXP["cue_max_lines"]:
            problems.append(f"реплика {cue['n']}: {len(cue['lines'])} строки, на экране помещаются две")
        long = [line for line in cue["lines"] if len(line) > EXP["cue_max_chars"]]
        if long:
            problems.append(f"реплика {cue['n']}: строка длиннее {EXP['cue_max_chars']} знаков")
        previous_end = cue["end"]
    video = read_mp4(ctx["out"] / "reel-01-shorts.mp4")[0] if (ctx["out"] / "reel-01-shorts.mp4").exists() else None
    if video and cues[-1]["end"] / 1000 > video["seconds"] + 0.1:
        problems.append(f"последняя реплика кончается на {cues[-1]['end'] / 1000:.1f} с, а ролик {video['seconds']:.1f} с")
    gone = missing_numbers("\n".join(line for cue in cues for line in cue["lines"]))
    if gone:
        problems.append("в субтитрах нет чисел отчёта: " + ", ".join(fmt(n) for n in gone))
    return Result(not problems, pass_=f"{path.relative_to(ctx['root'])}: {len(cues)} реплик, формат и тайминг в порядке",
                  fail="Субтитры не по правилам", details=problems,
                  hint="одна реплика — одна строка сценария: 1–7 секунд, до двух строк по 42 знака.")


@check.criterion("Обложка")
def _cover():
    path = ctx["out"] / "cover.png"
    if not path.exists():
        return Result(False, fail="Нет out/cover.png", hint="обложку рендерят кадром: npx remotion still.")
    size = png_size(path)
    if size is None:
        return Result(False, fail="out/cover.png — не PNG")
    ok = size == (EXP["width"], EXP["height"])
    return Result(ok, pass_=f"out/cover.png: {size[0]}×{size[1]}",
                  fail=f"out/cover.png: {size[0]}×{size[1]}, нужен {EXP['width']}×{EXP['height']}",
                  hint="обложку снимают с той же композиции, что и ролик: размер совпадёт сам.")


if __name__ == "__main__":
    check.run()

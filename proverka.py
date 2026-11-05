#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""proverka.py — проверки облачной сессии Claude Code для ReelsRobot на заглушке (без кода продукта).

Запуск в облачной сессии из корня тестового репозитория:  python3 proverka.py
Печатает таблицу и пишет её в proverka-<дата>.md рядом. Ключей не читает и не печатает:
распознавание идёт через «сетевой секрет» окружения (ключ подставляет прокси Anthropic).

Проверки:
  1. железо и окружение: ядра, память, диск, ОС, Python, ffmpeg; кеш setup-скрипта;
  2. скорость: кодирование x264 veryfast 10 с синтетики 1080×1920 на 4 потоках и сложение кадров
     numpy (как в рендере) — те же замеры на маке дают пересчёт времени рендера на облако;
  3. сеть — только те адреса, куда ходит сам движок ReelsRobot (список — отчёт «доставка движка»):
     Wikimedia (поиск + превью), сайты шрифтов (только заголовки ответа, без скачивания),
     GitHub: файл релиза неподключённого репозитория (micromamba — его качает установщик движка),
     архив codeload неподключённого репозитория (документация: 403), raw.githubusercontent.com;
  4. ElevenLabs через сетевой секрет: 1 секунда тишины → код ответа (без ключа в запросе);
  5. Remotion: пустая сцена 90 кадров (браузер ставит setup-скрипт), время против мака, прозрачность
     кадра, достижимость запасного адреса браузера (Google) и шрифтов Google для сцен.
Хранилища (S3 и т. п.) не трогаются — авто-режим облака считает такие пробы выносом данных."""
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

UA = "ReelsRobot/1.0 (+https://site-reels.b-cdn.net/)"
ROWS = []


def row(group, what, result, note=""):
    ROWS.append((group, what, result, note))
    print(f"[{group}] {what}: {result} {note}", flush=True)


def http(url, method="GET", data=None, headers=None, limit=2_000_000, timeout=60):
    """(код, байт, секунд, ошибка). Тело читается не больше limit байт."""
    h = {"User-Agent": UA}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(limit) if method != "HEAD" else b""
            return r.status, len(body), round(time.time() - t, 2), ""
    except urllib.error.HTTPError as e:
        return e.code, 0, round(time.time() - t, 2), (e.read(300) or b"").decode("utf-8", "replace")[:160]
    except Exception as e:  # noqa: BLE001
        return None, 0, round(time.time() - t, 2), f"{type(e).__name__}: {e}"[:160]


def zhelezo():
    row("1", "ОС", platform.platform())
    row("1", "ядер", os.cpu_count())
    try:
        mem = open("/proc/meminfo").read().split("\n")[0]
        row("1", "память", mem.split(":")[1].strip())
    except OSError:
        pass
    du = shutil.disk_usage("/")
    row("1", "диск свободно", f"{du.free / 1e9:.1f} ГБ")
    row("1", "Python", sys.version.split()[0])
    ff = shutil.which("ffmpeg")
    row("1", "ffmpeg", subprocess.run([ff, "-version"], capture_output=True, text=True).stdout.split("\n")[0] if ff else "НЕТ")
    for p in ("/opt/rr-stub/setup-stamp", "/opt/rr-stub/setup.log"):
        if os.path.isfile(p):
            row("1", p, open(p).read().strip().replace("\n", " | "))
        else:
            row("1", p, "нет (setup-скрипт не отработал)")


def skorost():
    ff = shutil.which("ffmpeg")
    if ff:
        t = time.time()
        r = subprocess.run([ff, "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=30:d=10",
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-threads", "4",
                            "-f", "null", "-"], capture_output=True, text=True)
        row("2", "x264 veryfast, 10 с 1080×1920, 4 потока", f"{time.time() - t:.1f} с",
            "" if r.returncode == 0 else r.stderr[:120])
    try:
        import numpy as np
        a = np.random.rand(1920, 1080, 3).astype(np.float32)
        b = np.random.rand(1920, 1080, 4).astype(np.float32)
        t = time.time()
        for _ in range(60):                       # 60 сложений слоя RGBA поверх кадра — как в рендере
            a *= 1.0 - b[..., 3:4]
            a += b[..., :3]
        row("2", "numpy: 60 сложений слоя 1080×1920", f"{time.time() - t:.2f} с")
    except ImportError:
        row("2", "numpy", "НЕТ")


def set_():
    checks = [
        ("шрифт Coolvetica (dl.dafont.com, только заголовки)", "https://dl.dafont.com/dl/?f=coolvetica", "HEAD"),
        ("шрифт Bebas (ofont.ru, только заголовки)", "https://ofont.ru/view/4643", "HEAD"),
        ("шрифт Jun (befonts.com, только заголовки)", "https://befonts.com/wp-content/uploads/2024/12/jun-regular.otf", "HEAD"),
        ("GitHub raw (публичный файл)", "https://raw.githubusercontent.com/mamba-org/micromamba-releases/main/README.md", "GET"),
        ("GitHub: файл релиза неподключённого репозитория (micromamba)", "https://github.com/mamba-org/micromamba-releases/releases/download/2.9.0-0/micromamba-linux-64", "GET"),
        ("GitHub: codeload неподключённого репозитория (ожидаем 403)", "https://codeload.github.com/remotion-dev/skills/tar.gz/refs/heads/main", "GET"),
        ("PyPI (простой индекс)", "https://pypi.org/simple/numpy/", "GET"),
    ]
    # Wikimedia — как движок (engine/tools/inserts.py): поиск файла с превью, затем само превью
    api = ("https://commons.wikimedia.org/w/api.php?action=query&format=json&generator=search"
           "&gsrsearch=Barcelona&gsrnamespace=6&gsrlimit=1&prop=imageinfo&iiprop=url&iiurlwidth=120")
    h = {"User-Agent": UA}
    try:
        with urllib.request.urlopen(urllib.request.Request(api, headers=h), timeout=60) as r:
            pages = json.load(r).get("query", {}).get("pages", {})
        thumb = next(iter(pages.values()))["imageinfo"][0]["thumburl"]
        row("3", "Wikimedia API (поиск вставок)", 200, thumb.split("/")[2])
        code, n, sec, err = http(thumb, limit=200_000)
        row("3", "Wikimedia файл (превью)", code, f"{n} байт, {sec} с {err}")
    except Exception as e:  # noqa: BLE001
        row("3", "Wikimedia API (поиск вставок)", "ошибка", f"{type(e).__name__}: {e}"[:160])
    for name, url, m in checks:
        code, n, sec, err = http(url, method=m, limit=200_000)
        row("3", name, code, f"{n} байт, {sec} с {err}")


def elevenlabs():
    ff = shutil.which("ffmpeg")
    if not ff:
        row("4", "ElevenLabs", "пропущено (нет ffmpeg)")
        return
    tmp = tempfile.mkdtemp()
    mp3 = os.path.join(tmp, "silence.mp3")
    subprocess.run([ff, "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "1", "-q:a", "9", mp3], check=False)
    # multipart вручную: файл + model_id; заголовка с ключом НЕТ — его подставит прокси
    bnd = "rrstub7c1"
    body = (f"--{bnd}\r\nContent-Disposition: form-data; name=\"model_id\"\r\n\r\nscribe_v2\r\n"
            f"--{bnd}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"silence.mp3\"\r\n"
            f"Content-Type: audio/mpeg\r\n\r\n").encode() + open(mp3, "rb").read() + f"\r\n--{bnd}--\r\n".encode()
    code, n, sec, err = http("https://api.elevenlabs.io/v1/speech-to-text", "POST", body,
                             {"Content-Type": f"multipart/form-data; boundary={bnd}"}, timeout=90)
    verdict = {200: "ключ подставлен, распознавание прошло", 401: "ключа нет (секрет не настроен или не тот заголовок)",
               403: "ключ без права Speech to Text или блок"}.get(code, "")
    row("4", "ElevenLabs Speech-to-Text через сетевой секрет", code, f"{verdict} {sec} с {err[:80]}")
    row("4", "ключ в окружении сессии виден?", "да — ПЛОХО" if any("ELEVEN" in k for k in os.environ) else "нет — хорошо")


SCENE = """import React from 'react';
import {AbsoluteFill, Composition, interpolate, spring, useCurrentFrame, useVideoConfig, registerRoot} from 'remotion';
const Proba: React.FC = () => {
  const frame = useCurrentFrame(); const {fps} = useVideoConfig();
  const s = spring({frame, fps, config: {damping: 200}}); const y = interpolate(s, [0, 1], [200, 0]);
  return (<AbsoluteFill style={{backgroundColor: 'transparent', justifyContent: 'center', alignItems: 'center'}}>
    <div style={{transform: `translateY(${y}px)`, opacity: s, padding: '40px 60px', borderRadius: 48,
      background: 'rgba(255,255,255,0.18)', backdropFilter: 'blur(24px)', color: 'white', fontSize: 96,
      fontFamily: 'sans-serif', fontWeight: 700}}>ReelsRobot {frame}</div></AbsoluteFill>);
};
const Root: React.FC = () => (<Composition id="proba" component={Proba} durationInFrames={90} fps={30} width={1080} height={1920} />);
registerRoot(Root);
"""


def remotion():
    """Пустая сцена Remotion — так же, как движок рисует вставки (glass/remotion.py): кадры PNG
    последовательностью. Мак (M1 Pro, занят ВМ): 90 кадров за 4–6 с вместе со сборкой."""
    d = "/opt/rr-stub/remotion"
    if not os.path.isdir(os.path.join(d, "node_modules")):
        row("5", "Remotion", "нет node_modules — setup-скрипт не поставил (см. setup.log)")
        return
    os.makedirs(os.path.join(d, "src"), exist_ok=True)
    open(os.path.join(d, "src", "index.tsx"), "w").write(SCENE)
    out = tempfile.mkdtemp(prefix="remotion-proba-")
    for conc in (None, 2):
        t = time.time()
        cmd = ["npx", "--no-install", "remotion", "render", "src/index.tsx", "proba", out, "--sequence",
               "--image-format=png", "--log=error"] + ([f"--concurrency={conc}"] if conc else [])
        r = subprocess.run(cmd, cwd=d, capture_output=True, text=True)
        n = len([f for f in os.listdir(out) if f.endswith(".png")])
        row("5", f"Remotion 90 кадров 1080×1920, конкурентность {conc or 'по умолчанию'}",
            f"{time.time() - t:.1f} с, кадров {n}", "" if r.returncode == 0 else (r.stderr or r.stdout)[-160:])
    try:
        from PIL import Image
        f = sorted(os.listdir(out))[45]
        im = Image.open(os.path.join(out, f))
        row("5", "кадр PNG с прозрачностью", im.mode, "RGBA — хорошо" if im.mode == "RGBA" else "")
    except Exception as e:  # noqa: BLE001
        row("5", "кадр PNG", "ошибка", str(e)[:120])
    code, n, sec, err = http("https://storage.googleapis.com/chrome-for-testing-public/149.0.7790.0/linux64/"
                             "chrome-headless-shell-linux64.zip", method="HEAD")
    row("5", "запасной адрес браузера (Google, Chrome for Testing)", code, f"{sec} с {err}")
    code, n, sec, err = http("https://fonts.gstatic.com/s/inter/v13/UcCO3FwrK3iLTeHuS_fvQtMwCp50KnMw2boKoduKmMEVuLyfAZ9hiA.woff2",
                             limit=100_000)
    row("5", "fonts.gstatic.com (@remotion/google-fonts в сценах)", code, f"{n} байт {err}")


def main():
    t0 = time.time()
    zhelezo()
    skorost()
    set_()
    elevenlabs()
    remotion()
    out = f"proverka-{time.strftime('%Y%m%d-%H%M')}.md"
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# Проверка облачной сессии ReelsRobot (заглушка), {time.strftime('%d.%m.%Y %H:%M UTC', time.gmtime())}\n\n")
        f.write("| Группа | Что | Итог | Заметка |\n|---|---|---|---|\n")
        for g, w, r, n in ROWS:
            f.write(f"| {g} | {w} | {r} | {str(n).replace('|', '/')} |\n")
        f.write(f"\nВсего {time.time() - t0:.0f} с.\n")
    print(f"\nотчёт: {out}")


if __name__ == "__main__":
    main()

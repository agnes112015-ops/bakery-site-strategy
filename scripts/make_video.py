"""Build video/presentation.mp4 from video/script.json.

Steps: slide HTML -> PNG (headless Edge/Chrome), narration -> WAV (Windows System.Speech,
'Microsoft Heami Desktop'), ffmpeg segments (audio + 0.6s) -> concat, captions.vtt.
Run: PYTHONIOENCODING=utf-8 python scripts/make_video.py
"""
import html, json, os, re, shutil, subprocess, time, wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VID = ROOT / "video"
SLIDES, AUDIO, SEG = VID / "slides", VID / "audio", VID / "segments"
PAD = 0.6
RATE = 2

BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

CSS = """
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1920px;height:1080px;overflow:hidden}
body{font-family:'Pretendard','Malgun Gothic',sans-serif;background:#F5F3FF;color:#1F1235;position:relative}
.bar{position:absolute;left:0;top:0;width:1920px;height:18px;background:linear-gradient(90deg,#4C1D95,#7C3AED)}
.wrap{padding:110px 130px 0 130px}
.kicker{font-size:34px;font-weight:700;color:#7C3AED;letter-spacing:2px}
h1{font-size:84px;font-weight:800;line-height:1.2;margin:18px 0 56px;color:#2E1065}
.card{background:#fff;border-radius:28px;box-shadow:0 10px 40px rgba(76,29,149,.12);padding:44px 56px;margin-bottom:28px}
ul{list-style:none}
li{font-size:46px;line-height:1.45;padding:14px 0 14px 46px;position:relative;font-weight:500}
li:before{content:'';position:absolute;left:0;top:34px;width:20px;height:20px;border-radius:50%;background:#7C3AED}
.stats{display:flex;gap:36px;margin-top:10px}
.stat{flex:1;background:#fff;border-radius:28px;box-shadow:0 10px 40px rgba(76,29,149,.12);padding:46px 40px;border-top:12px solid #7C3AED}
.stat .n{font-size:104px;font-weight:800;color:#4C1D95}
.stat .l{font-size:36px;color:#4B4560;margin-top:12px}
.pal{display:flex;gap:28px;margin-top:10px}
.sw{flex:1;background:#fff;border-radius:24px;overflow:hidden;box-shadow:0 10px 40px rgba(76,29,149,.12)}
.sw .c{height:230px}
.sw .t{font-size:32px;padding:20px 22px;font-weight:700}
.sw .h{font-size:26px;color:#6B6480;padding:0 22px 22px}
.foot{position:absolute;left:130px;right:130px;bottom:44px;display:flex;justify-content:space-between;font-size:26px;color:#7C6FA0}
"""


def slide_html(s, total):
    parts = [f'<div class="bar"></div><div class="wrap">',
             f'<div class="kicker">{s["slide"]:02d} / {total:02d} · 베이커리 1호점 출점 제안</div>',
             f'<h1>{html.escape(s["title"])}</h1>']
    if s.get("bullets"):
        parts.append('<div class="card"><ul>' + "".join(f"<li>{html.escape(b)}</li>" for b in s["bullets"]) + "</ul></div>")
    if s.get("stats"):
        parts.append('<div class="stats">' + "".join(
            f'<div class="stat"><div class="n">{html.escape(n)}</div><div class="l">{html.escape(l)}</div></div>'
            for n, l in s["stats"]) + "</div>")
    if s.get("palette"):
        parts.append('<div class="pal">' + "".join(
            f'<div class="sw"><div class="c" style="background:{h}"></div><div class="t">{html.escape(n)}</div><div class="h">{h}</div></div>'
            for n, h in s["palette"]) + "</div>")
    parts.append("</div>")
    parts.append('<div class="foot"><span>출처: 서울 열린데이터광장 상권분석서비스 · DART 감사보고서</span><span>예측·계획 수치는 가정</span></div>')
    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            '<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css">'
            f"<style>{CSS}</style></head><body>" + "".join(parts) + "</body></html>")


def render_png(browser, html_path, png_path):
    tmp_profile = VID / f"_profile_{png_path.stem}"
    subprocess.run([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    f"--user-data-dir={tmp_profile}", "--virtual-time-budget=4000",
                    "--window-size=1920,1080", f"--screenshot={png_path}", html_path.as_uri()],
                   check=True, capture_output=True, timeout=120)
    # msedge.exe may hand off to a running instance and return before the PNG is written
    for _ in range(120):
        if png_path.exists() and png_path.stat().st_size > 0:
            time.sleep(0.5)
            return
        time.sleep(0.25)
    raise RuntimeError(f"screenshot not written: {png_path}")


def tts_all(slides):
    ps_lines = ["Add-Type -AssemblyName System.Speech",
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer",
                "$s.SelectVoice('Microsoft Heami Desktop')", f"$s.Rate = {RATE}"]
    for s in slides:
        txt = AUDIO / f"{s['slide']:02d}.txt"
        txt.write_text(s["narration"], encoding="utf-8")
        wav = AUDIO / f"{s['slide']:02d}.wav"
        ps_lines += [f"$s.SetOutputToWaveFile('{wav}')",
                     f"$s.Speak([IO.File]::ReadAllText('{txt}', [Text.Encoding]::UTF8))"]
    ps_lines.append("$s.Dispose()")
    ps = AUDIO / "tts.ps1"
    ps.write_text("\n".join(ps_lines), encoding="utf-8-sig")
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps)], check=True)


def wav_len(p):
    with wave.open(str(p)) as w:
        return w.getnframes() / w.getframerate()


def ts(t):
    h, r = divmod(t, 3600); m, s = divmod(r, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}"


def main():
    slides = json.loads((VID / "script.json").read_text(encoding="utf-8"))
    for d in (SLIDES, AUDIO, SEG):
        d.mkdir(parents=True, exist_ok=True)
    browser = next(b for b in BROWSERS if os.path.exists(b))
    for s in slides:
        h = SLIDES / f"{s['slide']:02d}.html"
        h.write_text(slide_html(s, len(slides)), encoding="utf-8")
        render_png(browser, h, SLIDES / f"{s['slide']:02d}.png")
        shutil.rmtree(VID / f"_profile_{s['slide']:02d}", ignore_errors=True)
        assert (SLIDES / f"{s['slide']:02d}.png").exists(), "screenshot failed"
    tts_all(slides)

    vtt, t0, concat = ["WEBVTT", ""], 0.0, []
    for s in slides:
        n = f"{s['slide']:02d}"
        alen = wav_len(AUDIO / f"{n}.wav")
        dur = alen + PAD
        seg = SEG / f"{n}.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", "30",
                        "-i", str(SLIDES / f"{n}.png"), "-i", str(AUDIO / f"{n}.wav"),
                        "-af", f"apad=pad_dur={PAD}", "-t", f"{dur:.3f}",
                        "-vf", "scale=1920:1080,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast",
                        "-tune", "stillimage", "-r", "30", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
                        str(seg)], check=True)
        concat.append(f"file '{seg.as_posix()}'")
        # captions: split by sentence, time proportional to character count
        sents = [x.strip() for x in re.split(r"(?<=[.?!])\s+", s["narration"]) if x.strip()]
        total = sum(len(x) for x in sents)
        t = t0
        for x in sents:
            d = alen * len(x) / total
            vtt += [f"{ts(t)} --> {ts(t + d)}", x, ""]
            t += d
        t0 += dur
    (SEG / "list.txt").write_text("\n".join(concat), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(SEG / "list.txt"), "-c", "copy", "-movflags", "+faststart",
                    str(VID / "presentation.mp4")], check=True)
    (VID / "captions.vtt").write_text("\n".join(vtt), encoding="utf-8")
    print(f"done: {VID / 'presentation.mp4'}  expected {t0:.1f}s")


if __name__ == "__main__":
    main()

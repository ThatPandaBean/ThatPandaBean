#!/usr/bin/env python3
"""Renders the profile cards into cards/.

    python build_cards.py            animated cards -> cards/
    STATIC=1 python build_cards.py   final frame, no animation -> cards-static/ (for screenshots)

Data comes from data/contributions.json and data/repos.jsonl (refreshed by fetch_data.sh).
Also writes preview.html, which shows the README's layout using the freshly rendered cards.

Motion rules (cards are shown through <img>, so CSS keyframes and SMIL are all that runs):
  - Entrances are CSS keyframes whose base style is the final state, so turning them off
    (STATIC=1, or prefers-reduced-motion) leaves the finished card.
  - SMIL loops and count-ups cannot be switched off by CSS, so they live in class="smil"
    elements that are hidden instead. Anything they replace is class="still" and is hidden
    only while motion is allowed.
"""
import base64, calendar, html, json, math, os, subprocess, sys, tempfile
from datetime import date
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).parent
STATIC = os.environ.get("STATIC") == "1"
OUT = ROOT / ("cards-static" if STATIC else "cards")

# ---- edit these ----------------------------------------------------------
HANDLE = "ThatPandaBean"
EYEBROW = "ECONOMICS STUDENT"
TAGLINE = "Economics student with a data science minor, and a past dabbler in psychology. I build small web projects."
PORTRAIT = ROOT / "data/avatar.jpg"  # set to None for no portrait
# Paper, ink and one flat accent. No gradients, no glow.
PAPER, INK, INK2, MUTED, LINE, STONE = "#f3f3f1", "#111111", "#3a3a3c", "#6e6e73", "#dcdcd7", "#c9c9c4"
ACCENT = "#1f7a4d"  # bamboo green: best month, graph, pills
FONTS = {  # key: (file in fonts/, variable-font axes to pin or None for a static font)
    "head": ("Newsreader[opsz,wght].ttf", {"wght": 500, "opsz": 60}),
    "body": ("Inter[opsz,wght].ttf", {"wght": 400, "opsz": 14}),
    "mono": ("DMMono-Regular.ttf", None),
    "monob": ("DMMono-Medium.ttf", None),
}
LANG = {"TypeScript": "#3178c6", "HTML": "#e34c26", "JavaScript": "#f1e05a", "Python": "#3572a5"}
# ---------------------------------------------------------------------------

W = 830
FAMILY = {k: f"f-{k},system-ui,sans-serif" for k in FONTS}
FAMILY["head"] = "f-head,Georgia,serif"
FAMILY["mono"] = "f-mono,ui-monospace,monospace"
FAMILY["monob"] = "f-monob,ui-monospace,monospace"


def mix(a, b, t):
    """Blend hex colour a toward b by t (0..1)."""
    pa, pb = (int(a[i:i + 2], 16) for i in (1, 3, 5)), (int(b[i:i + 2], 16) for i in (1, 3, 5))
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(pa, pb))


# ---- fonts -----------------------------------------------------------------
_tmp = tempfile.TemporaryDirectory()
_fonts = {}


def font(key):
    """Static instance of the font, kept in memory and saved once for pyftsubset."""
    if key not in _fonts:
        file, axes = FONTS[key]
        t = TTFont(ROOT / "fonts" / file)
        if axes:
            t = instantiateVariableFont(t, axes)
        t.save(Path(_tmp.name) / f"{key}.ttf")
        _fonts[key] = t
    return _fonts[key]


def width(key, s, size):
    t = font(key)
    cmap, hm = t.getBestCmap(), t["hmtx"]
    return sum(hm[cmap.get(ord(c), ".notdef")][0] for c in s) * size / t["head"].unitsPerEm


def wrap(key, s, size, maxw, max_lines=2):
    lines, cur = [], ""
    for w in s.split():
        if cur and width(key, cur + " " + w, size) > maxw:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(" ,.") + "â€¦"
    return lines


def woff_b64(key, chars):
    """Subset to just these characters with pyftsubset (fontTools.subset), as a base64 WOFF."""
    d = Path(_tmp.name)
    (d / f"{key}.txt").write_text("".join(sorted(chars | {" "})), encoding="utf-8")
    subprocess.run([sys.executable, "-m", "fontTools.subset", str(d / f"{key}.ttf"),
                    f"--text-file={d / f'{key}.txt'}", "--flavor=woff", "--layout-features=kern",
                    "--no-hinting", f"--output-file={d / f'{key}.woff'}"], check=True)
    return base64.b64encode((d / f"{key}.woff").read_bytes()).decode()


# ---- css --------------------------------------------------------------------
ANIM = f"""
@keyframes rise{{from{{opacity:0;transform:translateY(10px)}}}}
@keyframes grow{{from{{transform:scaleY(0)}}}}
@keyframes growx{{from{{transform:scaleX(0)}}}}
@keyframes pop{{from{{opacity:0;transform:scale(.6)}}}}
@keyframes swing{{from{{opacity:0;transform:translateY(26px) rotate(-4deg)}}
  60%{{opacity:1;transform:translateY(-5px) rotate(.8deg)}}80%{{transform:translateY(1px) rotate(-.2deg)}}}}
.a{{animation:rise .7s cubic-bezier(.2,.7,.2,1) var(--d,0s) both}}
.p{{transform-box:fill-box;transform-origin:50% 50%;animation:pop .6s cubic-bezier(.3,1.6,.5,1) var(--d,0s) both}}
.g{{transform-box:fill-box;transform-origin:50% 100%;animation:grow .9s cubic-bezier(.2,.7,.2,1) var(--d,0s) both}}
.gx{{transform-box:fill-box;transform-origin:0 50%;animation:growx .8s cubic-bezier(.2,.7,.2,1) var(--d,0s) both}}
.sw{{transform-origin:50% 100%;animation:swing .95s cubic-bezier(.2,.7,.2,1) var(--d,0s) both}}
@media (prefers-reduced-motion:no-preference){{.still{{display:none}}}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}.smil{{display:none}}.shine{{fill:{INK}!important}}}}
"""
STATIC_CSS = f".smil{{display:none}}.shine{{fill:{INK}}}"


class Card:
    def __init__(self, name, h, label, t0=0.0, w=W, fill=PAPER, stroke=LINE, clip=False):
        self.name, self.w, self.h, self.label, self.t0 = name, w, h, label, t0
        self.fill, self.stroke = fill, stroke
        self.body, self.chars = [], {k: set() for k in FONTS}

    def A(self, d=0.0, cls="a"):
        """Class + delay attributes that play an entrance animation (nothing in STATIC mode)."""
        return "" if STATIC else f' class="{cls}" style="--d:{self.t0 + d:.2f}s"'

    def add(self, s):
        self.body.append(s)

    def attrs(self, x, y, key, size, fill, anchor="start", ls=0):
        return (f'x="{x:.1f}" y="{y:.1f}" font-family="{FAMILY[key]}" font-size="{size}" fill="{fill}" '
                f'text-anchor="{anchor}"' + (f' letter-spacing="{ls}"' if ls else ""))

    def text(self, x, y, s, key, size, fill, anchor="start", d=0.0, ls=0, cls="a"):
        self.chars[key].update(s)
        self.add(f'<text {self.attrs(x, y, key, size, fill, anchor, ls)}{self.A(d, cls)}>{html.escape(s)}</text>')

    def count(self, x, y, n, key, size, fill, d=0.0):
        """A number that counts up from 0 (SMIL set frames). The still text is the reduced-motion and STATIC form."""
        self.chars[key].update("0123456789")
        at = self.attrs(x, y, key, size, fill)
        self.add(f'<text {at} class="still">{n}</text>')
        if STATIC:
            return
        steps = list(range(n + 1)) if n <= 18 else [round(n * i / 18) for i in range(19)]
        dt, t = 0.9 / len(steps), self.t0 + d
        for i, v in enumerate(steps):
            last = i == len(steps) - 1
            hold = ' fill="freeze"' if last else f' end="{t + (i + 1) * dt:.2f}s"'  # only the final number stays
            self.add(f'<text {at} class="smil" visibility="hidden">{v}'
                     f'<set attributeName="visibility" to="visible" begin="{t + i * dt:.2f}s"{hold}/></text>')

    def svg(self):
        faces = "".join(
            f"@font-face{{font-family:f-{k};src:url(data:font/woff;base64,{woff_b64(k, c)}) format('woff')}}"
            for k, c in self.chars.items() if c)
        css = faces + (STATIC_CSS if STATIC else ANIM)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}" role="img" aria-label="{html.escape(self.label)}">'
            f'<title>{html.escape(self.label)}</title><style>{css}</style>'
            f'<defs><clipPath id="card"><rect width="{self.w}" height="{self.h}" rx="14"/></clipPath></defs>'
            f'<rect x=".5" y=".5" width="{self.w - 1}" height="{self.h - 1}" rx="14" fill="{self.fill}" stroke="{self.stroke}"/>'
            + "".join(self.body) + "</svg>")


def pulse(cx, cy, r0, r1, colour, dur="2.4s"):
    """Decorative looping ring (SMIL), hidden under prefers-reduced-motion and in STATIC mode."""
    return (f'<circle class="smil" cx="{cx}" cy="{cy}" r="{r0}" fill="{colour}" opacity=".4">'
            f'<animate attributeName="r" values="{r0};{r1};{r0}" dur="{dur}" repeatCount="indefinite"/>'
            f'<animate attributeName="opacity" values=".4;0;.4" dur="{dur}" repeatCount="indefinite"/></circle>')


def arrow(x, y, colour, nudge=True):
    """Up-right arrow. The still copy stays put; the SMIL copy nudges and replaces it while motion is allowed."""
    d = f'd="M0 14L14 0M4 0H14V10" fill="none" stroke="{colour}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'
    s = f'<path class="still" {d} transform="translate({x} {y})"/>'
    if nudge and not STATIC:
        s += (f'<path class="smil" {d} transform="translate({x} {y})"><animateTransform attributeName="transform" '
              f'type="translate" values="{x} {y};{x + 3} {y - 3};{x} {y}" dur="1.8s" repeatCount="indefinite"/></path>')
    return s


def star(cx, cy, r, colour):
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.42
        pts.append(f"{cx + rr * math.cos(a):.1f},{cy + rr * math.sin(a):.1f}")
    return f'<polygon points="{" ".join(pts)}" fill="{colour}"/>'


# ---- data -------------------------------------------------------------------
days = [(date.fromisoformat(d["date"]), d["count"])
        for d in json.loads((ROOT / "data/contributions.json").read_text(encoding="utf-8-sig"))["days"]]
rows = [json.loads(l) for l in (ROOT / "data/repos.jsonl").read_text(encoding="utf-8-sig").splitlines() if l.strip()]
public_repos, repos = rows[0]["public_repos"], rows[1:]


def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


# ---- cards ------------------------------------------------------------------
def hero():
    c = Card("hero", 250, f"{HANDLE}: {TAGLINE}")
    text_w = 560 if PORTRAIT else 700
    c.add(f'<rect x="48" y="54" width="9" height="9" fill="{ACCENT}"{c.A(0.0, "p")}/>')
    c.text(66, 63, EYEBROW, "mono", 12, MUTED, d=0.05, ls=1.6)
    # a green shine crosses the name every few seconds; the gradient starts off to the left of the text
    nw = width("head", HANDLE, 64)
    if not STATIC:
        c.add(f'<defs><linearGradient id="shine" x1="0" x2="1" y1="0" y2="0" gradientTransform="translate(-1 0)">'
              f'<stop offset="0" stop-color="{INK}"/><stop offset=".42" stop-color="{INK}"/>'
              f'<stop offset=".5" stop-color="{ACCENT}"/><stop offset=".58" stop-color="{INK}"/>'
              f'<stop offset="1" stop-color="{INK}"/>'
              f'<animateTransform attributeName="gradientTransform" type="translate" values="-1 0;-1 0;1 0;1 0" '
              f'keyTimes="0;.15;.4;1" dur="7s" begin="1.2s" repeatCount="indefinite"/></linearGradient></defs>')
    c.chars["head"].update(HANDLE)
    c.add(f'<text {c.attrs(46, 132, "head", 64, "url(#shine)" if not STATIC else INK)}{c.A(0.15, "a shine")}>{HANDLE}</text>')
    for i, line in enumerate(wrap("body", TAGLINE, 20, text_w)):
        c.text(48, 172 + i * 27, line, "body", 20, INK2, d=0.35 + i * 0.1)
    c.add(f'<rect x="48" y="218" width="56" height="4" rx="2" fill="{ACCENT}"{c.A(0.7, "gx")}/>')
    if PORTRAIT and PORTRAIT.exists():
        cx, cy, r = W - 48 - 78, 125, 68
        img = base64.b64encode(PORTRAIT.read_bytes()).decode()
        c.add(f'<g{c.A(0.2, "p")}><clipPath id="av"><circle cx="{cx}" cy="{cy}" r="{r}"/></clipPath>'
              f'<circle cx="{cx}" cy="{cy}" r="{r + 9}" fill="none" stroke="{INK}" stroke-width="1.5"/>'
              f'<image href="data:image/jpeg;base64,{img}" x="{cx - r}" y="{cy - r}" width="{2 * r}" height="{2 * r}" '
              f'clip-path="url(#av)" preserveAspectRatio="xMidYMid slice"/></g>'
              f'<circle class="smil" cx="{cx}" cy="{cy}" r="{r + 9}" fill="none" stroke="{ACCENT}" stroke-width="3.5" '
              f'stroke-dasharray="16 340" stroke-linecap="round"><animateTransform attributeName="transform" type="rotate" '
              f'from="0 {cx} {cy}" to="360 {cx} {cy}" dur="8s" repeatCount="indefinite"/></circle>')
    return c


def tile(i, label, title, count, suffix, sub, fill, fg, sub_fg):
    """Flat colour tile. With a count, the headline is that number (counting up) plus the suffix."""
    stroke = LINE if fill == PAPER else fill
    shown = f"{count}{suffix}" if count is not None else title
    c = Card(f"tile-{i}", 130, f"{shown}: {sub}", t0=0.45 + 0.14 * (i - 1), w=270, fill=fill, stroke=stroke)
    body = Card("x", 0, "")  # collects the swinging content, then wrapped in one group below
    body.t0, body.chars = c.t0, c.chars
    body.add(f'<rect x="22" y="26" width="8" height="8" fill="{fg}"/>')
    body.text(38, 34, label, "mono", 11, sub_fg, ls=1.5, cls="")
    if count is None:
        body.text(22, 92, title, "head", 34, fg, cls="")
    else:
        body.count(22, 92, count, "head", 34, fg, d=0.5)
        body.text(22 + width("head", str(count), 34) + 8, 92, suffix, "head", 34, fg, cls="")
    body.text(22, 114, sub, "body", 13, sub_fg, cls="")
    c.add(f'<g{c.A(0.0, "sw")}>' + "".join(body.body).replace(' class=""', "") + arrow(232, 24, fg) + "</g>")
    if not STATIC:  # a pale band sweeps across the tile every few seconds
        t = c.t0 + 1.6
        c.add(f'<g class="smil" clip-path="url(#card)"><g><rect x="-70" y="-10" width="46" height="150" fill="#fff" '
              f'opacity="{.16 if fill != PAPER else .0}" transform="skewX(-18)"/>'
              f'<animateTransform attributeName="transform" type="translate" values="0 0;0 0;380 0;380 0" '
              f'keyTimes="0;.001;.35;1" dur="5.5s" begin="{t:.2f}s" repeatCount="indefinite"/></g></g>')
        c.add(pulse(26, 30, 4, 9, fg, "2.6s"))
    return c


def monthly():
    last = days[-1][0]
    months, (y, m) = [], (last.year, last.month)
    for _ in range(12):
        months.append((y, m))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    months.reverse()
    window = [(d, n) for d, n in days if (d.year, d.month) in months]
    sums = {ym: sum(n for d, n in window if (d.year, d.month) == ym) for ym in months}
    return window, sums


def activity():
    window, sums = monthly()
    total, ymax = sum(sums.values()), max(max(sums.values()), 1)
    vals = list(sums.values())
    best = max(range(12), key=lambda i: (vals[i], i)) if total else -1  # latest month wins ties
    c = Card("activity", 346, f"Contributions per month, {total} in the last 12 months", t0=1.0)
    c.text(48, 60, "Contributions per month", "head", 28, INK)
    c.text(48, 82, f"{plural(total, 'contribution')} in the last 12 months", "body", 13, MUTED, d=0.05)
    x0, x1, base, top = 48, 782, 214, 122
    slot, bw = (x1 - x0) / 12, 34
    c.add(f'<line x1="{x0}" x2="{x1}" y1="{base}" y2="{base}" stroke="{LINE}"/>')
    for i, ((y, m), v) in enumerate(sums.items()):
        cx, h, d = x0 + slot * (i + 0.5), max(3, (base - top) * v / ymax) if v else 3, 0.25 + i * 0.06
        colour = ACCENT if i == best else (STONE if v else LINE)
        c.add(f'<rect x="{cx - bw / 2:.1f}" y="{base - h:.1f}" width="{bw}" height="{h:.1f}" rx="4" fill="{colour}"{c.A(d, "g")}/>')
        if v and i == best:  # the best month's number pops in once its bar has grown
            c.text(cx, base - h - 9, str(v), "monob", 15, ACCENT, "middle", 1.2, cls="p")
        elif v:
            c.text(cx, base - h - 9, str(v), "mono", 11, MUTED, "middle", d + 0.5)
        c.text(cx, base + 22, calendar.month_abbr[m].upper(), "monob" if i == best else "mono", 11,
               INK if i == best else MUTED, "middle", d, ls=0.8)
    c.add(f'<line x1="{x0}" x2="{x1}" y1="262" y2="262" stroke="{LINE}"/>')

    i, streak = len(days) - 1, 0  # a zero today does not break the streak yet
    i -= days[i][1] == 0
    while i >= 0 and days[i][1] > 0:
        streak, i = streak + 1, i - 1
    active = sum(1 for _, n in window if n)
    best_d, best_n = max(reversed(window), key=lambda t: t[1])  # latest day wins ties
    for k, (label, num, unit, text, note) in enumerate([
            ("CURRENT STREAK", streak, "day" + ("" if streak == 1 else "s"), None, ""),
            ("ACTIVE DAYS", active, "", None, "in 12 months"),
            ("BUSIEST DAY", None, "", f"{calendar.month_abbr[best_d.month]} {best_d.day}" if best_n else "None yet",
             plural(best_n, "contribution") if best_n else "")]):
        x, d = 48 + k * 252, 0.9 + k * 0.12
        c.text(x, 288, label, "mono", 11, MUTED, d=d, ls=1.5)
        if num is not None:
            c.count(x, 324, num, "head", 36, INK, d=d + 0.1)
            vw = width("head", str(num), 36)
        else:
            c.text(x, 324, text, "head", 36, INK, d=d + 0.1)
            vw = width("head", text, 36)
        tail = unit or note
        if tail:
            c.text(x + vw + 9, 324, tail, "body", 14, MUTED, d=d + 0.15)
    return c


def repo_card(i, r):
    c = Card(f"repo-{r['name']}", 156, f"{r['name']}: {r['description'] or ''}", t0=1.7 + 0.3 * i)
    c.add(f'<g{c.A()}><rect x="30" y="31" width="15" height="19" rx="2.5" fill="none" stroke="{MUTED}" stroke-width="1.8"/>'
          f'<path d="M36 31v19" stroke="{MUTED}" stroke-width="1.8"/></g>')
    c.text(58, 50, r["name"], "head", 28, INK, d=0.05)
    if r["homepage"]:
        pw = width("monob", "LIVE DEMO", 11) + 9 * 1.2 + 52
        px = W - 28 - pw
        c.add(f'<g{c.A(0.1)}><rect x="{px:.1f}" y="28" width="{pw:.1f}" height="28" rx="14" fill="{ACCENT}"/>'
              f'<path d="M0 8L8 0M2.5 0H8V5.5" transform="translate({px + pw - 26:.1f} 36)" fill="none" stroke="#fff" '
              f'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></g>')
        c.text(px + 16, 46, "LIVE DEMO", "monob", 11, "#ffffff", d=0.1, ls=1.2)
    for j, line in enumerate(wrap("body", r["description"] or "No description yet.", 14, W - 56)):
        c.text(30, 84 + j * 22, line, "body", 14, INK2, d=0.15 + j * 0.08)
    x, d, y = 30, 0.3, 132
    if r["language"]:
        col = LANG.get(r["language"], MUTED)
        c.add(pulse(35, y - 4, 5, 10, col))
        c.add(f'<circle cx="35" cy="{y - 4}" r="5" fill="{col}"{c.A(d, "p")}/>')
        c.text(48, y, r["language"], "mono", 12, MUTED, d=d)
        x = 48 + width("mono", r["language"], 12) + 24
    c.add(f'<g{c.A(d)}>{star(x + 6, y - 5, 7, MUTED)}</g>')
    c.text(x + 18, y, str(r["stars"]), "mono", 12, MUTED, d=d)
    x += 18 + width("mono", str(r["stars"]), 12) + 24
    p = date.fromisoformat(r["pushed"][:10])
    c.text(x, y, f"Updated {calendar.month_abbr[p.month]} {p.year}", "mono", 12, MUTED, d=d)
    return c


def graph():
    offset = (days[0][0].weekday() + 1) % 7  # weeks start on Sunday
    cols, step, cell = (offset + len(days) + 6) // 7, 14, 11
    gx, gy = (W - (cols * step - 3)) / 2, 112
    total, mx = sum(n for _, n in days), max(max(n for _, n in days), 1)
    ramp = ["#e2e2de"] + [mix("#e2e2de", ACCENT, t) for t in (0.4, 0.62, 0.82, 1.0)]
    c = Card("graph", 236, f"Contribution graph, {total} contributions in the last year", t0=2.4)
    c.text(48, 58, "Contribution graph", "head", 28, INK)
    c.text(48, 80, f"{plural(total, 'contribution')} in the last year", "body", 13, MUTED, d=0.05)
    lx = 782  # legend, right to left
    c.text(lx, 66, "MORE", "mono", 10, MUTED, "end", 0.1, ls=1)
    lx -= width("mono", "MORE", 10) + 4 + 8
    for lvl in range(4, -1, -1):
        lx -= 14
        c.add(f'<rect x="{lx}" y="56" width="{cell}" height="{cell}" rx="2.5" fill="{ramp[lvl]}"{c.A(0.1)}/>')
    c.text(lx - 8, 66, "LESS", "mono", 10, MUTED, "end", 0.1, ls=1)
    by_col = {}
    for i, (d, n) in enumerate(days):
        col, row = divmod(offset + i, 7)
        lvl = min(4, math.ceil(4 * n / mx)) if n else 0
        by_col.setdefault(col, []).append(
            f'<rect x="{gx + col * step:.1f}" y="{gy + row * step}" width="{cell}" height="{cell}" rx="2.5" fill="{ramp[lvl]}"/>')
        if row == 0 and col > 0 and d.month != days[max(0, i - 7)][0].month:  # like GitHub, no label on the partial first week
            c.text(gx + col * step, 102, calendar.month_abbr[d.month].upper(), "mono", 10, MUTED, d=0.1 + col * 0.02, ls=0.8)
    for col, rects in by_col.items():
        c.add(f'<g{c.A(0.1 + col * 0.02, "p")}>{"".join(rects)}</g>')
    col, row = divmod(offset + len(days) - 1, 7)  # ring marks today
    c.add(f'<rect class="smil" x="{gx + col * step - 2:.1f}" y="{gy + row * step - 2}" width="{cell + 4}" height="{cell + 4}" '
          f'rx="4" fill="none" stroke="{INK}" stroke-width="1.5"><animate attributeName="opacity" values="1;.15;1" '
          f'dur="2s" repeatCount="indefinite"/></rect>')
    return c


def main():
    OUT.mkdir(exist_ok=True)
    cards = [hero(),
             tile(1, "LIVE DEMO", "Concord", None, "", "Orbs that sing, in your browser", INK, PAPER, "#a8a8a3"),
             tile(2, "APP", "Workout", None, "", "Push, pull, legs and Couch to 5K", ACCENT, "#ffffff", "#cde6d8"),
             tile(3, "ALL WORK", "", public_repos, " public repo" + ("" if public_repos == 1 else "s"),
                  "See the full list on GitHub", PAPER, INK, MUTED),
             activity(), *(repo_card(i, r) for i, r in enumerate(repos)), graph()]
    for c in cards:
        s = c.svg()
        (OUT / f"{c.name}.svg").write_text(s, encoding="utf-8")
        print(f"{c.name}.svg  {len(s) / 1024:.1f} KB")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for c in cards:  # inline the cards so preview.html works from any viewer, still as <img> like GitHub
        uri = "data:image/svg+xml;base64," + base64.b64encode((OUT / f"{c.name}.svg").read_bytes()).decode()
        readme = readme.replace(f"cards/{c.name}.svg", uri)
    (ROOT / "preview.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Preview</title>'
        '<body style="margin:0;background:#0d1117;color:#e6edf3;font-family:system-ui">'
        f'<div style="max-width:830px;margin:24px auto">{readme}</div>', encoding="utf-8")


if __name__ == "__main__":
    main()

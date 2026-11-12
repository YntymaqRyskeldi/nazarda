"""NAZARDA дизайн жүйесі: шағын оқшауланған CSS, SVG элементтер, Plotly баптауы.

Ережелер:
- Карточкалар — st.container(border=True, key="card_...") арқылы. HTML-div ішіне виджет орауға тырыспаймыз.
- st.html тек толық, өз-өзімен жабылатын блоктар үшін (сақина, уақыт сызығының белгісі, мұқаба).
- Пайдаланушы мәтіні әрқашан html.escape арқылы шығарылады.
"""
from __future__ import annotations

import base64
import hashlib
import html
import uuid

import plotly.graph_objects as go
import streamlit as st

from core.db import BASE_DIR

INK, MUTED, INDIGO, INDIGO_L, TEAL, TEAL_L, LINE = ("#182238", "#596579", "#4F46E5", "#EEF2FF", "#0F766E",
                                                     "#E8F7F3", "#E3E8F0")
AMBER_TXT, AMBER_BG = "#92400E", "#FFF7E6"
FONT = "Noto Sans, sans-serif"

CSS = """
<style>
/* Тек мәтіндік элементтер. Streamlit белгішелерінің (Material Symbols) қарпі өзгертілмейді. */
html, body { font-size: 16px; }
.block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1180px; }
p, li, label, .stMarkdown { line-height: 1.55; }
[data-testid="stCaptionContainer"], .stCaption { font-size: 0.875rem; color: #596579; }

/* Карточкалар: тек key='card_*' контейнерлері */
[class*="st-key-card_"] { background: #FFFFFF; border-radius: 18px; }
[class*="st-key-card_"] { box-shadow: 0 1px 2px rgba(24, 34, 56, 0.04); }
.st-key-card_hero { background: #FFFFFF; }

.nz-greet { font-size: 30px; font-weight: 700; color: #182238; margin: 0; line-height: 1.2; }
.nz-sub { font-size: 16px; color: #596579; margin: 4px 0 0; }
.nz-meta { font-size: 14px; color: #596579; text-align: right; }
.nz-h { font-size: 20px; font-weight: 700; color: #182238; margin: 0 0 4px; }
.nz-kicker { font-size: 13px; color: #596579; margin: 0; }
.nz-big { font-size: 32px; font-weight: 700; color: #182238; line-height: 1.15; margin: 4px 0; }
.nz-num { font-size: 28px; font-weight: 700; color: #182238; line-height: 1.1; }
.nz-muted { color: #596579; font-size: 14px; }
.nz-badge { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 13px; font-weight: 600;
            background: #EEF2FF; color: #3730A3; margin-right: 6px; }
.nz-badge.teal { background: #E8F7F3; color: #0F766E; }
.nz-badge.amber { background: #FFF7E6; color: #92400E; }
.nz-badge.grey { background: #F1F5F9; color: #475569; }
.nz-warn { background: #FFF7E6; color: #92400E; border: 1px solid #FCD9A8; border-radius: 14px;
           padding: 12px 16px; font-size: 15px; }
.nz-demo { display: inline-block; background: #FFF7E6; color: #92400E; border: 1px solid #FCD9A8;
           border-radius: 999px; padding: 2px 12px; font-size: 13px; font-weight: 600; }
.nz-avatar { display: inline-flex; width: 40px; height: 40px; border-radius: 50%; color: #fff; font-weight: 700;
             align-items: center; justify-content: center; font-size: 16px; }
.nz-row { display: flex; gap: 12px; align-items: center; }
.nz-time { font-weight: 700; color: #182238; font-size: 16px; min-width: 52px; }
.nz-title { font-size: 16px; color: #182238; font-weight: 600; }
.nz-title.done { color: #596579; text-decoration: line-through; text-decoration-color: #A5B4FC; font-weight: 500; }
.nz-title.cancelled { color: #94A3B8; text-decoration: line-through; }
.nz-check { width: 26px; height: 26px; flex: none; }
.nz-dot { width: 26px; height: 26px; flex: none; }
.nz-calm { animation: nz-calm 420ms ease-out both; }
@keyframes nz-calm { from { opacity: 1; } to { opacity: .72; } }
.nz-confetti { position: fixed; inset: 0; pointer-events: none; z-index: 1000; overflow: hidden; }
.nz-confetti i { position: absolute; top: -12px; width: 8px; height: 14px; border-radius: 2px; opacity: 0;
                 animation: nz-fall 1600ms ease-in forwards; }
@keyframes nz-fall { 0% { opacity: 1; transform: translateY(0) rotate(0); }
                     100% { opacity: 0; transform: translateY(85vh) rotate(320deg); } }
@media (prefers-reduced-motion: reduce) {
  .nz-calm, .nz-confetti i { animation: none !important; }
  .nz-confetti { display: none; }
}
.nz-cover { width: 100%; border-radius: 14px; display: block; }
@media (max-width: 640px) {
  .block-container { padding-left: 1rem; padding-right: 1rem; padding-top: 4rem; }
  .nz-greet { font-size: 26px; }
  .nz-big { font-size: 26px; }
  .nz-meta { text-align: left; }
}
</style>
"""


def inject_css() -> None:
    st.html(CSS)


def esc(s) -> str:
    return html.escape("" if s is None else str(s))


def token(name: str) -> str:
    """Бір форма жіберілімінің тұрақты белгісі. Сәтті сақталғаннан кейін renew_token шақырылады."""
    k = f"tok_{name}"
    if k not in st.session_state:
        st.session_state[k] = uuid.uuid4().hex
    return st.session_state[k]


def renew_token(name: str) -> None:
    st.session_state[f"tok_{name}"] = uuid.uuid4().hex


def svg_img(svg: str, alt: str, width: str = "100%", height: str | None = None, cls: str = "") -> str:
    """st.html SVG элементтерін тазалайды, сондықтан SVG <img> ретінде data URI арқылы шығарылады.
    SVG ішіндегі CSS анимациясы img ішінде де жұмыс істейді."""
    if "xmlns=" not in svg[:200]:
        svg = svg.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ', 1)
    data = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    style = f"width:{width};" + (f"height:{height};" if height else "") + "display:block"
    return f'<img src="data:image/svg+xml;base64,{data}" alt="{esc(alt)}" class="{cls}" style="{style}"/>'


def h(text: str, kicker: str | None = None) -> None:
    st.html(f'<div><p class="nz-h">{esc(text)}</p>' + (f'<p class="nz-kicker">{esc(kicker)}</p>' if kicker else "")
            + "</div>")


def badge(text: str, tone: str = "") -> str:
    return f'<span class="nz-badge {tone}">{esc(text)}</span>'


def avatar(name: str, color: str, size: int = 40) -> str:
    return (f'<span class="nz-avatar" style="background:{esc(color)};width:{size}px;height:{size}px" '
            f'aria-hidden="true">{esc(name[:1])}</span>')


def demo_badge() -> str:
    return '<span class="nz-demo">Демо режимі</span>'


def warn(text: str) -> None:
    st.html(f'<div class="nz-warn" role="note">{esc(text)}</div>')


def empty(text: str, hint: str | None = None) -> None:
    st.html(f'<div style="padding:16px 4px"><p class="nz-title" style="margin:0">{esc(text)}</p>'
            + (f'<p class="nz-muted" style="margin:4px 0 0">{esc(hint)}</p>' if hint else "") + "</div>")


def ring(done: int, total: int, size: int = 132, label: str | None = None) -> str:
    r = 52
    circ = 2 * 3.14159 * r
    frac = done / total if total else 0
    off = circ * (1 - frac)
    pct = round(frac * 100)
    svg = (f'<svg width="{size}" height="{size}" viewBox="0 0 132 132">'
           f'<circle cx="66" cy="66" r="{r}" stroke="{INDIGO_L}" stroke-width="12" fill="none"/>'
           f'<circle cx="66" cy="66" r="{r}" stroke="{TEAL}" stroke-width="12" fill="none" '
           f'stroke-linecap="round" stroke-dasharray="{circ:.1f}" stroke-dashoffset="{off:.1f}" '
           f'transform="rotate(-90 66 66)"/>'
           f'<text x="66" y="75" text-anchor="middle" font-family="Noto Sans, Arial, sans-serif" font-size="27" '
           f'font-weight="700" fill="{INK}">{pct}%</text></svg>')
    return svg_img(svg, label or f"{pct}%", f"{size}px", f"{size}px")


_REDUCE = "@media (prefers-reduced-motion: reduce){*{animation:none!important}}"


def check_icon(done: bool, animate: bool = False, cancelled: bool = False) -> str:
    if cancelled:
        svg = ('<svg viewBox="0 0 26 26"><circle cx="13" cy="13" r="11" fill="#F1F5F9"/>'
               '<path d="M8 13h10" stroke="#94A3B8" stroke-width="3" stroke-linecap="round"/></svg>')
        return svg_img(svg, "Бас тартылды", "26px", "26px", "nz-dot")
    if not done:
        svg = (f'<svg viewBox="0 0 26 26"><circle cx="13" cy="13" r="10" fill="#FFFFFF" stroke="{LINE}" '
               f'stroke-width="3"/></svg>')
        return svg_img(svg, "Жоспарда", "26px", "26px", "nz-dot")
    anim = ("<style>path{stroke-dasharray:24;animation:d 380ms ease-out both}"
            "circle{transform-origin:13px 13px;animation:f 260ms ease-out both}"
            "@keyframes d{from{stroke-dashoffset:24}to{stroke-dashoffset:0}}"
            "@keyframes f{from{opacity:0;transform:scale(.7)}to{opacity:1;transform:scale(1)}}" + _REDUCE +
            "</style>") if animate else ""
    svg = (f'<svg viewBox="0 0 26 26">{anim}<circle cx="13" cy="13" r="12" fill="{TEAL_L}"/>'
           f'<path d="M7.5 13.5l3.8 3.8 7.2-8" stroke="{TEAL}" stroke-width="3" fill="none" stroke-linecap="round" '
           f'stroke-linejoin="round"/></svg>')
    return svg_img(svg, "Орындалды", "26px", "26px", "nz-check")


def confetti() -> None:
    colors = [INDIGO, TEAL, "#A5B4FC", "#5EEAD4", "#F59E0B"]
    bits = "".join(f'<i style="left:{(k * 37) % 100}%;background:{colors[k % 5]};animation-delay:{(k % 7) * 60}ms"></i>'
                   for k in range(28))
    st.html(f'<div class="nz-confetti" aria-hidden="true">{bits}</div>')


def cover_svg(title: str, image: str = "", height: int = 120) -> str:
    """Мұқаба: пайдаланушы суреті болмаса, атауға байланысты тұрақты геометриялық мұқаба салынады."""
    hsh = int(hashlib.md5(title.encode()).hexdigest(), 16)
    palettes = [(INDIGO_L, INDIGO, "#A5B4FC"), (TEAL_L, TEAL, "#5EEAD4"), ("#F1F5F9", "#475569", "#CBD5E1"),
                ("#FFF7E6", "#B45309", "#FCD9A8")]
    bg, fg, soft = palettes[hsh % len(palettes)]
    cx, cy = 60 + hsh % 160, 20 + (hsh >> 4) % 60
    letter = esc(title.strip()[:1].upper() or "N")
    svg = (f'<svg viewBox="0 0 320 {height}" preserveAspectRatio="xMidYMid slice">'
           f'<rect width="320" height="{height}" fill="{bg}"/>'
           f'<circle cx="{cx}" cy="{cy}" r="70" fill="{soft}" opacity=".55"/>'
           f'<rect x="{220 - hsh % 40}" y="{height - 50}" width="120" height="70" rx="20" fill="{soft}" opacity=".7"/>'
           f'<text x="24" y="{height - 24}" font-family="Noto Sans, Arial, sans-serif" font-size="44" '
           f'font-weight="700" fill="{fg}">{letter}</text></svg>')
    return (f'<div style="height:{height}px;overflow:hidden;border-radius:14px">'
            + svg_img(svg, f"{title} мұқабасы", "100%", f"{height}px", "nz-cover").replace(
                'display:block', 'display:block;object-fit:cover') + "</div>")


def image_tag(src: str, height: int = 120) -> str:
    return (f'<img src="{esc(src)}" alt="" class="nz-cover" style="height:{height}px;object-fit:cover" '
            f'loading="lazy"/>')


def progress_bar(frac: float, color: str = TEAL) -> str:
    frac = max(0.0, min(1.0, frac))
    return (f'<div style="background:{INDIGO_L};border-radius:999px;height:10px;overflow:hidden" role="progressbar" '
            f'aria-valuenow="{round(frac * 100)}" aria-valuemin="0" aria-valuemax="100">'
            f'<div style="width:{frac * 100:.1f}%;background:{color};height:10px;border-radius:999px"></div></div>')


def style_fig(fig: go.Figure, height: int = 300) -> go.Figure:
    fig.update_layout(font=dict(family=FONT, size=14, color=INK), height=height,
                      margin=dict(l=8, r=16, t=16, b=8), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      hoverlabel=dict(font_family=FONT), legend=dict(orientation="h", y=-0.2))
    fig.update_xaxes(gridcolor=LINE, zeroline=False)
    fig.update_yaxes(gridcolor=LINE, zeroline=False)
    return fig


PLOTLY_CFG = {"displayModeBar": False, "responsive": True}


def illustration() -> str:
    svg = (BASE_DIR / "static" / "img" / "day.svg").read_text(encoding="utf-8")
    return svg_img(svg, "Оқу, кітап, спорт және уақыт иллюстрациясы")


def flash(msg: str, kind: str = "success") -> None:
    """Rerun-нан кейін бір рет көрсетілетін қысқа хабар."""
    st.session_state.setdefault("_flash", []).append((msg, kind))


def show_flash() -> None:
    for msg, kind in st.session_state.pop("_flash", []):
        st.toast(msg, icon=":material/check_circle:" if kind == "success" else ":material/info:")


def run_action(fn, *args, ok: str | None = None, **kwargs):
    """Сервис әрекетін орындайды; қатені жасырмай, түсінікті түрде көрсетеді."""
    try:
        res = fn(*args, **kwargs)
    except (ValueError, PermissionError) as e:
        st.error(str(e), icon=":material/error:")
        return None
    if ok:
        flash(ok)
    return res if res is not None else True

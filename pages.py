"""Mini paginas por lead (GitHub Pages) con boton Copiar, color por fuente y propuesta/precio/plazo.
Las paginas se escriben en PAGES_DIR (por defecto ./docs) y GitHub Pages las publica en PAGES_BASE_URL."""
from __future__ import annotations

import hashlib
import html
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import settings

log = logging.getLogger("pages")

# Color por fuente (titulo + acentos). Freelancer = azul (pedido del usuario).
SOURCE_THEME = {
    "freelancer": {"color": "#1e88e5", "name": "Freelancer", "emoji": "\U0001F535"},
    "facebook": {"color": "#22c55e", "name": "Facebook", "emoji": "\U0001F7E2"},
    "linkedin": {"color": "#a855f7", "name": "LinkedIn", "emoji": "\U0001F7E3"},
    "twitter": {"color": "#334155", "name": "X / Twitter", "emoji": "\u26AB"},
    "reddit": {"color": "#f97316", "name": "Reddit", "emoji": "\U0001F7E0"},
    "telegram": {"color": "#06b6d4", "name": "Telegram", "emoji": "\U0001F537"},
}
DEFAULT_THEME = {"color": "#64748b", "name": "Otra fuente", "emoji": "\u26AA"}


def theme(source: str) -> dict:
    return SOURCE_THEME.get(source, DEFAULT_THEME)


def page_id(post_id: str) -> str:
    return hashlib.sha256((post_id + settings.pages_salt).encode("utf-8")).hexdigest()[:20]


TEMPLATE = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>{title}</title>
<style>
:root{{--c:{color};}}
*{{box-sizing:border-box}}body{{margin:0;background:#0f141b;color:#e6edf3;font:15px/1.55 -apple-system,Segoe UI,Roboto,Inter,sans-serif}}
.wrap{{max-width:720px;margin:0 auto;padding:18px 16px 60px}}
.src{{display:inline-flex;align-items:center;gap:8px;font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--c);border:1px solid var(--c);border-radius:999px;padding:4px 10px}}
h1{{color:var(--c);font-size:22px;line-height:1.25;margin:12px 0 6px}}
.meta{{color:#94a3b8;font-size:13px;margin-bottom:14px}}
.card{{background:#161d27;border:1px solid #243041;border-radius:14px;padding:16px;margin:12px 0}}
.card h2{{margin:0 0 10px;font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:#94a3b8}}
.kpis{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
.kpi{{background:#0f141b;border:1px solid #243041;border-radius:12px;padding:12px;text-align:center}}
.kpi b{{display:block;font-size:24px;color:var(--c)}}.kpi span{{font-size:12px;color:#94a3b8}}
.content{{font-weight:700;white-space:pre-wrap;word-wrap:break-word}}
.proposal{{white-space:pre-wrap;word-wrap:break-word;font-weight:600}}
.muted{{color:#94a3b8;font-size:13px}}
.btn{{display:flex;align-items:center;justify-content:center;gap:8px;width:100%;padding:14px;border-radius:12px;border:0;font-weight:700;font-size:16px;cursor:pointer;background:var(--c);color:#fff;margin-top:10px}}
.btn.alt{{background:#243041;color:#e6edf3}}
.btn:active{{transform:scale(.99)}}
.toast{{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);background:#22c55e;color:#06130a;font-weight:700;padding:10px 16px;border-radius:999px;opacity:0;transition:opacity .2s}}
.toast.show{{opacity:1}}
a{{color:var(--c)}}
</style></head><body><div class="wrap">
<span class="src">{emoji} {source_name} &middot; Lead {score}/100</span>
<h1>{title}</h1>
<div class="meta">{meta}</div>
{proposal_block}
<div class="card"><h2>Publicaci\u00f3n original</h2><div class="content">{content}</div>
<a class="btn alt" href="{url}" target="_blank" rel="noopener">Abrir publicaci\u00f3n en {source_name}</a></div>
<div class="muted">Generado {generated} &middot; Dev Lead Hunter</div>
<div class="toast" id="toast">Copiado</div>
<textarea id="clip" style="position:fixed;left:-9999px;top:0"></textarea>
<script>
const DATA={data_json};
function toast(t){{const e=document.getElementById('toast');e.textContent=t;e.classList.add('show');setTimeout(()=>e.classList.remove('show'),1600);}}
async function copyText(t,label){{try{{await navigator.clipboard.writeText(t);toast(label||'Copiado');}}catch(e){{const ta=document.getElementById('clip');ta.value=t;ta.select();document.execCommand('copy');toast(label||'Copiado');}}}}
function copyProposal(){{copyText(DATA.proposal,'Propuesta copiada');}}
function copyOpener(){{copyText(DATA.opener,'Mensaje copiado');}}
function copyAll(){{copyText(DATA.proposal+"\\n\\n"+(DATA.question?('Pregunta: '+DATA.question):''),'Todo copiado');}}
</script></div></body></html>
"""


class PageWriter:
    def __init__(self):
        self.dir = Path(settings.pages_dir)
        self.base_url = settings.pages_base_url.rstrip("/") if settings.pages_base_url else ""
        self.enabled = settings.pages_enabled
        if self.enabled:
            (self.dir / "p").mkdir(parents=True, exist_ok=True)
            self._ensure_index()

    def _ensure_index(self):
        (self.dir / "p").mkdir(parents=True, exist_ok=True)
        keep = self.dir / "p" / ".gitkeep"
        if not keep.exists():
            keep.write_text("", encoding="utf-8")
        idx = self.dir / "index.html"
        if not idx.exists():
            idx.write_text('<!doctype html><meta charset="utf-8"><meta name="robots" content="noindex"><title>Dev Lead Hunter</title>'
                           '<body style="font-family:sans-serif;background:#0f141b;color:#e6edf3;padding:40px"><h1>Dev Lead Hunter</h1>'
                           '<p>Las paginas de cada lead llegan por notificacion.</p></body>', encoding="utf-8")
        nj = self.dir / ".nojekyll"
        if not nj.exists():
            nj.write_text("", encoding="utf-8")

    def write(self, *, post_id: str, source: str, score: int, title: str, text: str, url: str, summary: str, opener: str,
              location: Optional[str], proposal=None) -> Optional[str]:
        """Escribe la pagina y devuelve su URL publica (o None si Pages no esta configurado)."""
        if not self.enabled:
            return None
        th = theme(source)
        pid = page_id(post_id)
        esc = html.escape
        meta_bits = [esc(summary)]
        if location:
            meta_bits.append("\U0001F4CD " + esc(location))
        proposal_block = ""
        data = {"proposal": "", "opener": opener or "", "question": ""}
        if proposal is not None:
            data["proposal"] = proposal.text
            data["question"] = proposal.question
            proposal_block = (
                '<div class="card"><h2>Cu\u00e1nto cobrar y en cu\u00e1nto tiempo</h2><div class="kpis">'
                f'<div class="kpi"><b>{esc(proposal.price_label)}</b><span>precio sugerido</span></div>'
                f'<div class="kpi"><b>{proposal.days} d\u00edas</b><span>plazo sugerido</span></div></div>'
                f'<p class="muted" style="margin:10px 0 0">{esc(proposal.justification)}</p></div>'
                '<div class="card"><h2>Propuesta lista para pegar</h2>'
                f'<div class="proposal">{esc(proposal.text)}</div>'
                '<button class="btn" onclick="copyProposal()">\U0001F4CB Copiar propuesta</button>'
                + (f'<p class="muted" style="margin:14px 0 0"><b>Pregunta / riesgo para el chat:</b> {esc(proposal.question)}</p>'
                   '<button class="btn alt" onclick="copyAll()">Copiar propuesta + pregunta</button>' if proposal.question else "")
                + f'<p class="muted" style="margin:10px 0 0">Redactada por {esc(proposal.model)}. Rev\u00edsala antes de enviar.</p></div>'
            )
        elif opener:
            proposal_block = (
                '<div class="card"><h2>Mensaje sugerido para abrir</h2>'
                f'<div class="proposal">{esc(opener)}</div>'
                '<button class="btn" onclick="copyOpener()">\U0001F4CB Copiar mensaje</button></div>'
            )
        page = TEMPLATE.format(
            title=esc(title or summary or "Lead"), color=th["color"], emoji=th["emoji"], source_name=th["name"], score=score,
            meta=" &middot; ".join(meta_bits), proposal_block=proposal_block, content=esc(text[:3000]), url=esc(url),
            generated=datetime.now().strftime("%Y-%m-%d %H:%M"), data_json=json.dumps(data, ensure_ascii=False),
        )
        path = self.dir / "p" / f"{pid}.html"
        path.write_text(page, encoding="utf-8")
        rel = f"p/{pid}.html"
        log.info("Pagina escrita: %s", path)
        return f"{self.base_url}/{rel}" if self.base_url else None

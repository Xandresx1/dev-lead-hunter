"""Pre-filtro barato por palabras clave (ES/EN) antes de gastar cuota de Gemini."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower()).strip()


# Senales de que ALGUIEN NECESITA que le construyan algo (intencion de contratar)
NEED_PATTERNS = [
    # Espanol
    r"\bbusco (un |una |a )?(programador|desarrollador|dev|ingeniero|ing\.? de sistemas|freelancer|persona|alguien|equipo|empresa|agencia)",
    r"\bnecesito (un |una |a )?(programador|desarrollador|dev|ingeniero|sistema|app|aplicacion|pagina|web|software|bot|automatizacion|alguien|quien)",
    r"\b(necesitamos|buscamos|requiero|requerimos|solicito|ocupo) (un |una |a )?(programador|desarrollador|dev|ingeniero|sistema|app|aplicacion|pagina|web|software|bot|alguien|quien)",
    r"\bquiero (hacer|crear|desarrollar|mandar a hacer|que me hagan|una app|un sistema|una pagina|un software|un bot)",
    r"\bquien (me )?(puede|pueda|sepa|sabe) (hacer|crear|desarrollar|programar)",
    r"\balguien que (me )?(haga|programe|desarrolle|cree|pueda hacer|sepa)",
    r"\b(recomiendan|recomendacion de|conocen) (un |una |a |algun |alguna )?(programador|desarrollador|freelancer|agencia|empresa de software)",
    r"\b(me )?cotiz(an|ar|acion)\b.*\b(sistema|app|aplicacion|pagina|web|software|bot)",
    r"\bpresupuesto\b.*\b(sistema|app|aplicacion|pagina|web|software|bot)",
    r"\b(hacer|crear|desarrollar) (mi|una|un) (tesis|proyecto de tesis)",
    r"\bpara (mi|nuestro|nuestra|la) (negocio|empresa|bodega|tienda|restaurante|clinica|colegio|gimnasio|farmacia|ferreteria|emprendimiento)",
    # Ingles
    r"\blooking for (a |an |someone|somebody|freelance|dev)\w* ?(developer|programmer|engineer|coder|freelancer|to build|who can)",
    r"\bneed (a |an |someone|somebody)? ?(developer|programmer|engineer|coder|freelancer|app|website|web app|system|software|bot|script|automation)",
    r"\b(hiring|seeking|want to hire|wanted) (a |an )?(developer|programmer|freelancer|engineer|coder)",
    r"\b(who can|anyone who can|someone who can|someone to) (build|develop|create|make|code|program)",
    r"\bbuild (me |us )?(a |an )?(app|website|web app|system|bot|tool|mvp|saas|platform)",
    r"\b(budget|quote|estimate)\b.*\b(app|website|system|software|bot)",
    r"\b\[hiring\]",
    r"\bfor my (business|store|shop|restaurant|clinic|gym|startup|company)",
]

# Vocabulario de software (al menos uno debe aparecer)
SOFTWARE_TERMS = [
    "sistema", "software", "app", "aplicacion", "aplicativo", "pagina web", "sitio web", "web", "plataforma", "bot",
    "automatiza", "programa", "programador", "desarrollador", "developer", "ingeniero", "erp", "crm", "pos", "punto de venta",
    "inventario", "facturacion", "ecommerce", "e-commerce", "tienda online", "tienda virtual", "landing", "api", "base de datos",
    "excel", "macro", "script", "scraper", "scraping", "dashboard", "chatbot", "whatsapp", "integracion", "tesis",
    "website", "application", "system", "database", "backend", "frontend", "mobile", "android", "ios", "saas", "mvp",
    "wordpress", "shopify", "woocommerce", "python", "javascript", "react", "flutter", "laravel", "php", "node", "django",
]

# Senales de que es OFERTA de servicios, empleo corporativo, spam o ruido -> penaliza
NEGATIVE_PATTERNS = [
    r"\b(soy|somos) (un |una |el |la )?(programador|desarrollador|ingeniero|agencia|empresa|equipo|freelancer|estudiante)",
    r"\bofrezco\b|\bofrecemos\b|\bmis servicios\b|\bnuestros servicios\b|\bbrindo\b|\bbrindamos\b",
    r"\bdisponible para (trabajar|proyectos|nuevos proyectos)",
    r"\b(en busca de|busco) (empleo|trabajo|oportunidad laboral|practicas|chamba)",
    r"\b(cv|curriculum|hoja de vida|portafolio|portfolio) (adjunto|disponible|aqui)",
    r"\b(estamos contratando|we are hiring|we're hiring|join our team|unete a nuestro equipo|vacante|convocatoria|postula)",
    r"\b(senior|semi senior|junior|jr|sr|ssr) (developer|desarrollador|engineer|ingeniero)",
    r"\b(\d\+? ?anos de experiencia|years of experience|experiencia minima|experiencia comprobable)",
    r"\b(planilla|beneficios de ley|salario|sueldo|remuneracion|rango salarial|salary range|401k|equity|full[- ]time|tiempo completo|part[- ]time)",
    r"\b(i am a|i'm a|we are a) (developer|programmer|freelancer|software house|dev shop|agency)",
    r"\b(for hire|available for work|open to work|open for projects|dm me for (rates|work|projects))\b",
    r"\b\[for hire\]",
    r"\b(curso|tutorial|aprende|webinar|masterclass|bootcamp|certificacion|descuento|promocion|inscribete)\b",
    r"\b(ganar dinero|gana dinero|inversion garantizada|trading|forex|cripto|casino|apuestas)\b",
]

_need_re = [re.compile(p) for p in NEED_PATTERNS]
_neg_re = [re.compile(p) for p in NEGATIVE_PATTERNS]


# Monedas/medios de pago a excluir por reportes de estafas (ademas de EXCLUDED_CURRENCIES en la fuente)
_CURRENCY_TEXT_PATTERNS = {
    "INR": re.compile(r"(\bINR\b|\u20b9|\brupees?\b|\brupias?\b|\bRs\.? ?\d)", re.I),
}


def excluded_currency_hit(text: str, excluded: list[str]) -> str | None:
    """Devuelve el codigo de moneda excluida si aparece en el texto (ej. 'INR'), si no None."""
    for code in excluded:
        pat = _CURRENCY_TEXT_PATTERNS.get(code.upper())
        if pat and pat.search(text or ""):
            return code.upper()
        if not pat and re.search(rf"\b{re.escape(code)}\b", text or "", re.I):
            return code.upper()
    return None


@dataclass
class PrefilterResult:
    passes: bool
    score: int  # 0-100 estimado solo por keywords
    need_hits: list[str]
    negative_hits: list[str]
    has_software_term: bool


def prefilter(text: str, *, source_is_request: bool = False) -> PrefilterResult:
    """
    source_is_request=True para fuentes donde TODO es un pedido de trabajo (ej. Freelancer):
    ahi solo exigimos vocabulario de software y pocas senales negativas.
    """
    t = normalize(text)
    need_hits = [p.pattern[:40] for p in _need_re if p.search(t)]
    neg_hits = [p.pattern[:40] for p in _neg_re if p.search(t)]
    has_sw = any(term in t for term in SOFTWARE_TERMS)

    score = 0
    if need_hits:
        score += min(60, 30 + 15 * len(need_hits))
    if has_sw:
        score += 25
    if source_is_request and has_sw:
        score += 30
    score -= 25 * len(neg_hits)
    score = max(0, min(100, score))

    if source_is_request:
        passes = has_sw and len(neg_hits) <= 1
    else:
        passes = bool(need_hits) and has_sw and len(neg_hits) < 2
    return PrefilterResult(passes, score, need_hits, neg_hits, has_sw)

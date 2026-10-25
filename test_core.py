"""
POC test_core.py - prueba aislada del nucleo del bot Dev Lead Hunter.
Cubre: ntfy, Freelancer API, Reddit (tolerante), Gemini clasificador, Apify (FB/LinkedIn/X), dedup.
Ejecutar: python test_core.py [--skip-apify]
"""
import os, sys, json, time, hashlib, sqlite3
from decimal import Decimal
from dotenv import load_dotenv
import httpx

load_dotenv()
UA = "Mozilla/5.0 (X11; Linux x86_64) dev-lead-hunter/0.1"
RESULTS = {}
SKIP_APIFY = "--skip-apify" in sys.argv


def ok(name, detail=""):
    RESULTS[name] = ("PASS", detail); print(f"[PASS] {name} {detail}")


def fail(name, detail=""):
    RESULTS[name] = ("FAIL", detail); print(f"[FAIL] {name} {detail}")


def warn(name, detail=""):
    RESULTS[name] = ("WARN", detail); print(f"[WARN] {name} {detail}")


# ---------------- 1. ntfy ----------------
def test_ntfy():
    topic = os.environ["NTFY_TOPIC"]
    r = httpx.post(f"https://ntfy.sh/{topic}", content="POC: el bot Dev Lead Hunter esta vivo",
                   headers={"Title": "Dev Lead Hunter POC", "Priority": "high", "Tags": "rocket",
                            "Click": "https://www.freelancer.com"}, timeout=15)
    if r.status_code == 200 and r.json().get("topic") == topic:
        ok("ntfy", f"msg id={r.json()['id']}")
    else:
        fail("ntfy", f"{r.status_code} {r.text[:100]}")


# ---------------- 2. Freelancer public API ----------------
def test_freelancer():
    items = []
    for q, lang in [("sistema web", "es"), ("need developer app", None)]:
        params = {"query": q, "limit": 5, "compact": "true", "sort_field": "time_updated", "full_description": "true"}
        if lang: params["languages[]"] = lang
        r = httpx.get("https://www.freelancer.com/api/projects/0.1/projects/active/", params=params,
                      headers={"User-Agent": UA}, timeout=20)
        r.raise_for_status()
        for p in r.json()["result"]["projects"]:
            items.append({"id": f"freelancer:{p['id']}", "source": "freelancer", "title": p["title"],
                          "text": (p.get("description") or p.get("preview_description") or "")[:800],
                          "url": f"https://www.freelancer.com/projects/{p['seo_url']}", "ts": p["time_submitted"]})
    if len(items) >= 3:
        ok("freelancer_api", f"{len(items)} items, ej: {items[0]['title'][:50]}")
    else:
        fail("freelancer_api", f"solo {len(items)} items")
    return items


# ---------------- 3. Reddit (tolerante) ----------------
def test_reddit():
    try:
        r = httpx.get("https://www.reddit.com/r/forhire/search.json",
                      params={"q": "developer", "sort": "new", "restrict_sr": 1, "limit": 3},
                      headers={"User-Agent": UA}, timeout=15)
        if r.status_code == 200:
            n = len(r.json()["data"]["children"]); ok("reddit_public", f"{n} items"); return
        warn("reddit_public", f"HTTP {r.status_code} (bloqueado desde IP cloud, fuente se omite sin romper el bot)")
    except Exception as e:
        warn("reddit_public", f"{type(e).__name__}: {e}")


# ---------------- 4. Gemini classifier ----------------
SAMPLES = [
    ("es_lead", "Hola, busco un programador que me haga un sistema de ventas e inventario para mi bodega en Lima, "
                "con boletas electronicas. Presupuesto a convenir, escribanme al privado.", True),
    ("en_lead", "Looking for someone to build a simple mobile app for my gym to manage memberships and payments. "
                "Not a company, just me. DM me with rates please.", True),
    ("es_offer", "Soy desarrollador full stack con 5 anos de experiencia, ofrezco desarrollo de paginas web y sistemas "
                 "a medida, precios comodos, contactame.", False),
    ("en_corp_job", "We are hiring! Senior Backend Engineer (Java, Kubernetes) at Globant. 5+ years, remote LATAM. "
                    "Apply through our careers page.", False),
]


def test_gemini():
    from google import genai
    from google.genai import types
    from pydantic import BaseModel

    class LeadVerdict(BaseModel):
        is_lead: bool
        score: int
        lead_type: str
        language: str
        summary_es: str
        reply_opener_es: str

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    system = (
        "Eres un filtro para un freelancer ingeniero de software/sistemas de Peru. Analiza publicaciones de redes "
        "sociales (espanol o ingles). is_lead=true SOLO si una PERSONA o pequeno negocio NECESITA que alguien le "
        "construya/arregle software (app, web, sistema, bot, automatizacion, tesis, etc.) y busca a quien contratar. "
        "is_lead=false si: la persona OFRECE sus servicios, es una oferta de empleo corporativa (empresa contratando "
        "empleados con requisitos), es spam, noticia, tutorial o pregunta tecnica. "
        "score 0-100 = probabilidad de que sea un cliente real alcanzable por mensaje directo. "
        "lead_type: 'cliente_directo' | 'oferta_servicios' | 'empleo_corporativo' | 'otro'. "
        "language: 'es' | 'en' | 'otro'. summary_es: resumen de 1 linea en espanol. "
        "reply_opener_es: primera frase sugerida para contactar (en el idioma del post), max 25 palabras."
    )
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    correct = 0
    for name, text, expected in SAMPLES:
        for attempt in range(3):
            try:
                resp = client.models.generate_content(
                    model=model, contents=f"PUBLICACION:\n{text}",
                    config=types.GenerateContentConfig(system_instruction=system, response_mime_type="application/json",
                                                       response_schema=LeadVerdict, temperature=0.1))
                v: LeadVerdict = resp.parsed
                hit = v.is_lead == expected
                correct += hit
                print(f"   - {name}: is_lead={v.is_lead} score={v.score} type={v.lead_type} lang={v.language} "
                      f"{'OK' if hit else 'MISMATCH'} | {v.summary_es[:60]}")
                break
            except Exception as e:
                msg = str(e)
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                    print(f"   - {name}: 429, reintento {attempt+1}"); time.sleep(8); continue
                fail("gemini", f"{name}: {type(e).__name__}: {msg[:200]}"); return
    if correct == len(SAMPLES):
        ok("gemini", f"{correct}/{len(SAMPLES)} clasificaciones correctas con {model}")
    elif correct >= 3:
        warn("gemini", f"{correct}/{len(SAMPLES)} correctas (ajustar prompt)")
    else:
        fail("gemini", f"{correct}/{len(SAMPLES)} correctas")


# ---------------- 5. Apify ----------------
def test_apify():
    if SKIP_APIFY:
        warn("apify", "omitido por --skip-apify"); return
    from apify_client import ApifyClient
    client = ApifyClient(os.environ["APIFY_TOKEN"])
    me = client.user().get()
    print(f"   Apify user: {me.username} plan={me.plan.id} credits=${me.plan.monthly_usage_credits_usd}")
    cap = Decimal(os.getenv("APIFY_MAX_CHARGE_USD", "0.10"))

    def run(label, actor_id, run_input, extract):
        try:
            # verify actor exists
            info = client.actor(actor_id).get()
            if not info:
                fail(f"apify_{label}", f"actor {actor_id} no existe"); return
            print(f"   actor {actor_id} ok -> running...")
            from datetime import timedelta
            run = client.actor(actor_id).call(run_input=run_input, max_total_charge_usd=cap,
                                              run_timeout=timedelta(seconds=240), wait_duration=timedelta(seconds=270), logger=None)
            run = run.model_dump(by_alias=True) if hasattr(run, "model_dump") else dict(run)
            status = str(run.get("status"))
            items = list(client.dataset(run["defaultDatasetId"]).iterate_items(limit=20))
            usd = run.get("usageTotalUsd")
            if status in ("SUCCEEDED", "SUCCEEDED_WITH_WARNINGS"):
                sample = extract(items[0]) if items else None
                ok(f"apify_{label}", f"status={status} items={len(items)} usd={usd} sample={str(sample)[:90]!r}")
                if items:
                    print("   keys:", sorted(items[0].keys())[:30])
                    print("   item0:", json.dumps(items[0], ensure_ascii=False)[:600])
            else:
                fail(f"apify_{label}", f"status={status} usd={usd} msg={run.get('statusMessage')} items={len(items)}")
        except Exception as e:
            fail(f"apify_{label}", f"{type(e).__name__}: {str(e)[:300]}")

    run("twitter", "simoit/x-twitter-search-tweets-scrapper",
        {"inputTargetType": "search", "searchTerms": "\"busco programador\" OR \"necesito un programador\"",
         "sort": "latest", "limit": 10, "maxPages": 1, "maxItems": 10, "includeReplies": False, "includeRetweets": False},
        lambda it: it.get("text") or it.get("full_text") or it.get("fullText"))

    run("linkedin", "datadoping/linkedin-posts-search-scraper",
        {"keywords": ["busco desarrollador de software"], "max_posts": 10, "sort_by": "date_posted", "date_filter": "past-week"},
        lambda it: it.get("text") or it.get("post_text") or it.get("content"))

    run("facebook", "apify/facebook-groups-scraper",
        {"startUrls": [{"url": "https://www.facebook.com/groups/programadoresperu"}], "resultsLimit": 5,
         "viewOption": "CHRONOLOGICAL", "onlyPostsNewerThan": "30 days"},
        lambda it: it.get("text") or it.get("message"))


# ---------------- 6. Dedup ----------------
def test_dedup(items):
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE seen (id TEXT PRIMARY KEY, ts INTEGER)")
    new = 0
    for it in items * 2:
        try:
            db.execute("INSERT INTO seen VALUES (?, ?)", (it["id"], int(time.time()))); new += 1
        except sqlite3.IntegrityError:
            pass
    if new == len(items):
        ok("dedup", f"{len(items)} unicos de {len(items)*2} procesados")
    else:
        fail("dedup", f"new={new} expected={len(items)}")


if __name__ == "__main__":
    steps = [("ntfy", test_ntfy), ("reddit", test_reddit), ("gemini", test_gemini), ("apify", test_apify)]
    if "--only-apify" in sys.argv:
        steps = [("apify", test_apify)]
    items = []
    try:
        items = test_freelancer()
    except Exception as e:
        fail("freelancer_api", f"{type(e).__name__}: {e}")
    for name, fn in steps:
        try:
            fn()
        except Exception as e:
            fail(name, f"{type(e).__name__}: {str(e)[:300]}")
    test_dedup(items)
    print("\n===== RESUMEN =====")
    for k, (s, d) in RESULTS.items():
        print(f"{s:5} {k:18} {d}")
    sys.exit(1 if any(s == "FAIL" for s, _ in RESULTS.values()) else 0)

"""Broker Watch judge: pure functions, no I/O, no network. Ported from the phase 2 spike.

A subject `p` is a dict: first, middle, last, alt_first, names, city, state, birth_year, age, year
(`year` = the reference year for "born 19xx"; defaults to this year). Every verdict here is tested
against saved, PII-scrubbed pages in tests/fixtures (golden 1-3).
"""
import datetime as dt
import re
from urllib.parse import urlparse, unquote

STATES = {"TN": "tennessee", "KY": "kentucky"}

SPONSOR = re.compile(r"(?i)sponsored|paid service|paid results|^\s*ad\s*$|advertise with us")
SPONSOR_END = re.compile(r"(?i)^(advertise with us|need more data|directory|people:|faq|summary)")
CHALLENGE = re.compile(r"(?i)just a moment|verify you are (a )?human|attention required|access denied|unusual traffic|"
                       r"press (&|and) hold|captcha|are you a robot|checking your browser|request blocked|error 1020")
NO_RESULTS = re.compile(r"(?i)no results|0 results|no records found|couldn'?t find any|we could not find|no matches|"
                        r"did not find|no people found|0 records|page not found|isn'?t available")
GONE = re.compile(r"(?i)transferred by court order|atlas data privacy")
CONSENT = re.compile(r"^\s*(i agree|agree|accept|accept all|continue to results|continue|i understand|ok|got it)\s*$", re.I)
BAD_LINK = re.compile(r"(?i)/send\?|widget|tracking|checkout|/lp/|linksynergy|pubview|/auth/|login|signup|optout|opt-out|"
                      r"minage|age_range|/es/|#|/reviews|/about|/api|privacy|terms")


# ---------------- the judge (pure; no I/O) ----------------

ECHO = re.compile(r"(?i)search criteria|you searched for|modify search|edit search")


def clean(text):
    """Drop sponsored blocks (ads for other brokers carry other people's / the owner's rows) and query echoes."""
    out, skip, echo = [], 0, 0
    for line in text.split("\n"):
        if ECHO.search(line):
            echo = 3; continue
        if echo:
            echo -= 1
            if line.strip(): continue
        if SPONSOR.search(line):
            skip = 14; continue
        if skip:
            if SPONSOR_END.search(line.strip()):
                skip = 0
            else:
                skip -= 1; continue
        out.append(line)
    return "\n".join(out)


AGE_PATS = [r"(?i)\bage[d]?\s*[:\-]?\s*\|?\s*(\d{2})\b", r"(?i)\b(\d{2})\s*(?:years old|yrs\b|year-old)",
            r"(?i)\bage\b[^\d\n]{0,6}\n?\s*(\d0)s\b", r"(?i)in their (\d0)s", r"(?i)\bborn\b[^\n\d]{0,12}(\d{4})",
            r"^\w{0,20}\.?,\s*(\d{2})\s*(?:\||\n|$)"]  # MyLife: "Name, 46 |" (window starts at the surname)


def ages_in(s, by, year=None):
    """[(age, kind)] in order of appearance. kind: exact | decade."""
    year = year or dt.date.today().year
    hits = []
    for pat in AGE_PATS:
        for m in re.finditer(pat, s):
            v = int(m.group(1)); kind = "exact"
            if v > 1900: v = year - v
            elif m.group(0).rstrip().endswith("s") and v % 10 == 0 and "0s" in m.group(0): kind = "decade"
            if 18 <= v <= 110: hits.append((m.start(), v, kind))
    hits.sort()
    return [(v, k) for _, v, k in hits]


def age_ok(v, kind, age):
    return (v <= age < v + 10) if kind == "decade" else abs(v - age) <= 1


# A line listing other people ("Relatives: A • B • the subject's name"): a name there is never the page's subject,
# and the next age after it belongs to whoever comes next (seen 2026-10-14 on a FastPeopleSearch listing).
KIN_LINE = re.compile(r"(?i)^\s*(relatives?|possible relatives|related to|associated with|associates|possible associates|"
                      r"family members?|neighbors?|household members?|also lived here|others at this address)\b")


def in_kin_line(t, i):
    start = t.rfind("\n", 0, i) + 1
    return bool(KIN_LINE.match(t[start:i + 1]))


def judge_listing(text, p):
    """Individual listing page: subject = first full-name hit (not inside a relatives line); age = first age after it."""
    t = clean(text)
    low = t.lower(); F, L = p["first"].lower(), p["last"].lower(); alt = p["alt_first"].lower()
    idx = [m.start() for m in re.finditer(re.escape(L), low)]
    idx = [i for i in idx if (F in low[max(0, i - 40):i] or alt in low[max(0, i - 40):i] or F in low[i:i + 40])
           and not in_kin_line(t, i)]
    if not idx:
        return {"subject": None, "verdict": "no-name"}
    tail = t[idx[0]:idx[0] + 1500]
    a = ages_in(tail, p["birth_year"], p.get("year"))
    if not a:
        return {"subject": "name", "verdict": "no-age"}
    v, kind = a[0]
    return {"subject": "name+age", "age_kind": kind, "verdict": "me" if age_ok(v, kind, p["age"]) else "other",
            "age_off": v - p["age"] if kind == "exact" else None}


def judge_cards(text, p):
    """Result cards (only when a site has no free individual listing). Each card = name hit + next ~250 chars."""
    t = clean(text); low = t.lower(); F, L = p["first"].lower(), p["last"].lower(); alt = p["alt_first"].lower()
    cards = []
    for m in re.finditer(re.escape(L), low):
        i = m.start()
        if not (F in low[max(0, i - 40):i] or alt in low[max(0, i - 40):i]) or in_kin_line(t, i):
            continue
        window = t[i:i + 260]
        nxt = low.find(L, i + len(L) + 5)
        if 0 < nxt - i < 260 and F in low[max(0, nxt - 40):nxt]:
            window = t[i:nxt]
        a = ages_in(window, p["birth_year"], p.get("year"))
        if not a:  # Intelius/TruthFinder grid: bare age on its own line under the name
            mm = re.search(r"\n\s*\|?\s*(\d{2})\s*\|?\s*\n", window)
            a = [(int(mm.group(1)), "exact")] if mm else []
        if a:
            cards.append("me" if age_ok(a[0][0], a[0][1], p["age"]) else "other")
    if "me" in cards: return {"verdict": "me", "cards": len(cards)}
    if cards: return {"verdict": "other", "cards": len(cards)}
    return {"verdict": "no-age", "cards": 0}


NOT_FOUND_PAGE = re.compile(r"(?i)\b404\b|not found|cannot be found|could not be found")


def is_challenge(text):
    """A bot wall / CAPTCHA page (logged per run so we learn how often the owner is needed)."""
    return bool(CHALLENGE.search(text[:3000]))


def classify_page(status, url, text, p, none_on_404=False):
    """Is this page usable at all? Returns blocked | gone | none | unrecognized | ok.

    none_on_404: the site answers a name URL for someone it has no listing for with a real 404 page
    (proven per site on the made-up person). Only those sites may turn a 404 into "none"; anywhere else a
    404 stays "couldn't check", because a changed URL pattern must never read as "not found".
    """
    if url.startswith("chrome-error") or status is None:
        return "blocked"
    if GONE.search(text):
        return "gone"
    if CHALLENGE.search(text[:3000]) and p["last"].lower() not in text.lower():
        return "blocked"
    named = p["last"].lower() in text.lower()
    if NO_RESULTS.search(text) and (named or status == 404):
        if not re.search(re.escape(p["first"]) + r"\W{1,3}(\w\.?\W{1,3})?" + re.escape(p["last"]), clean(text), re.I):
            return "none"
    if status in (401, 403, 429, 503) and not named:
        return "blocked"
    if status == 404 and named:
        return "none"
    if not named and none_on_404 and status == 404 and len(text) >= 400 and NOT_FOUND_PAGE.search(text) \
            and not CHALLENGE.search(text[:3000]):
        return "none"
    if not named:
        return "blocked" if len(text) < 400 or status >= 400 else "unrecognized"
    return "ok"


def listing_links(links, page_url, p):
    host = urlparse(page_url).netloc.replace("www.", "")
    F, L = p["first"].lower(), p["last"].lower(); alt = p["alt_first"].lower()
    base = page_url.split("#")[0].rstrip("/")
    out = []
    for l in links:
        h = l["href"]
        if urlparse(h).netloc.replace("www.", "") != host or BAD_LINK.search(h) or h.split("#")[0].rstrip("/") == base:
            continue
        path = unquote(urlparse(h).path).lower()
        card = (l.get("card") or "").lower()
        has_id = bool(re.search(r"/find/person/|/detail/|_id_|/p\d+|/e\d+|/g-?\d+", path)) or \
            any(len(seg) >= 8 and re.search(r"\d", seg) and re.search(r"[a-z]", seg, re.I) for seg in path.split("/"))
        if not has_id:
            continue
        slug_named = bool(re.search(r"/[a-z]+[-_+][a-z]", path))  # path carries someone's name
        if slug_named:
            ok = L in path and (F in path or alt in path)  # relatives' pages carry a different name: skip
        else:
            who = card[:200]
            ok = L in who and (F in who or alt in who)
        if ok:
            if h not in out:
                out.append(h)
    return out[:8]


def site_verdict(page_results):
    """Combine listing/card verdicts into one site verdict."""
    vs = [r["verdict"] for r in page_results]
    if "me" in vs: return "me"
    if "other" in vs: return "not-me"
    return "unknown"


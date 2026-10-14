"""The escalation ladder for one site, independent of how pages are fetched.

A fetcher has .name and .fetch(url, label) -> (status, final_url, text, links). The weekly job passes real
fetchers (HTTP, fresh Chrome, Chrome with the saved profile); tests pass fixture fetchers built from saved,
PII-scrubbed pages. Every verdict decision lives here or in judge.py, so CI tests the same code the job runs.
"""
import re
from urllib.parse import quote, unquote, urlparse

from judge import (BAD_LINK, classify_page, is_challenge, judge_cards, judge_listing, listing_links, site_verdict)

RANK = {"me": 4, "not-me": 3, "none": 3, "gone": 3, "couldnt": 0}


def run_step(fetcher, site, url, p, none_on_404=False, save=None):
    """One ladder step (1-3, or 5 with a changed query) on one site. Returns a dict with 'verdict' in
    me | not-me | none | gone | couldnt, plus evidence, listing url and whether a CAPTCHA/bot wall was hit."""
    save = save or (lambda *a: None)
    status, final, text, links = fetcher.fetch(url, f"{site} search")
    save(site, "search", final, text)
    cls = classify_page(status, final, text, p, none_on_404=none_on_404)
    rec = {"http": status, "page": cls, "listings": [], "captcha": is_challenge(text)}
    if cls in ("blocked", "gone", "none", "unrecognized"):
        rec["verdict"] = {"blocked": "couldnt", "gone": "gone", "none": "none", "unrecognized": "couldnt"}[cls]
        return rec
    results, urls = [], listing_links(links, final, p)
    for i, h in enumerate(urls):
        st2, fin2, t2, _ = fetcher.fetch(h, f"{site} listing {i + 1}/{len(urls)}")
        save(site, f"listing{i + 1}", fin2, t2)
        rec["captcha"] = rec["captcha"] or is_challenge(t2)
        c2 = classify_page(st2, fin2, t2, p)
        if c2 != "ok":
            results.append({"verdict": "blocked" if c2 in ("blocked", "unrecognized") else c2, "url": fin2})
            continue
        results.append(dict(judge_listing(t2, p), url=fin2))
    rec["listings"] = [r.get("verdict") for r in results]
    v = site_verdict(results)
    if v == "unknown":  # no usable free listing: judge the result cards (gated sites land here)
        j = judge_cards(text, p)
        rec["cards"] = j
        v = {"me": "me", "other": "not-me"}.get(j["verdict"], "unknown")
        rec["evidence"], rec["url"] = "card", final
        if v == "me" and re.search(r"(?i)open report|view full report|view report|unlock", text):
            rec["gated"] = True
    else:
        rec["evidence"] = "listing"
        rec["url"] = next((r["url"] for r in results if r.get("verdict") == ("me" if v == "me" else "other")), final)
    if v == "unknown":
        v = "couldnt" if any(r.get("verdict") == "blocked" for r in results) else "none"
    rec["verdict"] = v
    return rec


def side_door(fetcher, site, url, p, save=None):
    """Step 4: find the site's listing through a search engine (DuckDuckGo html, `uddg=` redirect links)."""
    save = save or (lambda *a: None)
    dom = urlparse(url).netloc.replace("www.", "")
    q = f'site:{dom} "{p["first"]} {p["last"]}"'
    _, _, _, links = fetcher.fetch("https://duckduckgo.com/html/?q=" + quote(q), f"{site} side door")
    hits = []
    for l in links:
        h = l["href"]
        m = re.search(r"[?&]uddg=([^&]+)", h)
        h = unquote(m.group(1)) if m else h
        if dom in urlparse(h).netloc and h not in hits and not BAD_LINK.search(h):
            hits.append(h)
    res, captcha = [], False
    for i, h in enumerate(hits[:4]):
        st, fin, t, _ = fetcher.fetch(h, f"{site} side-door hit {i + 1}")
        save(site, f"sidedoor{i + 1}", fin, t)
        captcha = captcha or is_challenge(t)
        c = classify_page(st, fin, t, p)
        res.append(dict(judge_listing(t, p), url=fin) if c == "ok" else {"verdict": c})
    v = site_verdict(res)
    if v == "unknown":
        v = "couldnt" if (not hits or all(x.get("verdict") == "blocked" for x in res)) else "none"
    out = {"page": "search-engine", "hits": len(hits), "listings": [x.get("verdict") for x in res], "verdict": v,
           "captcha": captcha}
    if v in ("me", "not-me"):
        out["evidence"] = "listing"
        out["url"] = next(x["url"] for x in res if x.get("verdict") == ("me" if v == "me" else "other"))
    return out


def better(a, b):
    """The more informative of two step results (a real answer beats couldn't check)."""
    return b if a is None or RANK[b["verdict"]] > RANK[a["verdict"]] else a


def final_result(best):
    """Site verdict -> what the app stores. 'not-me' (only a relative listed) is 'not found' for the owner."""
    v = best["verdict"]
    return {"me": "found", "not-me": "not_found", "none": "not_found", "gone": "gone", "couldnt": "couldnt_check"}[v]

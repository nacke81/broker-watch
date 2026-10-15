"""Ladder step 6: the owner in the loop. A site that stopped at a CAPTCHA on every automated step is opened in the
Broker Watch Chrome (saved profile, port 9333) on this PC; the owner solves it once; the job then re-checks that site
with the same profile (so the cookie the solve left behind is what gets tested) and updates this week's result.

  python job/solve.py brokerwatch://solve/SearchPeopleFree   (what the app's button launches, via the URL handler)
  python job/solve.py --site SearchPeopleFree [--dry]         (by hand; --dry writes nothing)
  python job/solve.py --register                              (install the brokerwatch:// handler for this user)

Only site names from sites.py are accepted: the URL handler can be called by any web page, so its argument is untrusted.
Never pays a CAPTCHA farm and never solves anything itself: if nobody solves it in time, the site stays couldn't check.
Stdout carries no personal data.
"""
import argparse, datetime as dt, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ladder  # noqa: E402
import run as R  # noqa: E402
from judge import classify_page, is_challenge  # noqa: E402
from sites import NONE_ON_404, SITES, site_urls, step5_queries  # noqa: E402

WAIT_S = 600  # ten minutes to solve it


def parse_target(arg):
    """'brokerwatch://solve/Name' or 'Name' -> a known site name, else None."""
    m = re.match(r"(?i)^(?:brokerwatch:/*solve/)?([A-Za-z]+)/?$", (arg or "").strip())
    name = m and next((s for s in SITES if s.lower() == m.group(1).lower()), None)
    return name or None


def wait_for_human(pg, timeout_s=WAIT_S, poll_s=2.0, p=None):
    """Wait until the page in front of the owner is no longer a challenge. Returns ('solved', secs) or ('timeout', secs).
    'Solved' means the page now reads as a real page: no challenge text and enough content to judge."""
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            text = pg.inner_text("body", timeout=3000)
        except Exception:
            text = ""
        if text and not is_challenge(text) and len(text) >= 400:
            return "solved", round(time.time() - t0, 1)
        pg.wait_for_timeout(int(poll_s * 1000))
    return "timeout", round(time.time() - t0, 1)


def recheck(fetcher, site, url, p, save=None):
    """After the solve: the plain search with the same profile, then the changed queries if that wasn't 'me'."""
    best = None
    tries = [(None, "name", url)] + [tuple(q) for q in step5_queries(p, site)]
    for variant, kind, u in tries:
        r = ladder.run_step(fetcher, site, u, p, site in NONE_ON_404 and kind == "name", save, cards=(kind == "name"))
        r["variant"] = variant
        best = ladder.better(best, r)
        print(f"{site:22} re-check {variant or 'name'}: {r['verdict']}{' CAPTCHA again' if r.get('captcha') else ''}", flush=True)
        if r["verdict"] in ("me", "gone") or r.get("captcha"):
            break  # found, or the wall is back: stop hitting the site
    return best


def write_result(db, site, best):
    """Update this site's row in the latest finished run, and that run's counts."""
    runs = db.call("GET", f"bw_runs?owner=eq.{db.owner}&status=eq.ok&select=id&order=finished_at.desc&limit=1")
    if not runs:
        return "no finished run to update"
    rid = runs[0]["id"]
    rows = db.call("GET", f"bw_checks?run_id=eq.{rid}&site=eq.{site}&select=id,tried")
    if not rows:
        return "site not in the latest run"
    res = ladder.final_result(best)
    db.call("PATCH", f"bw_checks?id=eq.{rows[0]['id']}", {
        "result": res, "step": 6 if res != "couldnt_check" else None, "tried": sorted(set(rows[0]["tried"] + [6])),
        "evidence": best.get("evidence"), "url": best.get("url"), "captcha": True,
        "reason": "captcha" if res == "couldnt_check" and best.get("captcha") else None,
        "query": best.get("variant") if res != "couldnt_check" else None}, prefer="return=minimal")
    allc = db.call("GET", f"bw_checks?run_id=eq.{rid}&select=result")
    n = {k: sum(c["result"] == k for c in allc) for k in ("found", "not_found", "couldnt_check", "gone")}
    db.call("PATCH", f"bw_runs?id=eq.{rid}", {"found": n["found"], "not_found": n["not_found"], "couldnt": n["couldnt_check"],
                                              "gone": n["gone"]}, prefer="return=minimal")
    return f"updated: {res} (step 6)"


def solve(site, E, dry=False, wait_s=WAIT_S):
    try:
        return _solve(site, E, dry, wait_s)
    finally:  # the window the owner solved in closes after the solve or the timeout, and on a crash; a Chrome already up is left alone
        R.stop_chrome()


def _solve(site, E, dry=False, wait_s=WAIT_S):
    from playwright.sync_api import sync_playwright
    from fetchers import BrowserFetcher
    reader = R.DB(E)
    rows = reader.call("GET", f"bw_profile?owner=eq.{reader.owner}&select=*")
    p, src = R.subject(rows[0] if rows else None, E)
    url = site_urls(p)[site]
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = os.path.join(R.BW, "runs", f"{stamp}-solve-{site}" + ("-dry" if dry else ""))
    os.makedirs(os.path.join(out_dir, "pages"), exist_ok=True)

    def save(s, what, u, text):
        fn = re.sub(r"[^\w.-]", "_", f"{s}__s6__{what}") + ".txt"
        open(os.path.join(out_dir, "pages", fn), "w", encoding="utf-8").write(u + "\n\n" + text)

    print(f"solve {site}: details from {src}; chrome (saved profile): {R.ensure_chrome()}", flush=True)
    with sync_playwright() as pw:
        ctx = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{R.CDP_PORT}").contexts[0]
        pg = ctx.new_page()
        try:
            r = pg.goto(url, timeout=45000, wait_until="domcontentloaded")
            pg.bring_to_front()
            pg.wait_for_timeout(4000)
            first = pg.inner_text("body", timeout=8000)
            walled = is_challenge(first) or classify_page(r.status if r else None, pg.url, first, p) == "blocked"
            print(f"{site:22} opened: {'CAPTCHA/bot wall, waiting for you' if walled else 'no wall right now'}", flush=True)
            outcome, secs = wait_for_human(pg, wait_s) if walled else ("no-wall", 0)
            print(f"{site:22} {outcome} after {secs}s", flush=True)
        finally:
            try:
                pg.close()
            except Exception:
                pass
        if outcome == "timeout":
            print("RESULT not solved in time; the site stays couldn't check", flush=True)
            return 2
        best = recheck(BrowserFetcher(ctx, "chrome-profile", human=True), site, url, p, save)
    res = ladder.final_result(best)
    why = "" if res != "couldnt_check" else " (CAPTCHA again)" if best.get("captcha") else " (blocked without a CAPTCHA: nothing to solve)"
    print(f"RESULT {site}: {res}{why}", flush=True)
    print(("DRY: nothing written" if dry else write_result(reader, site, best)), flush=True)
    if not dry:
        R.notify(f"Broker Watch: {site} re-checked after your solve: " + {"found": "it lists you", "not_found": "no listing of you",
                 "gone": "site gone", "couldnt_check": "still couldn't check" + why}[res] + ". The app is updated.")
    print("RUN", out_dir)
    return 0 if res != "couldnt_check" else 3


def register():
    """brokerwatch://solve/<Site> -> pythonw solve.py "<url>" for this Windows user (HKCU, no admin). Straight to
    Python, never through cmd.exe: the URL comes from a web page, and cmd would expand %VARS% and & inside it."""
    import winreg
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\brokerwatch")
    winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "URL:Broker Watch")
    winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
    c = winreg.CreateKey(k, r"shell\open\command")
    winreg.SetValueEx(c, "", 0, winreg.REG_SZ, f'"{pyw}" "{os.path.abspath(__file__)}" "%1"')
    print("registered brokerwatch:// ->", winreg.QueryValue(k, r"shell\open\command"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", nargs="?")
    ap.add_argument("--site"); ap.add_argument("--dry", action="store_true"); ap.add_argument("--register", action="store_true")
    ap.add_argument("--wait", type=int, default=WAIT_S)
    a = ap.parse_args()
    if a.register:
        return register()
    if sys.stdout is None or (a.target or "").lower().startswith("brokerwatch:"):
        os.makedirs(os.path.join(R.BW, "logs"), exist_ok=True)  # launched by the app's button: no console, log to file
        sys.stdout = sys.stderr = open(os.path.join(R.BW, "logs", "solve-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S") + ".log"),
                                       "w", encoding="utf-8", buffering=1)
    site = parse_target(a.site or a.target)
    if not site:
        print("refused: not a Broker Watch site name", flush=True)
        sys.exit(64)
    sys.exit(solve(site, R.load_env(), dry=a.dry, wait_s=a.wait))


if __name__ == "__main__":
    main()

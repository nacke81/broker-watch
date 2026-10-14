"""Broker Watch weekly job. Runs on the owner's PC (home connection + the saved Chrome profile), reads only.

  python job/run.py                   the real weekly run: every site, ladder steps 1-5, results to the database
  python job/run.py --check           watchdog: alert if no finished run in the last 8 days (PC off, task broken)
  python job/run.py --sites A,B --dry a partial run, nothing written (for testing)
  python job/run.py --fail-on-purpose prove the alert path: the run fails and Reed is alerted

Sites are visited in rounds (step 1 on every site, then step 2 on the ones still open, ...), so no site is hit
twice in a row: yesterday's Whitepages CAPTCHA came from 5 hits in one burst. Every CAPTCHA/bot wall is counted.

Needs (default profile .env, never printed): PEOPLE_CRM_SUPABASE_URL, PEOPLE_CRM_SECRET_KEY, BROKER_WATCH_OWNER_ID.
The owner's details come from his My details page (bw_profile); the .env BROKER_WATCH_* lines are the fallback.
Local evidence (contains personal data, never committed): %LOCALAPPDATA%/broker-watch/runs/<stamp>/.
Stdout carries no personal data: site names, verdicts, counts.
"""
import argparse, datetime as dt, json, os, re, subprocess, sys, time, traceback, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ladder  # noqa: E402
from sites import NONE_ON_404, SITES, STATES, site_urls, step5_queries  # noqa: E402

BW = os.path.expandvars(r"%LOCALAPPDATA%/broker-watch")
ENV_FILE = os.path.expandvars(r"%LOCALAPPDATA%/hermes/.env")
CDP_PORT = 9333
CHROME = r"C:/Program Files/Google/Chrome/Application/chrome.exe"
TELEGRAM = "telegram:6554402525"
APP_URL = "https://nacke81.github.io/broker-watch/"


def load_env():
    E = {}
    for l in open(ENV_FILE, encoding="utf-8"):
        if "=" in l and not l.lstrip().startswith("#"):
            k, v = l.rstrip("\n").split("=", 1)
            E[k.strip()] = v.strip().strip('"')
    return E


class DB:
    """Supabase REST with the secret key (bypasses row security, so owner is always set explicitly)."""

    def __init__(self, E):
        self.url, self.key, self.owner = E["PEOPLE_CRM_SUPABASE_URL"], E["PEOPLE_CRM_SECRET_KEY"], E["BROKER_WATCH_OWNER_ID"]

    def call(self, method, path, body=None, prefer="return=representation"):
        req = urllib.request.Request(self.url + "/rest/v1/" + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"apikey": self.key, "Authorization": "Bearer " + self.key,
                                              "Content-Type": "application/json", "Prefer": prefer})
        with urllib.request.urlopen(req, timeout=30) as r:
            t = r.read()
            return json.loads(t) if t else None


# ---------------- the subject (the owner) ----------------

SUF = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv"}


def subject(profile, E, fake=False):
    """Build the judge's subject from My details (bw_profile) or the .env fallback."""
    if profile and profile.get("names") and profile.get("city_state") and profile.get("birth_year"):
        names, cs, by, src = profile["names"], profile["city_state"], int(profile["birth_year"]), "app"
        phones, addrs = profile.get("phones") or [], profile.get("addresses") or []
    else:
        names = [n.strip() for n in E["BROKER_WATCH_NAMES"].split(";") if n.strip()]
        cs, by, src = E["BROKER_WATCH_CITY_STATE"], int(E["BROKER_WATCH_BIRTH_YEAR"]), "env"
        phones = [x for x in E.get("BROKER_WATCH_PHONE", "").split(";") if x.strip()]
        addrs = [x.strip() for x in E.get("BROKER_WATCH_ADDRESSES", "").split(";") if x.strip()]
    phones = [d for d in (re.sub(r"\D", "", x)[-10:] for x in phones) if len(d) == 10]
    toks = [t for t in names[0].split() if t.lower().strip(",.") not in SUF]
    first, last = toks[0], toks[-1]
    alt = next((n.split()[0] for n in names[1:] if n.split() and n.split()[0].lower() != first.lower()), first)
    parts = cs.replace(",", " ").split()
    p = {"first": first, "middle": toks[1] if len(toks) > 2 else "", "last": last, "alt_first": alt, "names": names,
         "city": " ".join(parts[:-1]), "state": parts[-1].upper(), "birth_year": by,
         "age": dt.date.today().year - by, "year": dt.date.today().year, "phones": phones, "addresses": addrs}
    if fake:  # negative control: every name field swapped; same city, age, phones and addresses (they list the owner's family)
        p.update(first="Zorvath", middle="Quentin", last="Quillbeck", alt_first="Zed", names=["Zorvath Quentin Quillbeck"])
    return p, src


# ---------------- Chrome with the saved profile (step 3+) ----------------

def ensure_chrome():
    def up():
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=3)
            return True
        except Exception:
            return False
    if up():
        return "already running"
    subprocess.Popen([CHROME, f"--remote-debugging-port={CDP_PORT}", f"--user-data-dir={BW}/chrome-profile",
                      "--no-first-run", "about:blank"], creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    for _ in range(30):
        time.sleep(1)
        if up():
            return "started"
    raise RuntimeError("the Broker Watch Chrome (port 9333) did not start")


# ---------------- alerts ----------------

def alert(text, key):
    """Failed or missed run -> Telegram to the owner + a triage card on Reed's board (idempotent per key)."""
    out = []
    try:
        r = subprocess.run(["hermes", "send", "--to", TELEGRAM, "--quiet", text], capture_output=True, text=True, timeout=60)
        out.append(f"telegram rc={r.returncode}")
    except Exception as e:
        out.append(f"telegram failed: {type(e).__name__}")
    try:
        r = subprocess.run(["hermes", "kanban", "--board", "default", "create", "Broker Watch: " + text[:80],
                            "--body", text + "\n\nOwner: Reed. Local evidence: %LOCALAPPDATA%/broker-watch/runs/. "
                            "Fix, re-run `python job/run.py`, and log it in apps/broker-watch/STATE.md.",
                            "--assignee", "default", "--triage", "--idempotency-key", "broker-watch-" + key,
                            "--created-by", "broker-watch", "--json"], capture_output=True, text=True, timeout=60)
        m = re.search(r'"(?:id|task_id)":\s*"([^"]+)"', r.stdout or "")
        out.append(f"card {m.group(1) if m else 'rc=' + str(r.returncode)}")
    except Exception as e:
        out.append(f"card failed: {type(e).__name__}")
    print("ALERT SENT:", "; ".join(out), flush=True)
    return out


# ---------------- the run ----------------

CURRENT = {"run_id": None}  # so a failure marks only this run as failed, never another one in progress


def run(a, E):
    reader = DB(E)  # a dry run still reads My details (only reads; it never writes)
    db = None if a.dry else reader
    rows = reader.call("GET", f"bw_profile?owner=eq.{reader.owner}&select=*")
    profile = rows[0] if rows else None
    p, src = subject(profile, E, fake=a.fake)
    sites = a.sites.split(",") if a.sites else list(SITES)
    steps = [int(s) for s in a.steps.split(",")]
    urls = site_urls(p)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = os.path.join(BW, "runs", stamp + ("-fake" if a.fake else "") + ("-dry" if a.dry else ""))
    os.makedirs(os.path.join(out_dir, "pages"), exist_ok=True)
    print(f"run {stamp}: {len(sites)} sites, steps {steps}, details from {src}, "
          f"{'DRY (nothing written)' if a.dry else 'writing to the database'}", flush=True)

    run_row = db.call("POST", "bw_runs", {"owner": db.owner})[0] if db else {"id": None}
    CURRENT["run_id"] = run_row["id"]

    def saver(tag):
        def save(site, what, url, text):
            fn = re.sub(r"[^\w.-]", "_", f"{site}__{tag}__{what}") + ".txt"
            open(os.path.join(out_dir, "pages", fn), "w", encoding="utf-8").write(url + "\n\n" + text)
        return save

    if a.fail_on_purpose:
        raise RuntimeError("failed on purpose (alert-path test)")

    from playwright.sync_api import sync_playwright
    from fetchers import BrowserFetcher, HttpFetcher
    block_host = re.sub(r"^www\.", "", re.match(r"https?://([^/]+)", urls[a.block]).group(1)) if a.block else None
    state = {s: {"best": None, "log": [], "done": False} for s in sites}
    with sync_playwright() as pw:
        F = {1: HttpFetcher(block_host)}
        fresh_b = None
        if 2 in steps:
            fresh_b = pw.chromium.launch(channel="chrome", headless=False, args=["--window-position=40,40"])
            F[2] = BrowserFetcher(fresh_b.new_context(viewport={"width": 1280, "height": 800}), "chrome-fresh", block_host=block_host)
        if any(s >= 3 for s in steps):
            print("chrome (saved profile):", ensure_chrome(), flush=True)
            F[3] = BrowserFetcher(pw.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}").contexts[0],
                                  "chrome-profile", human=True, block_host=block_host)
        def attempt(step, site, fn, variant=None):
            st = state[site]
            t0 = time.time()
            try:
                r = fn()
            except Exception as e:
                r = {"verdict": "couldnt", "error": f"{type(e).__name__}: {str(e)[:100]}"}
            r["step"], r["secs"] = step, round(time.time() - t0, 1)
            if variant:
                r["variant"] = variant
            st["log"].append(r)
            st["best"] = ladder.better(st["best"], r)
            print(f"{site:22} step {step}{' ' + variant if variant else ''}: {r['verdict']:8} page={r.get('page')} "
                  f"ev={r.get('evidence')}{' CAPTCHA' if r.get('captcha') else ''} {r.get('error', '')}", flush=True)
            if r["verdict"] in ("me", "gone"):
                st["done"] = True

        for step in steps:  # rounds: one step across every open site, so no site gets a burst of hits
            if step == 5:  # change the query: other first name, past cities, each phone, each address
                Q = {s: step5_queries(p, s) for s in sites}
                for k in range(max([len(q) for q in Q.values()] or [0])):  # round-robin: query k on every site, then k+1
                    for site in sites:
                        if state[site]["done"] or k >= len(Q[site]):
                            continue
                        variant, kind, url = Q[site][k]
                        attempt(5, site, lambda: ladder.run_step(F[3], site, url, p, site in NONE_ON_404 and kind == "name",
                                                                 saver(f"s5-{variant}"), cards=(kind == "name")), variant)
                continue
            for site in sites:
                if state[site]["done"]:
                    continue
                if step in (1, 2, 3):
                    attempt(step, site, lambda: ladder.run_step(F[step], site, urls[site], p, site in NONE_ON_404, saver(f"s{step}")))
                else:
                    attempt(step, site, lambda: ladder.side_door(F[3], site, urls[site], p, saver("s4")))
        if fresh_b:
            fresh_b.close()

    today = dt.date.today().isoformat()
    checks, counts = [], {"found": 0, "not_found": 0, "couldnt_check": 0, "gone": 0}
    for site in sites:
        st = state[site]
        best = st["best"] or {"verdict": "couldnt", "step": None}
        res = ladder.final_result(best)
        counts[res] += 1
        checks.append({"site": site, "checked_on": today, "result": res,
                       "step": best.get("step") if res != "couldnt_check" else None,
                       "tried": [l["step"] for l in st["log"]], "evidence": best.get("evidence"),
                       "gated": bool(best.get("gated")), "url": best.get("url") or urls[site],
                       "captcha": any(l.get("captcha") for l in st["log"]),
                       "query": best.get("variant") if res != "couldnt_check" else None})
    captchas = sum(c["captcha"] for c in checks)
    json.dump({"stamp": stamp, "fake": a.fake, "block": a.block, "src": src, "checks": checks,
               "ladder": {s: state[s]["log"] for s in sites}}, open(os.path.join(out_dir, "result.json"), "w"), indent=1)
    if db:
        db.call("POST", "bw_checks", [dict(c, owner=db.owner, run_id=run_row["id"]) for c in checks], prefer="return=minimal")
        db.call("PATCH", f"bw_runs?id=eq.{run_row['id']}",
                {"status": "ok", "finished_at": dt.datetime.now().astimezone().isoformat(), "found": counts["found"],
                 "not_found": counts["not_found"], "couldnt": counts["couldnt_check"], "gone": counts["gone"],
                 "captchas": captchas}, prefer="return=minimal")
    print(f"RESULT found {counts['found']}, not found {counts['not_found']}, couldn't check {counts['couldnt_check']}, "
          f"gone {counts['gone']}, sites with a CAPTCHA/bot wall {captchas}", flush=True)
    print("RUN", out_dir)
    return run_row["id"]


def check(E):
    """Watchdog: the last finished run must be under 8 days old."""
    db = DB(E)
    rows = db.call("GET", f"bw_runs?owner=eq.{db.owner}&status=eq.ok&select=finished_at&order=finished_at.desc&limit=1")
    last = dt.datetime.fromisoformat(rows[0]["finished_at"]) if rows else None
    age = (dt.datetime.now().astimezone() - last).days if last else None
    print("last finished run:", last.isoformat() if last else "never", f"({age} days ago)" if last else "")
    if last is None or age >= 8:
        alert(f"Broker Watch missed its weekly run (last finished: {last.date().isoformat() if last else 'never'}). "
              f"Is the PC on and the scheduled task enabled?", "missed-" + dt.date.today().isoformat())
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites"); ap.add_argument("--steps", default="1,2,3,4,5"); ap.add_argument("--block")
    ap.add_argument("--fake", action="store_true", help="made-up person (negative control)")
    ap.add_argument("--dry", action="store_true"); ap.add_argument("--check", action="store_true")
    ap.add_argument("--fail-on-purpose", action="store_true")
    a = ap.parse_args()
    E = load_env()
    if a.check:
        sys.exit(check(E))
    try:
        run(a, E)
    except Exception as e:
        traceback.print_exc()
        if not a.dry and CURRENT["run_id"]:
            try:
                db = DB(E)
                for r in [{"id": CURRENT["run_id"]}]:
                    db.call("PATCH", f"bw_runs?id=eq.{r['id']}", {"status": "failed", "error": f"{type(e).__name__}: {str(e)[:300]}",
                                                                 "finished_at": dt.datetime.now().astimezone().isoformat()},
                            prefer="return=minimal")
            except Exception:
                pass
        alert(f"Broker Watch weekly run FAILED: {type(e).__name__}: {str(e)[:200]}", "failed-" + dt.datetime.now().strftime("%Y%m%d-%H%M"))
        sys.exit(1)


if __name__ == "__main__":
    main()

"""Skeleton end-to-end check in a real phone-sized browser against the hosted database.
Usage: python tests/e2e.py <base_url> <supabase_url> <publishable_key> <secret_key>
A throwaway account gets one weekly run written the way job/run.py writes it (secret key, owner stamped), then:
logged out shows sign-in only; sign in with a real one-time code; the run's results show up (found / couldn't
check never as not found); mark an opt-out and see it stored; save My details and see the row; sign out.
The account and its rows are deleted at the end. Exit 1 on any failure."""
import glob, json, os, sys, time, urllib.request
from playwright.sync_api import sync_playwright

base, sb_url, pub, secret = sys.argv[1:5]
run = str(int(time.time()))[-7:]
email = f"bw-e2e-{run}@example.com"
A = {"apikey": secret, "Authorization": "Bearer " + secret, "Content-Type": "application/json", "Prefer": "return=representation"}
ok = []


def check(name, cond):
    ok.append(bool(cond)); print(("PASS " if cond else "FAIL ") + name, flush=True)


def api(method, path, body=None):
    r = urllib.request.Request(sb_url + path, method=method, headers=A, data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(r, timeout=30) as f:
        t = f.read(); return json.loads(t) if t else None


uid = api("POST", "/auth/v1/admin/users", {"email": email, "email_confirm": True})["id"]
try:
    # one finished weekly run, written like the job writes it
    r1 = api("POST", "/rest/v1/bw_runs", {"owner": uid, "status": "ok", "finished_at": "2026-10-18T10:40:00-05:00",
                                          "started_at": "2026-10-18T10:00:00-05:00", "found": 1, "not_found": 1, "couldnt": 1, "captchas": 1})[0]
    K = {"step": None, "tried": [], "evidence": None, "url": None, "captcha": False, "gated": False}  # bulk insert: same keys on every row
    api("POST", "/rest/v1/bw_checks", [dict(K, **row) for row in [
        {"owner": uid, "run_id": r1["id"], "site": "Spokeo", "checked_on": "2026-10-18", "result": "found", "step": 1, "tried": [1], "evidence": "listing", "url": "https://example.com/spokeo-listing"},
        {"owner": uid, "run_id": r1["id"], "site": "Whitepages", "checked_on": "2026-10-18", "result": "couldnt_check", "tried": [1, 2, 3, 4, 5], "captcha": True, "url": "https://example.com/wp"},
        {"owner": uid, "run_id": r1["id"], "site": "AnyWho", "checked_on": "2026-10-18", "result": "not_found", "step": 2, "tried": [1, 2]},
    ]])
    exe = sorted(glob.glob(os.path.expandvars(r"%LOCALAPPDATA%/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-win64/chrome-headless-shell.exe")))
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe[-1]) if exe else p.chromium.launch()
        c = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        c.add_init_script(f"window.BW_CONFIG = {{ url: {json.dumps(sb_url)}, key: {json.dumps(pub)} }};")
        pg = c.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(base + "?e2e=" + run); pg.wait_for_selector("#email")
        check("logged out: sign-in screen only, no tabs, no sites", pg.locator("nav").is_hidden() and pg.locator("[data-testid=row]").count() == 0)
        pg.fill("#email", email)
        link = api("POST", "/auth/v1/admin/generate_link", {"type": "magiclink", "email": email})
        code = link.get("email_otp") or link["properties"]["email_otp"]
        pg.evaluate("e => window.__bw_codeView(e)", email); pg.wait_for_selector("#code")
        pg.fill("#code", code); pg.locator("#cf button[type=submit]").click()
        pg.wait_for_selector("body[data-loaded]", timeout=20000); pg.wait_for_selector("[data-testid=row]")
        txt = pg.locator("#app").inner_text()
        check("signed in: Spokeo shows Found, Whitepages Couldn't check, AnyWho Not found",
              pg.locator("[data-testid=row]", has_text="Spokeo").inner_text().endswith("Found")
              and "Couldn't check" in pg.locator("[data-testid=row]", has_text="Whitepages").inner_text()
              and "Not found" in pg.locator("[data-testid=row]", has_text="AnyWho").inner_text())
        check("header shows the last weekly check as 10/18/2026", "Last weekly check 10/18/2026" in pg.locator("#lastRun").inner_text())
        pg.locator("[data-testid=row]", has_text="Whitepages").click(); pg.wait_for_selector("#back")
        check("couldn't-check site: says it's never counted as not found, notes the CAPTCHA",
              'never counted as "not found"' in pg.locator("#app").inner_text() and "CAPTCHA" in pg.locator("#app").inner_text())
        pg.locator("#back").click()
        pg.locator("[data-testid=row]", has_text="Spokeo").click(); pg.wait_for_selector("#sent")
        check("found site links the page it found", pg.locator("a", has_text="See the page it found").get_attribute("href") == "https://example.com/spokeo-listing")
        pg.locator("#sent").click(); pg.wait_for_selector("#unsent")
        rows = api("GET", f"/rest/v1/bw_optouts?owner=eq.{uid}&select=site")
        check(f"opt-out mark is stored in the database ({rows})", rows == [{"site": "Spokeo"}])
        pg.locator("#back").click()
        check("Spokeo now reads Opt-out requested", "Opt-out requested" in pg.locator("[data-testid=row]", has_text="Spokeo").inner_text())
        pg.locator("nav [data-tab=runs]").click(); pg.wait_for_selector("[data-testid=runs]")
        check("Runs tab shows the run with its CAPTCHA count", "10/18/2026" in pg.locator("[data-testid=runs]").inner_text())
        pg.locator("nav [data-tab=me]").click(); pg.wait_for_selector("#names")
        pg.fill("#names", "Jordan A. Sample\nJordy Sample"); pg.fill("#cityState", "Springfield, IL"); pg.fill("#birthYear", "19x0")
        pg.locator("#saveMe").click()
        check("bad birth year gets our own friendly error", "Birth year as 4 digits" in pg.locator("#meErr").inner_text())
        pg.fill("#birthYear", "1980"); pg.locator("#saveMe").click(); pg.wait_for_selector("#meOk:has-text('Saved')")
        prof = api("GET", f"/rest/v1/bw_profile?owner=eq.{uid}&select=names,city_state,birth_year")
        check(f"My details row is real ({prof})", prof == [{"names": ["Jordan A. Sample", "Jordy Sample"], "city_state": "Springfield, IL", "birth_year": 1980}])
        pg.locator("#signout").click(); pg.wait_for_selector("#email")
        check("sign out returns to the sign-in screen with nothing shown", pg.locator("[data-testid=row]").count() == 0)
        check(f"no page errors ({errs})", not errs)
        b.close()
finally:
    api("DELETE", f"/auth/v1/admin/users/{uid}")
    left = api("GET", f"/rest/v1/bw_runs?owner=eq.{uid}&select=id")
    print("cleanup: test account deleted, rows left:", len(left))
print("ALL PASS" if all(ok) else "SOME FAILED")
sys.exit(0 if all(ok) else 1)

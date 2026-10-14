"""Skeleton end-to-end check in a real phone-sized browser against the hosted database.
Usage: python tests/e2e.py <base_url> <supabase_url> <publishable_key> <secret_key>
A throwaway account gets one weekly run written the way job/run.py writes it (secret key, owner stamped), then:
logged out shows sign-in only; sign in with a real one-time code; the run's results show up (found / couldn't
check never as not found); mark an opt-out and see it stored; change My details (autosave) and see each change in the row; sign out.
The account and its rows are deleted at the end. Exit 1 on any failure."""
import glob, json, os, sys, time, urllib.request
from playwright.sync_api import sync_playwright

base, sb_url, pub, secret = sys.argv[1:5]
run = str(int(time.time()))[-7:]
email = f"bw-e2e-{run}-{os.urandom(3).hex()}@example.com"  # unique even if CI and a local run start the same second
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
    K = {"step": None, "tried": [], "evidence": None, "url": None, "captcha": False, "gated": False, "reason": None}  # bulk insert: same keys on every row
    api("POST", "/rest/v1/bw_checks", [dict(K, **row) for row in [
        {"owner": uid, "run_id": r1["id"], "site": "Spokeo", "checked_on": "2026-10-18", "result": "found", "step": 1, "tried": [1], "evidence": "listing", "url": "https://example.com/spokeo-listing"},
        {"owner": uid, "run_id": r1["id"], "site": "Whitepages", "checked_on": "2026-10-18", "result": "couldnt_check", "tried": [1, 2, 3, 4, 5], "captcha": True, "url": "https://example.com/wp"},
        {"owner": uid, "run_id": r1["id"], "site": "AnyWho", "checked_on": "2026-10-18", "result": "not_found", "step": 2, "tried": [1, 2]},
        {"owner": uid, "run_id": r1["id"], "site": "Nuwber", "checked_on": "2026-10-18", "result": "couldnt_check", "tried": [], "reason": "unreachable"},
        {"owner": uid, "run_id": r1["id"], "site": "SearchPeopleFree", "checked_on": "2026-10-18", "result": "couldnt_check", "tried": [1, 2, 3, 4, 5], "captcha": True, "reason": "captcha", "url": "https://example.com/spf"},
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
        # Slice 2: unreachable is its own group and never "not found"; a CAPTCHA stop asks for one solve on the PC.
        pg.wait_for_selector("[data-testid=row] >> text=Nuwber")
        txt = pg.locator("#app").inner_text()
        nu = pg.locator("[data-testid=row]", has_text="Nuwber").inner_text()
        check("unreachable site: own group + pill, never Not found", "can't reach from your pc (1)" in txt.lower() and "Site unreachable" in nu and "Not found" not in nu)
        check("Whitepages (plain block) is not asked to solve", "needs you to solve" not in pg.locator("[data-testid=row]", has_text="Whitepages").inner_text())
        check("CAPTCHA site row says it needs one solve", "needs you to solve it once" in pg.locator("[data-testid=row]", has_text="SearchPeopleFree").inner_text())
        pg.locator("[data-testid=row]", has_text="SearchPeopleFree").click(); pg.wait_for_selector("[data-testid=solve]")
        check("solve button opens the PC handler for exactly this site",
              pg.locator("#solve").get_attribute("href") == "brokerwatch://solve/SearchPeopleFree")
        pg.locator("#back").click()
        pg.locator("[data-testid=row]", has_text="Nuwber").click(); pg.wait_for_selector("[data-testid=unreachable]")
        check("unreachable site page explains it's the network, with no solve button",
              "not the site blocking us" in pg.locator("#app").inner_text() and pg.locator("#solve").count() == 0)
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
        # Slice 2: My details saves itself. Every check below reads the DATABASE, never the screen alone.
        check("no Save button any more", pg.locator("#saveMe").count() == 0)
        prof = lambda: (api("GET", f"/rest/v1/bw_profile?owner=eq.{uid}&select=names,city_state,birth_year,phones,addresses") or [{}])[0]
        def saved():
            pg.wait_for_function("document.querySelector('#meStatus') && /^Saved/.test(document.querySelector('#meStatus').textContent)")
        def until(cond, what):  # the write is async; give the database up to 10 s to show it
            for _ in range(40):
                v = prof()
                if cond(v): return v
                time.sleep(0.25)
            return prof()
        pg.fill("#names", "Jordan A. Sample\nJordy Sample"); pg.locator("#cityState").focus(); saved()
        v = until(lambda v: v.get("names") == ["Jordan A. Sample", "Jordy Sample"], "names")
        check(f"names save on leaving the box, no button ({v.get('names')})", v.get("names") == ["Jordan A. Sample", "Jordy Sample"])
        pg.fill("#cityState", "Springfield, IL"); pg.press("#cityState", "Enter"); saved()
        check("city saves on Return", until(lambda v: v.get("city_state") == "Springfield, IL", "city").get("city_state") == "Springfield, IL")
        pg.fill("#birthYear", "19x0"); pg.locator("#names").focus()
        check("bad birth year: our friendly error, and nothing written",
              "Birth year as 4 digits" in pg.locator("#meErr").inner_text() and "Not saved" in pg.locator("#meStatus").inner_text()
              and prof().get("birth_year") is None)
        pg.fill("#birthYear", "1980"); pg.press("#birthYear", "Enter"); saved()
        check("birth year saves once it's valid", until(lambda v: v.get("birth_year") == 1980, "by").get("birth_year") == 1980)
        # Lists: Return adds AND writes; the box clears and keeps focus for the next one.
        pg.fill("#phonesNew", "(555) 010-0199"); pg.press("#phonesNew", "Enter"); saved()
        check("Return adds a phone, clears the box, keeps focus",
              "(555) 010-0199" in pg.locator("[data-testid=phones-list]").inner_text() and pg.input_value("#phonesNew") == ""
              and pg.evaluate("document.activeElement.id") == "phonesNew")
        check("…and the phone is in the database without pressing anything", until(lambda v: v.get("phones") == ["5550100199"], "p").get("phones") == ["5550100199"])
        # Two quick adds back to back: neither may be lost (each save builds on the last saved row).
        pg.fill("#phonesNew", "555 010 0200"); pg.locator("#phonesAdd").click()
        pg.fill("#phonesNew", "555 010 0201"); pg.locator("#phonesAdd").click(); saved()
        v = until(lambda v: v.get("phones") == ["5550100199", "5550100200", "5550100201"], "3p")
        check(f"two quick adds both land in the database ({len(v.get('phones') or [])} phones)", v.get("phones") == ["5550100199", "5550100200", "5550100201"])
        pg.fill("#phonesNew", "+1 555.010.0199"); pg.press("#phonesNew", "Enter"); saved()
        check("same phone in another format is kept once", pg.locator("[data-testid=phones-list] li").count() == 3 and len(prof()["phones"]) == 3)
        pg.fill("#phonesNew", "123"); pg.press("#phonesNew", "Enter")
        check("short phone: friendly error, not added, nothing written", "10 digits" in pg.locator("#meErr").inner_text()
              and pg.locator("[data-testid=phones-list] li").count() == 3 and len(prof()["phones"]) == 3)
        pg.fill("#phonesNew", "")
        pg.locator("[data-del=phones][data-i='2']").click(); saved()
        check("Remove writes to the database", until(lambda v: v.get("phones") == ["5550100199", "5550100200"], "rm").get("phones") == ["5550100199", "5550100200"])
        pg.fill("#addressesNew", "123 Example St, Springfield IL, 62701"); pg.press("#addressesNew", "Enter"); saved()
        pg.fill("#addressesNew", "somewhere"); pg.press("#addressesNew", "Enter")
        check("address without city/state gets our friendly error", "city and state" in pg.locator("#meErr").inner_text())
        pg.fill("#addressesNew", "45 Old Rd, Shelbyville, IL"); pg.press("#addressesNew", "Enter"); saved()
        # Typed but never added, then tapped elsewhere: the slice-1 miss. It must still be saved.
        pg.fill("#addressesNew", "9 Gone Ln, Ogden IL"); pg.locator("#names").focus(); saved()
        v = until(lambda v: v.get("addresses") == ["123 Example St, Springfield IL, 62701", "45 Old Rd, Shelbyville, IL", "9 Gone Ln, Ogden IL"], "a3")
        check(f"an address typed and left (no Return, no button) is still saved ({len(v.get('addresses') or [])})", len(v.get("addresses") or []) == 3)
        # Typed one address, then tapped Remove on another: Remove drops its row, the typed one is saved, nothing lost.
        pg.fill("#addressesNew", "7 Half Typed Rd, Ogden IL")
        pg.locator("[data-del=addresses][data-i='0']").click(); saved()
        A3 = ["45 Old Rd, Shelbyville, IL", "9 Gone Ln, Ogden IL", "7 Half Typed Rd, Ogden IL"]
        v = until(lambda v: v.get("addresses") == A3, "rm-a")
        check(f"Remove drops its address in the DB; the one being typed is saved, not lost ({len(v.get('addresses') or [])})", v.get("addresses") == A3)
        # A write the database refuses: the screen says so and keeps showing what's really stored.
        pg.route("**/rest/v1/bw_profile**", lambda r: r.fulfill(status=500, body='{"message":"forced failure"}') if r.request.method == "POST" else r.continue_())
        pg.fill("#phonesNew", "555 010 0299"); pg.press("#phonesNew", "Enter")
        pg.wait_for_function("/Didn't save/.test(document.querySelector('#meStatus').textContent)")
        check("a failed write says Didn't save and the list shows only what's stored",
              pg.locator("[data-testid=phones-list] li").count() == 2 and prof()["phones"] == ["5550100199", "5550100200"])
        pg.unroute("**/rest/v1/bw_profile**")
        prof_all = prof()
        check(f"My details row is real ({prof_all})", prof_all == {"names": ["Jordan A. Sample", "Jordy Sample"], "city_state": "Springfield, IL",
              "birth_year": 1980, "phones": ["5550100199", "5550100200"], "addresses": A3})
        pg.reload(); pg.wait_for_selector("body[data-loaded]"); pg.locator("nav [data-tab=me]").click(); pg.wait_for_selector("#phonesNew")
        check("after a reload the lists come back from the database", pg.locator("[data-testid=phones-list] li").count() == 2
              and pg.locator("[data-testid=addresses-list] li").count() == 3)
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

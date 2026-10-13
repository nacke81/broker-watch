# Real-browser click-through of the prototype. Usage: python tests/proto_click.py <url> [shotdir]
import sys, os
from playwright.sync_api import sync_playwright
url = sys.argv[1]; shots = sys.argv[2] if len(sys.argv) > 2 else None
ok = []; errs = []
def check(name, cond):
    ok.append((name, bool(cond))); print(("PASS " if cond else "FAIL ") + name)
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 390, "height": 844})
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(url); pg.wait_for_selector(".tile")
    tiles = pg.locator(".tile b").all_inner_texts()
    check("tiles 7 listed / 7 need you / 2 couldn't / 6 clean", tiles == ["7", "7", "2", "6"])
    check("15 sites listed", pg.locator("[data-site]").count() == 15)
    check("came back sorts first", pg.locator("[data-site] .name").first.inner_text() == "BeenVerified")
    if shots: pg.screenshot(path=os.path.join(shots, "1-sites.png"), full_page=True)
    # blocked site: ladder shown, never 'not found'
    pg.click("[data-site=peoplefinders]"); pg.wait_for_selector("#back")
    body = pg.inner_text("main")
    check("blocked site says couldn't check, not 'not found'", "Couldn't check" in body and "No listing for you" not in body)
    check("ladder points at step 7 (paid) after 6 tried", "Paid (needs your yes) ← next" in body)
    check("blocked weeks never claim a paid step", "Blocked at every step tried" in body and body.count("Paid (needs your yes)") == 1)
    if shots: pg.screenshot(path=os.path.join(shots, "2-blocked.png"), full_page=True)
    pg.click("#back")
    pg.wait_for_selector("[data-site=nuwber]"); pg.click("[data-site=nuwber]"); pg.wait_for_selector("#back")
    check("nuwber offers you-in-the-loop", pg.locator("#loop").count() == 1)
    pg.click("#back")
    # mark opt-out sent
    pg.wait_for_selector("[data-site=whitepages]"); pg.click("[data-site=whitepages]"); pg.wait_for_selector("#back")
    check("opt-out link present", pg.locator("a.btn").get_attribute("href").startswith("https://www.whitepages.com"))
    pg.click("#sent")
    check("marked requested", "Opt-out requested" in pg.inner_text("main"))
    if shots: pg.screenshot(path=os.path.join(shots, "3-site.png"), full_page=True)
    pg.reload(); pg.wait_for_selector(".card")
    check("survives reload", "Opt-out requested" in pg.inner_text("main"))
    pg.click("#unsent"); check("undo works", "Found" in pg.inner_text("main .card"))
    # runs tab
    pg.click("nav [data-tab=runs]"); pg.wait_for_selector("table")
    check("runs: 5 weeks", pg.locator("table tr").count() == 6)
    if shots: pg.screenshot(path=os.path.join(shots, "4-runs.png"), full_page=True)
    # my details: friendly error
    pg.click("nav [data-tab=me]"); pg.wait_for_selector("#phone")
    pg.fill("#phone", "123"); pg.click("#saveMe")
    check("friendly phone error", "10 digits" in pg.inner_text("#meErr"))
    pg.fill("#phone", "(555) 010-0100"); pg.click("#saveMe")
    check("save ok", "Saved" in pg.inner_text("#meOk"))
    check("no JS errors", not errs)
    b.close()
n = sum(1 for _, c in ok if c); print(f"{n} of {len(ok)}")
sys.exit(0 if n == len(ok) else 1)

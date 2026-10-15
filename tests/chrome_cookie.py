r"""Cookie-survival test (Windows, needs Chrome). Uses a SCRATCH profile and port 9444: the real chrome-profile is never touched.
Launches Chrome through run.ensure_chrome(), sets a persistent cookie, calls the real run.stop_chrome() immediately,
relaunches on the same profile, and asserts the cookie is still there. A hard kill loses it (Chrome flushes cookies on a ~30s timer).

  python tests/chrome_cookie.py [--job PATH]    --job: a different job dir's run.py (positive control on an old commit)
"""
import os, shutil, sys, tempfile, time, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
job = sys.argv[sys.argv.index("--job") + 1] if "--job" in sys.argv else os.path.join(os.path.dirname(HERE), "job", "run.py")
scratch = tempfile.mkdtemp(prefix="bw-cookie-")
os.makedirs(os.path.join(scratch, "chrome-profile"))
os.environ.update(BW_CDP_PORT="9444", BW_PROFILE_DIR=os.path.join(scratch, "chrome-profile"))
sys.path.insert(0, os.path.dirname(job))
spec = importlib.util.spec_from_file_location("bw_run_under_test", job)
R = importlib.util.module_from_spec(spec); spec.loader.exec_module(R)
R.CDP_PORT = 9444; R.BW = scratch  # old versions build the profile path from BW at call time
if hasattr(R, "PROFILE_DIR"):
    R.PROFILE_DIR = os.path.join(scratch, "chrome-profile")
assert R.CDP_PORT == 9444 and not R.cdp_up(), "scratch port 9444 must be free"

from playwright.sync_api import sync_playwright
ok = False
try:
    print("launch:", R.ensure_chrome(), flush=True)
    with sync_playwright() as pw:
        ctx = pw.chromium.connect_over_cdp("http://127.0.0.1:9444").contexts[0]
        ctx.add_cookies([{"name": "bw_clearance", "value": "solved-123", "domain": "bw-test.example", "path": "/",
                          "expires": int(time.time()) + 86400}])
        print("cookie set; stopping immediately", flush=True)
        t0 = time.time()
        R.stop_chrome()
        print(f"stop_chrome took {time.time() - t0:.1f}s", flush=True)
    assert not R.cdp_up(), "Chrome still up after stop_chrome"
    print("relaunch:", R.ensure_chrome(), flush=True)
    with sync_playwright() as pw:
        ctx = pw.chromium.connect_over_cdp("http://127.0.0.1:9444").contexts[0]
        got = [c for c in ctx.cookies() if c["name"] == "bw_clearance"]
    print("cookie after relaunch:", got and got[0]["value"] or "LOST")
    ok = bool(got) and got[0]["value"] == "solved-123"
finally:
    R.STARTED["pid"] = R.STARTED["pid"] or None
    R.stop_chrome()
    time.sleep(1)
    shutil.rmtree(scratch, ignore_errors=True)
print("chrome_cookie", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)

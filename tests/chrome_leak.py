r"""Chrome leak test (Windows, needs Chrome + the real .env; reads only, --dry writes nothing).
Runs job/run.py --dry --steps 2,3 on one site and counts chrome.exe processes that belong to Broker Watch
(command line has broker-watch\chrome-profile or --broker-watch-fresh) before and after. After must equal before.

  python tests/chrome_leak.py ok          happy path
  python tests/chrome_leak.py crash       exception injected after the first site
  python tests/chrome_leak.py preexisting a Chrome already on 9333 (not ours) must survive the run
  --job PATH   run a different run.py (positive control on a reverted copy)
"""
import json, os, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BW = os.path.expandvars(r"%LOCALAPPDATA%/broker-watch")
CHROME = r"C:/Program Files/Google/Chrome/Application/chrome.exe"


def mine():
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
        "Get-CimInstance Win32_Process -Filter \"name='chrome.exe'\" | Select ProcessId,CommandLine | ConvertTo-Json -Compress"],
        capture_output=True, text=True).stdout.strip()
    rows = json.loads(out) if out else []
    rows = [rows] if isinstance(rows, dict) else rows
    return sorted(r["ProcessId"] for r in rows
                  if "chrome-profile" in (r["CommandLine"] or "").replace("/", "\\") and "broker-watch" in (r["CommandLine"] or "").replace("/", "\\")
                  or "--broker-watch-fresh" in (r["CommandLine"] or ""))


def up():
    try:
        urllib.request.urlopen("http://127.0.0.1:9333/json/version", timeout=3)
        return True
    except Exception:
        return False


def main():
    mode = sys.argv[1]
    job = sys.argv[sys.argv.index("--job") + 1] if "--job" in sys.argv else os.path.join(ROOT, "job", "run.py")
    env = dict(os.environ, BW_TEST_NO_ALERT="1", PYTHONIOENCODING="utf-8")
    pre = None
    if mode == "crash":
        env["BW_TEST_RAISE_AFTER_FIRST_SITE"] = "1"
    if mode == "preexisting":
        pre = subprocess.Popen([CHROME, "--remote-debugging-port=9333", f"--user-data-dir={BW}/chrome-profile", "--no-first-run", "about:blank"])
        for _ in range(30):
            time.sleep(1)
            if up():
                break
        time.sleep(8)  # let its helper processes finish spawning so the before-count is stable
    before = mine()
    print("before:", len(before), before)
    r = subprocess.run([sys.executable, job, "--dry", "--sites", "AnyWho", "--steps", "2,3"], env=env, capture_output=True, text=True, timeout=900)
    print("exit", r.returncode); print((r.stdout + r.stderr)[-600:])
    time.sleep(3)
    after = mine()
    print("after:", len(after), after)
    ok = len(after) == len(before)
    if mode == "preexisting":
        alive = up() and all(p in after for p in before)
        print("pre-existing Chrome still alive:", alive)
        ok = ok and alive
        subprocess.run(["taskkill", "/PID", str(pre.pid), "/T", "/F"], capture_output=True)  # cleanup of our own setup
    print(mode, "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


main()

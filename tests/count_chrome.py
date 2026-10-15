"""Print the pids of Broker Watch chrome.exe processes (same counter as chrome_leak.py)."""
import importlib.util, os
spec = importlib.util.spec_from_file_location("cl", os.path.join(os.path.dirname(os.path.abspath(__file__)), "chrome_leak.py"))
src = open(spec.origin).read().replace("\nmain()", "\nif __name__ == '__main__': main()")
ns = {"__name__": "cl", "__file__": spec.origin}; exec(compile(src, spec.origin, "exec"), ns)
p = ns["mine"](); print(len(p), p)

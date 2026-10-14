"""Real page fetchers for ladder steps 1-3 (ported from the spike). Each .fetch(url, label) returns
(status, final_url, text, links). Every page a fetcher opens is closed again (shared Chrome over CDP)."""
import html as H
import random
import re
from urllib.parse import urljoin

from judge import CONSENT

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"


def html_to_text(src):
    src = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", src)
    src = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|h\d|td|span|a)>", "\n", src)
    t = H.unescape(re.sub(r"<[^>]+>", " ", src))
    return "\n".join(x.strip() for x in t.split("\n") if x.strip())


class HttpFetcher:
    """Step 1: a plain request dressed as a normal browser."""
    name = "http"

    def __init__(self, block_host=None):
        import httpx
        self.c = httpx.Client(headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                                       "Accept-Language": "en-US,en;q=0.9"}, follow_redirects=True, timeout=20)
        self.block = block_host

    def fetch(self, url, label=""):
        if self.block and self.block in url:
            return None, "chrome-error://blocked-on-purpose", "", []
        try:
            r = self.c.get(url)
        except Exception as e:
            return None, "chrome-error://" + type(e).__name__, "", []
        src, links = r.text, []
        for m in re.finditer(r'(?is)<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', src):
            ctx = html_to_text(src[max(0, m.start() - 600):m.end() + 200])
            links.append({"href": urljoin(str(r.url), H.unescape(m.group(1))), "card": ctx[-400:]})
        return r.status_code, str(r.url), html_to_text(src), links

    def close(self):
        self.c.close()


LINKS_JS = r"""() => [...document.querySelectorAll('a[href]')].map(a => {
  let n = a, txt = '';
  for (let i = 0; i < 8 && n; i++, n = n.parentElement) { txt = (n.innerText || ''); if (txt.length > 150) break; }
  return {href: a.href, card: txt.slice(0, 400)};
})"""


class BrowserFetcher:
    """Steps 2-5: real Chrome. human=True paces like a person (step 3+, saved profile)."""

    def __init__(self, ctx, name, human=False, block_host=None):
        self.ctx, self.name, self.human, self.block = ctx, name, human, block_host

    def fetch(self, url, label=""):
        pg = self.ctx.new_page()
        try:
            if self.block:
                pg.route(re.compile(".*" + re.escape(self.block) + ".*"), lambda r: r.abort("connectionrefused"))
            try:
                r = pg.goto(url, timeout=45000, wait_until="domcontentloaded")
                status = r.status if r else None
            except Exception as e:
                return None, "chrome-error://" + type(e).__name__, "", []
            pg.wait_for_timeout(random.randint(5000, 9000) if self.human else 5000)
            for _ in range(2):  # consent walls: click them ourselves
                if not self._consent(pg):
                    break
            if self.human:
                for _ in range(3):
                    pg.mouse.wheel(0, random.randint(300, 700))
                    pg.wait_for_timeout(random.randint(600, 1400))
            try:
                text = pg.inner_text("body", timeout=8000)
            except Exception:
                text = ""
            return status, pg.url, text, pg.evaluate(LINKS_JS)
        finally:
            try:
                pg.close()
            except Exception:
                pass

    def _consent(self, pg):
        for b in pg.query_selector_all("button, a, input[type=button], input[type=submit]"):
            try:
                t = (b.inner_text() or b.get_attribute("value") or "").strip()
                if CONSENT.match(t) and b.is_visible():
                    b.click(timeout=3000)
                    pg.wait_for_timeout(3000)
                    return t
            except Exception:
                pass
        return None

    def close(self):
        pass

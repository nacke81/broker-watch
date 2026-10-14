"""Golden tests 1-3 on saved real pages (PII scrubbed: the subject is "Jordan Avery Sample", Springfield IL).

The pages are the spike's real 2026-10-13/14 results with every identifying word replaced; the judge's verdict
on each was checked identical before and after scrubbing (build_fixtures.py, run locally).
  Golden 1: hand-checked truth set. Pass = at least 80% of the subject's listings found AND 0 of the
            same-name-father sites claimed.
  Golden 2: a made-up person (every name field swapped) is claimed on 0 sites, across every page the live
            run saw for him.
  Golden 3: a site blocked on purpose reports couldn't check, never not found, while another site in the same
            run still finds the subject (positive control).
Plus self-checks that these tests can fail: break the age rule and golden 1 must fail; read every 404 as
"not found" and golden 3's guard must fail.
Exit 1 on any failure.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "job"))
import judge  # noqa: E402
import ladder  # noqa: E402
from sites import NONE_ON_404  # noqa: E402

FX = os.path.join(HERE, "fixtures")
EXP = json.load(open(os.path.join(FX, "expected.json"), encoding="utf-8"))
SUBJ = EXP["subject"]
FAKE = dict(SUBJ, first="Zorvath", middle="Quentin", last="Quillbeck", alt_first="Zed", names=["Zorvath Quentin Quillbeck"])
ok = []


def check(name, cond, detail=""):
    ok.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)


def page(kind, name):
    return open(os.path.join(FX, kind, name), encoding="utf-8").read()


class Fixture:
    """A fetcher that serves saved pages. block=True answers like a refused connection."""
    name = "fixture"

    def __init__(self, text, status=200, block=False):
        self.text, self.status, self.block = text, status, block

    def fetch(self, url, label=""):
        if self.block:
            return None, "chrome-error://blocked-on-purpose", "", []
        return self.status, url, self.text, []


def verdict_on_truth_page(site, row, p):
    t = page("truth", site + ".txt")
    if row["kind"] == "page":
        return judge.classify_page(200, "https://example.com", t, p)
    return (judge.judge_listing if row["kind"] == "listing" else judge.judge_cards)(t, p)["verdict"]


def golden1(p=SUBJ, quiet=False):
    me = [s for s, r in EXP["truth"].items() if r["truth"].startswith("me")]
    father = [s for s, r in EXP["truth"].items() if r["truth"] == "father"]
    found = [s for s in me if verdict_on_truth_page(s, EXP["truth"][s], p) == "me"]
    wrong = [s for s in father if verdict_on_truth_page(s, EXP["truth"][s], p) == "me"]
    if not quiet:
        print(f"GOLDEN 1 SCORE: {len(found)} of {len(me)} found, {len(wrong)} of {len(father)} father sites claimed"
              f" (missed: {sorted(set(me) - set(found))}, wrong: {wrong})")
    return len(found) >= 0.8 * len(me) and not wrong and len(me) == 9 and len(father) == 6


def main():
    # ---- golden 1
    check("GOLDEN 1: >= 80% of the subject's listings found, 0 father sites claimed", golden1())
    gone = [s for s, r in EXP["truth"].items() if r["truth"] == "gone"]
    check("court-order sites read as gone", all(verdict_on_truth_page(s, EXP["truth"][s], SUBJ) == "gone" for s in gone),
          ", ".join(gone))
    # self-check: break the age rule (every age matches) -> father sites get claimed -> golden 1 must fail
    real_age_ok = judge.age_ok
    judge.age_ok = lambda v, kind, age: True
    try:
        check("self-check: with the age rule broken, golden 1 fails", not golden1(quiet=True))
    finally:
        judge.age_ok = real_age_ok

    # ---- golden 2: the made-up person, every page the live run saw for him
    claimed, by_site = [], {}
    for key, e in EXP["fake"].items():
        site = e["site"]
        if e["search"]:
            r = ladder.run_step(Fixture(page("fake", e["search"]), e["http"] or 200), site, "https://example.com/" + site, FAKE,
                                none_on_404=site in NONE_ON_404)
            by_site.setdefault(site, []).append(r)
            if r["verdict"] == "me": claimed.append(key)
        for l in e["listings"]:
            if judge.judge_listing(page("fake", l), FAKE)["verdict"] == "me": claimed.append(key + "/" + l)
    best = {s: ladder.final_result(max(rs, key=lambda r: ladder.RANK[r["verdict"]])) for s, rs in by_site.items()}
    print(f"GOLDEN 2 SCORE: made-up person claimed on {len(claimed)} of {len(by_site)} sites "
          f"({sum(v == 'not_found' for v in best.values())} not found, {sum(v == 'couldnt_check' for v in best.values())} couldn't check,"
          f" {sum(v == 'gone' for v in best.values())} gone)")
    check("GOLDEN 2: made-up person claimed on 0 sites", not claimed and len(by_site) >= 15, str(claimed))
    # also: the real truth pages read as the made-up person -> 0 claims (different name, same pages)
    fp = [s for s, r in EXP["truth"].items() if verdict_on_truth_page(s, r, FAKE) == "me"]
    check("made-up person on the subject's own pages: 0 claimed", not fp, str(fp))

    # ---- golden 3: blocked on purpose = couldn't check; positive control in the same run
    blocked = ladder.run_step(Fixture("", block=True), "ZabaSearch", "https://example.com/z", SUBJ, none_on_404=True)
    control = ladder.run_step(Fixture(page("truth", "ThatsThem.txt")), "ThatsThem", "https://example.com/t", SUBJ)
    print(f"GOLDEN 3: blocked site -> {blocked['verdict']}; positive control (ThatsThem, same run) -> {control['verdict']}")
    check("GOLDEN 3: blocked on purpose reads couldn't check", ladder.final_result(blocked) == "couldnt_check")
    check("GOLDEN 3 control: an unblocked site in the same run still finds the subject", control["verdict"] == "me")

    # ---- the 404 fix (carry item 2): genuine "no such person" 404s read not found, only on proven sites
    bv404 = page("fake", "BeenVerified__s2__search.txt")
    check("404 'no such person' page on a proven site reads not found",
          judge.classify_page(404, "u", bv404, FAKE, none_on_404=True) == "none")
    check("the same 404 on an unproven site stays couldn't check",
          judge.classify_page(404, "u", bv404, FAKE, none_on_404=False) == "blocked")
    wall = page("fake", "Whitepages__s1__search.txt")  # "Just a moment..." bot wall
    check("a bot wall stays couldn't check even on a proven site", judge.classify_page(404, "u", wall, FAKE, none_on_404=True) == "blocked")
    check("a bot wall is logged as a CAPTCHA", judge.is_challenge(wall))
    # self-check: if every 404 read as not found, a blocked-looking 404 would hide; the guard must catch it
    real_cls = judge.classify_page
    ladder.classify_page = lambda s, u, t, p, none_on_404=False: "none" if s == 404 else real_cls(s, u, t, p, none_on_404)
    try:
        r = ladder.run_step(Fixture(wall, 404), "Whitepages", "u", FAKE)
        check("self-check: a 404-means-not-found rule would turn a bot wall into not found", r["verdict"] == "none")
    finally:
        ladder.classify_page = real_cls

    # ---- slice 1: reverse-phone and address pages (ladder step 5) -----------------------------------------
    # They list everyone tied to a number or a house. Only an individual listing may decide "me".
    S1 = json.load(open(os.path.join(FX, "slice1", "slice1.json"), encoding="utf-8"))
    s1 = lambda n: page("slice1", n + ".txt")  # noqa: E731
    for n in ("cbc_address_page", "fps_phone_page", "tps_address_page"):
        r = ladder.run_step(Fixture(s1(n)), n.split("_")[0], "https://example.com/" + n, SUBJ, cards=False)
        check(f"slice 1: {n} with no listing reachable is never claimed (got {r['verdict']})", r["verdict"] != "me")
    # self-check: judging that address page on its cards claims "me" (a relatives list runs into the next
    # person's age). If this ever stops being true, the guard above is no longer proving anything.
    r = ladder.run_step(Fixture(s1("cbc_address_page")), "CyberBackgroundChecks", "https://example.com/a", SUBJ, cards=True)
    check("self-check: card-judging the address page would claim the subject (why cards are off there)",
          r["verdict"] == "me" and S1["cbc_address_page"]["verdict"] == "me")
    check("slice 1: the father's listing reached from his address reads not-me",
          judge.judge_listing(s1("cbc_address_listing_father"), SUBJ)["verdict"] == "other")
    for n in S1:
        fn = judge.judge_listing if S1[n]["kind"] == "listing" else judge.judge_cards
        if n != "cbc_address_page":
            check(f"made-up person on {n}: not claimed", fn(s1(n), FAKE)["verdict"] != "me")

    # step 5 builds a query per phone, past city and address, only on sites that take them
    from sites import step5_queries, parse_address
    P5 = dict(SUBJ, phones=["5550100199", "5550100200"],
              addresses=["1 Elm St, Springfield IL, 62701", "2 Oak Rd, Shelbyville, IL 62565", "3 Pine Ln, Ogden IL", "junk"])
    q = {s: [v for v, _, _ in step5_queries(P5, s)] for s in ("USPhoneBook", "Spokeo", "BeenVerified")}
    check("step 5 on a phone+address site: alt name, 2 past cities, 2 phones, 3 parseable addresses", q["USPhoneBook"] ==
          ["alt-first-name", "past-city-1", "past-city-2", "phone-1", "phone-2", "address-1", "address-2", "address-3"], str(q["USPhoneBook"]))
    check("step 5 on a name-only site: no phone or address queries", q["Spokeo"] == ["alt-first-name", "past-city-1", "past-city-2"]
          and q["BeenVerified"] == ["alt-first-name"], str(q))
    check("step 5 URLs carry the past city and the phone", "Shelbyville" in step5_queries(P5, "Spokeo")[1][2]
          and "555-010-0200" in step5_queries(P5, "USPhoneBook")[4][2])
    check("addresses parse the same way the app does", parse_address("2 Oak Rd, Shelbyville, IL 62565")["city"] == "Shelbyville"
          and parse_address("junk") is None and parse_address("Main St, Ogden IL") is None)

    # the app's site list and opt-out links are generated from job/sites.py: they must match
    import re as _re
    from sites import OPT_OUT
    js = open(os.path.join(HERE, "..", "site", "sites.js"), encoding="utf-8").read()
    app_map = json.loads(_re.search(r"OPT_OUT = (\{.*?\});", js, _re.S).group(1))
    check("app site list matches the job's (20 sites, same opt-out links)", app_map == OPT_OUT and len(OPT_OUT) == 20)

    print("ALL PASS" if all(ok) else "SOME FAILED")
    sys.exit(0 if all(ok) else 1)


if __name__ == "__main__":
    main()

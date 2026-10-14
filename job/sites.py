"""Where each site lists people, and where its opt-out lives. No personal data here: queries are built from the subject."""
from urllib.parse import quote

STATES = {"AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas", "CA": "california", "CO": "colorado", "CT": "connecticut", "DE": "delaware", "FL": "florida", "GA": "georgia", "HI": "hawaii", "ID": "idaho", "IL": "illinois", "IN": "indiana", "IA": "iowa", "KS": "kansas", "KY": "kentucky", "LA": "louisiana", "ME": "maine", "MD": "maryland", "MA": "massachusetts", "MI": "michigan", "MN": "minnesota", "MS": "mississippi", "MO": "missouri", "MT": "montana", "NE": "nebraska", "NV": "nevada", "NH": "new-hampshire", "NJ": "new-jersey", "NM": "new-mexico", "NY": "new-york", "NC": "north-carolina", "ND": "north-dakota", "OH": "ohio", "OK": "oklahoma", "OR": "oregon", "PA": "pennsylvania", "RI": "rhode-island", "SC": "south-carolina", "SD": "south-dakota", "TN": "tennessee", "TX": "texas", "UT": "utah", "VT": "vermont", "VA": "virginia", "WA": "washington", "WV": "west-virginia", "WI": "wisconsin", "WY": "wyoming", "DC": "district-of-columbia"}

OPT_OUT = {
 "Whitepages": "https://www.whitepages.com/suppression-requests",
 "Spokeo": "https://www.spokeo.com/optout",
 "BeenVerified": "https://www.beenverified.com/app/optout/search",
 "TruePeopleSearch": "https://www.truepeoplesearch.com/removal",
 "FastPeopleSearch": "https://www.fastpeoplesearch.com/removal",
 "Radaris": "https://radaris.com/control/privacy",
 "PeopleFinders": "https://www.peoplefinders.com/opt-out",
 "Intelius": "https://suppression.peopleconnect.us/login",
 "MyLife": "https://www.mylife.com/ccpa/index.pubview",
 "ThatsThem": "https://thatsthem.com/optout",
 "Nuwber": "https://nuwber.com/removal/link",
 "ClustrMaps": "https://clustrmaps.com/bl/opt-out",
 "PeekYou": "https://www.peekyou.com/about/contact/optout/",
 "USPhoneBook": "https://www.usphonebook.com/opt-out",
 "CyberBackgroundChecks": "https://www.cyberbackgroundchecks.com/removal",
 "AnyWho": "https://www.anywho.com/optout",
 "FamilyTreeNow": "https://www.familytreenow.com/optout",
 "TruthFinder": "https://www.truthfinder.com/opt-out/",
 "SearchPeopleFree": "https://www.searchpeoplefree.com/opt-out",
 "ZabaSearch": "https://suppression.peopleconnect.us/login"
}

SITES = list(OPT_OUT)

# Sites whose name URL returns a genuine 404 page for a person they don't list (seen on the made-up person,
# while the same URL pattern finds the owner). Only these may read a 404 as "not found".
NONE_ON_404 = {"BeenVerified", "PeopleFinders", "ZabaSearch"}


def site_urls(p, first=None, city=None, state=None):
    F = first or p["first"]; L = p["last"]; M = p["middle"]; Mi = (M[:1] or "")
    f, l, m = F.lower(), L.lower(), M.lower()
    C = city or p["city"]; c = C.lower().replace(" ", "-"); Cd = C.replace(" ", "-")
    ST = state or p["state"]; st = ST.lower(); state = STATES.get(ST, st)
    age = p["age"]; dlo = age // 10 * 10
    return {
        "Whitepages": f"https://www.whitepages.com/name/{F}-{L}/{Cd}-{ST}",
        "Spokeo": f"https://www.spokeo.com/search/{F}-{L}?age_range={dlo}-{dlo+9}&city={quote(C)}&middle_name={M}&state={ST}",
        "BeenVerified": f"https://www.beenverified.com/people/{f}-{l}/",
        "TruePeopleSearch": f"https://www.truepeoplesearch.com/results?name={F}%20{L}&citystatezip={quote(C)},%20{ST}",
        "FastPeopleSearch": f"https://www.fastpeoplesearch.com/name/{f}-{l}_{c}-{st}",
        "Radaris": f"https://radaris.com/p/{F}/{L}/",
        "PeopleFinders": f"https://www.peoplefinders.com/name/{f}-{l}/{st}/{c}",
        "Intelius": f"https://www.intelius.com/results/?firstName={F}&middleInitial={Mi}&lastName={L}&city={quote(C)}&state={ST}&age={age}",
        "MyLife": f"https://www.mylife.com/{f}-{l}/",
        "ThatsThem": f"https://thatsthem.com/name/{F}-{L}/{Cd}-{ST}",
        "Nuwber": f"https://nuwber.com/search?name={F}%20{L}&state={ST}",
        "ClustrMaps": f"https://clustrmaps.com/persons/{F}-{L}",
        "PeekYou": f"https://www.peekyou.com/usa/{st}/{f}_{l}",
        "USPhoneBook": f"https://www.usphonebook.com/{f}-{l}/{st}/{c}",
        "CyberBackgroundChecks": f"https://www.cyberbackgroundchecks.com/people/{F}-{Mi}-{L}/{ST}/{Cd}",
        "AnyWho": f"https://www.anywho.com/people/{f}+{l}/{st}",
        "FamilyTreeNow": f"https://www.familytreenow.com/search/genealogy/results?first={F}&middle={M}&last={L}&citystatezip={quote(C)},%20{ST}",
        "TruthFinder": f"https://www.truthfinder.com/results?firstName={F}&middleInitial=&lastName={L}&city={quote(C)}&state={ST}&age={age}",
        "SearchPeopleFree": f"https://www.searchpeoplefree.com/find/{f}-{m[:1]}-{l}/{st}/{c}",
        "ZabaSearch": f"https://www.zabasearch.com/people/{f}-{l}/{state}/{c}/",
    }


# ---------------- ladder step 5: change the query (slice 1) ----------------
# Reverse-phone and address pages list whoever had that number or lived there (a parent sharing a landline,
# past tenants), so they are only ever a way to reach individual listings, which the judge reads on name + age.
# URL patterns proven on 2026-10-14 (recon: the page came back naming the owner's family, not a redirect or 404).

def _slug(s, sep="-"):
    import re
    return re.sub(r"[^a-z0-9]+", sep, s.lower()).strip(sep)


def _dash(d):
    return f"{d[:3]}-{d[3:6]}-{d[6:]}"


PHONE_URLS = {
    "TruePeopleSearch": lambda d: f"https://www.truepeoplesearch.com/resultphone?phoneno=({d[:3]}){d[3:6]}-{d[6:]}",
    "FastPeopleSearch": lambda d: f"https://www.fastpeoplesearch.com/{_dash(d)}",
    "USPhoneBook": lambda d: f"https://www.usphonebook.com/{_dash(d)}",
    "ThatsThem": lambda d: f"https://thatsthem.com/phone/{_dash(d)}",
    "CyberBackgroundChecks": lambda d: f"https://www.cyberbackgroundchecks.com/phone/{_dash(d)}",
    "ZabaSearch": lambda d: f"https://www.zabasearch.com/phone/{d}",
}

ADDRESS_URLS = {
    "TruePeopleSearch": lambda a: "https://www.truepeoplesearch.com/resultaddress?streetaddress=" + quote(a["street"])
                                  + "&citystatezip=" + quote(f"{a['city']}, {a['state']} {a['zip']}".strip()),
    "FastPeopleSearch": lambda a: f"https://www.fastpeoplesearch.com/address/{_slug(a['street'])}_{_slug(a['city'])}-{a['state'].lower()}"
                                  + (f"-{a['zip']}" if a["zip"] else ""),
    "USPhoneBook": lambda a: f"https://www.usphonebook.com/address/{_slug(a['street'])}/{_slug(a['city'])}-{a['state'].lower()}",
    "ThatsThem": lambda a: f"https://thatsthem.com/address/{_slug(a['street'])}-{_slug(a['city'])}-{a['state']}" + (f"-{a['zip']}" if a["zip"] else ""),
    "CyberBackgroundChecks": lambda a: f"https://www.cyberbackgroundchecks.com/address/{_slug(a['street'])}/{_slug(a['city'])}/{a['state']}",
}

# Name URLs that carry a city (so a past city is a different query).
CITY_IN_URL = {"Whitepages", "Spokeo", "TruePeopleSearch", "FastPeopleSearch", "PeopleFinders", "Intelius", "ThatsThem",
               "USPhoneBook", "CyberBackgroundChecks", "FamilyTreeNow", "TruthFinder", "SearchPeopleFree", "ZabaSearch"}


def parse_address(s):
    """'123 Main St, Springfield IL, 62701' or '123 Main St, Springfield, IL 62701' -> dict, else None (same rule as the app)."""
    import re
    parts = [x.strip() for x in str(s).split(",") if x.strip()]
    if len(parts) < 2 or not re.search(r"\d", parts[0]):
        return None
    m = re.match(r"^([A-Za-z .'-]+?)\s+([A-Za-z]{2})(?:\s+(\d{5})(?:-\d{4})?)?$", re.sub(r"\s+", " ", " ".join(parts[1:])).strip())
    return {"street": parts[0], "city": m.group(1).strip(), "state": m.group(2).upper(), "zip": m.group(3) or ""} if m else None


def step5_queries(p, site):
    """Every changed query for one site, in order: other first name, each past city, each phone, each address.
    Returns [(variant, kind, url)]; kind 'name' pages may be judged on cards, 'phone'/'address' pages only on listings."""
    out, seen = [], set()

    def add(variant, kind, url):
        if url not in seen:
            seen.add(url); out.append((variant, kind, url))
    if p["alt_first"].lower() != p["first"].lower():
        add("alt-first-name", "name", site_urls(p, first=p["alt_first"])[site])
    if site in CITY_IN_URL:
        cities = []
        for a in p.get("addresses", []):
            x = parse_address(a)
            if x and (x["city"].lower(), x["state"]) != (p["city"].lower(), p["state"]) and (x["city"].lower(), x["state"]) not in cities:
                cities.append((x["city"].lower(), x["state"]))
        for i, (c, st) in enumerate(cities):
            add(f"past-city-{i + 1}", "name", site_urls(p, city=c.title(), state=st)[site])
    if site in PHONE_URLS:
        for i, d in enumerate(p.get("phones", [])):
            add(f"phone-{i + 1}", "phone", PHONE_URLS[site](d))
    if site in ADDRESS_URLS:
        for i, a in enumerate(p.get("addresses", [])):
            x = parse_address(a)
            if x:
                add(f"address-{i + 1}", "address", ADDRESS_URLS[site](x))
    return out

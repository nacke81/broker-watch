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


def site_urls(p, first=None):
    F = first or p["first"]; L = p["last"]; M = p["middle"]; Mi = (M[:1] or "")
    f, l, m = F.lower(), L.lower(), M.lower()
    C = p["city"]; c = C.lower().replace(" ", "-"); Cd = C.replace(" ", "-")
    ST = p["state"]; st = ST.lower(); state = STATES.get(ST, st)
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

// FAKE DATA for the prototype. "Jordan Sample" is made up. No real person's details live here.
const W = ['2026-09-15', '2026-09-22', '2026-09-29', '2026-10-06', '2026-10-13'];
const F = 'found', N = 'not_found', C = 'couldnt_check';
const run = (results, steps) => results.map((r, i) => ({ date: W[i], result: r, step: steps[i] ?? steps[steps.length - 1] }));

export const PERSON = {
  names: ['Jordan Sample', 'Jordan A. Sample', 'Jordy Sample'],
  addresses: ['123 Example St, Springfield, IL', '45 Old Rd, Shelbyville, IL'],
  phone: '(555) 010-0199',
};

export const SITES = [
  { id: 'whitepages', name: 'Whitepages', optOut: 'https://www.whitepages.com/suppression-requests',
    shows: 'Name, age 40s, current address, 2 relatives', checks: run([F, F, F, F, F], [2]) },
  { id: 'spokeo', name: 'Spokeo', optOut: 'https://www.spokeo.com/optout', optOutSentOn: '2026-10-01',
    shows: 'Name, current + past address, phone', checks: run([F, F, F, F, F], [3]) },
  { id: 'beenverified', name: 'BeenVerified', optOut: 'https://www.beenverified.com/app/optout/search',
    shows: 'Name, age, city', checks: run([F, F, N, N, F], [2]) },
  { id: 'truepeoplesearch', name: 'TruePeopleSearch', optOut: 'https://www.truepeoplesearch.com/removal',
    shows: 'Name, phone, 3 addresses, relatives', checks: run([C, C, F, F, F], [7, 7, 6]) },
  { id: 'fastpeoplesearch', name: 'FastPeopleSearch', optOut: 'https://www.fastpeoplesearch.com/removal',
    shows: 'Name, phone, current address', optOutSentOn: '2026-09-20', checks: run([F, F, N, N, N], [4]) },
  { id: 'radaris', name: 'Radaris', optOut: 'https://radaris.com/control/privacy',
    shows: '', checks: run([N, N, N, N, N], [2]) },
  { id: 'peoplefinders', name: 'PeopleFinders', optOut: 'https://www.peoplefinders.com/opt-out',
    shows: '', checks: run([C, C, C, C, C], [7]), tried: [1, 2, 3, 4, 5, 6] },
  { id: 'intelius', name: 'Intelius', optOut: 'https://suppression.peopleconnect.us/login',
    shows: 'Name, age, past address', checks: run([F, F, F, F, F], [4]) },
  { id: 'mylife', name: 'MyLife', optOut: 'https://www.mylife.com/ccpa/index.pubview',
    shows: 'Name, "reputation score", city', optOutSentOn: '2026-09-25', checks: run([F, F, F, F, F], [5]) },
  { id: 'thatsthem', name: 'ThatsThem', optOut: 'https://thatsthem.com/optout',
    shows: '', checks: run([N, N, N, N, N], [1]) },
  { id: 'nuwber', name: 'Nuwber', optOut: 'https://nuwber.com/removal/link',
    shows: 'Name, phone, city', checks: run([F, F, F, F, C], [2, 2, 2, 2, 7]), tried: [1, 2, 3, 4, 5] },
  { id: 'clustrmaps', name: 'ClustrMaps', optOut: 'https://clustrmaps.com/bl/opt-out',
    shows: '', checks: run([N, N, N, N, N], [2]) },
  { id: 'peekyou', name: 'PeekYou', optOut: 'https://www.peekyou.com/about/contact/optout/',
    shows: '', checks: run([N, N, N, N, N], [1]) },
  { id: 'usphonebook', name: 'USPhoneBook', optOut: 'https://www.usphonebook.com/opt-out',
    shows: 'Name, phone', checks: run([F, F, F, F, F], [5]) },
  { id: 'cyberbackgroundchecks', name: 'CyberBackgroundChecks', optOut: 'https://www.cyberbackgroundchecks.com/removal',
    shows: '', checks: run([N, N, N, N, N], [2]) },
];

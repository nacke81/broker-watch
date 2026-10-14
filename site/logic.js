// Pure rules. No DOM. Tested by tests/logic.test.mjs.

export const RESULT = { FOUND: 'found', NOT_FOUND: 'not_found', COULDNT: 'couldnt_check' };

export const STATUS = {
  FOUND: 'Found',
  REQUESTED: 'Opt-out requested',
  GONE: 'Gone',
  CAME_BACK: 'Came back',
  NOT_FOUND: 'Not found',
  COULDNT: "Couldn't check",
  NEVER: 'Not checked yet',
};

export const LADDER = [
  null,
  'Plain request',
  'Real Chrome',
  'Chrome, saved profile',
  'Side door',
  'Changed query',
  'You in the loop',
  'Paid (needs your yes)',
];

const t = (d) => new Date(d + 'T12:00:00').getTime(); // compare as times, never strings

export function sortedChecks(site) {
  return [...(site.checks || [])].sort((a, b) => t(a.date) - t(b.date));
}

// Status of one site from its history. "Couldn't check" never becomes "Not found".
export function siteStatus(site) {
  const checks = sortedChecks(site);
  if (!checks.length) return STATUS.NEVER;
  const last = checks[checks.length - 1];
  if (last.result === RESULT.COULDNT) return STATUS.COULDNT;

  // Only real answers count for history.
  const real = checks.filter((c) => c.result !== RESULT.COULDNT);
  const everFound = real.some((c) => c.result === RESULT.FOUND);
  const optOut = site.optOutSentOn ? t(site.optOutSentOn) : null;

  if (last.result === RESULT.NOT_FOUND) return everFound ? STATUS.GONE : STATUS.NOT_FOUND;

  // last is FOUND
  const prior = real.slice(0, -1);
  const wasGone = prior.some((c, i) => c.result === RESULT.NOT_FOUND && prior.slice(0, i).some((p) => p.result === RESULT.FOUND));
  if (wasGone) return STATUS.CAME_BACK;
  if (optOut !== null) return STATUS.REQUESTED; // still listed, waiting on the site
  return STATUS.FOUND;
}

// What needs Mike's attention, in order.
const RANK = {
  [STATUS.CAME_BACK]: 0,
  [STATUS.FOUND]: 1,
  [STATUS.COULDNT]: 2,
  [STATUS.REQUESTED]: 3,
  [STATUS.NEVER]: 4,
  [STATUS.GONE]: 5,
  [STATUS.NOT_FOUND]: 6,
};

export function needsAction(status) {
  return status === STATUS.FOUND || status === STATUS.CAME_BACK || status === STATUS.COULDNT;
}

export function sortSites(sites) {
  return [...sites].sort((a, b) => RANK[siteStatus(a)] - RANK[siteStatus(b)] || a.name.localeCompare(b.name));
}

export function summary(sites) {
  const s = { listed: 0, action: 0, couldnt: 0, clean: 0 };
  for (const site of sites) {
    const st = siteStatus(site);
    if ([STATUS.FOUND, STATUS.CAME_BACK, STATUS.REQUESTED].includes(st)) s.listed++;
    if (needsAction(st)) s.action++;
    if (st === STATUS.COULDNT) s.couldnt++;
    if (st === STATUS.GONE || st === STATUS.NOT_FOUND) s.clean++;
  }
  return s;
}

// One row per weekly run: how many sites found / clean / couldn't check that day.
export function runHistory(sites) {
  const byDate = new Map();
  for (const site of sites) {
    for (const c of site.checks || []) {
      const r = byDate.get(c.date) || { date: c.date, found: 0, not_found: 0, couldnt_check: 0 };
      r[c.result]++;
      byDate.set(c.date, r);
    }
  }
  return [...byDate.values()].sort((a, b) => t(b.date) - t(a.date));
}

export function fmtDate(d) {
  const [y, m, day] = d.split('-').map(Number);
  return `${m}/${day}/${y}`;
}

// ---- My details lists (slice 1): phones and addresses are lists, each item checked before it's added ----

// "(555) 010-0199", "555.010.0199", "+1 555 010 0199" -> "5550100199"; anything else -> null.
export function normPhone(s) {
  let d = String(s ?? '').replace(/\D/g, '');
  if (d.length === 11 && d[0] === '1') d = d.slice(1);
  return d.length === 10 ? d : null;
}
export const fmtPhone = (d) => `(${d.slice(0, 3)}) ${d.slice(3, 6)}-${d.slice(6)}`;

// "123 Main St, Springfield IL, 62701" or "123 Main St, Springfield, IL 62701" -> {street, city, state, zip}.
// The weekly check searches by city + state, so both must be there; zip is optional.
export function parseAddress(s) {
  const parts = String(s ?? '').split(',').map((x) => x.trim()).filter(Boolean);
  if (parts.length < 2) return null;
  const rest = parts.slice(1).join(' ').replace(/\s+/g, ' ').trim();
  const m = rest.match(/^([A-Za-z .'-]+?)\s+([A-Za-z]{2})(?:\s+(\d{5})(?:-\d{4})?)?$/);
  if (!m || !/\d/.test(parts[0])) return null;
  return { street: parts[0], city: m[1].trim(), state: m[2].toUpperCase(), zip: m[3] || '' };
}

// Add one item to a list: returns { list, error }. Duplicates are ignored, not errors.
export function addPhone(list, s) {
  const d = normPhone(s);
  if (!d) return { list, error: 'Phone needs 10 digits, like (555) 010-0199.' };
  return { list: list.includes(d) ? list : [...list, d], error: '' };
}
export function addAddress(list, s) {
  const a = String(s ?? '').trim().replace(/\s+/g, ' ');
  if (!parseAddress(a)) return { list, error: 'Address like 123 Main St, Springfield IL, 62701 (street, then city and state).' };
  return { list: list.some((x) => x.toLowerCase() === a.toLowerCase()) ? list : [...list, a], error: '' };
}

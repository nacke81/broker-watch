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

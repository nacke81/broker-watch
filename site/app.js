import { siteStatus, sortSites, summary, runHistory, sortedChecks, fmtDate, STATUS, LADDER, RESULT } from './logic.js';
import { SITES, PERSON } from './seed.js';

const KEY = 'broker-watch-proto-v1';
const app = document.getElementById('app');
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// Prototype state: seed + Mike's local clicks (opt-out marks, details). Saved on first load.
function load() {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY));
    if (saved && saved.sites) return saved;
  } catch { /* fall through to seed */ }
  const fresh = { sites: structuredClone(SITES), person: structuredClone(PERSON) };
  localStorage.setItem(KEY, JSON.stringify(fresh));
  return fresh;
}
let state = load();
const save = () => localStorage.setItem(KEY, JSON.stringify(state));

const CLS = {
  [STATUS.FOUND]: 's-found', [STATUS.CAME_BACK]: 's-came-back', [STATUS.COULDNT]: 's-couldnt',
  [STATUS.REQUESTED]: 's-requested', [STATUS.GONE]: 's-gone', [STATUS.NOT_FOUND]: 's-not-found', [STATUS.NEVER]: 's-never',
};
const pill = (st) => `<span class="pill ${CLS[st]}">${esc(st)}</span>`;
const today = () => new Date().toISOString().slice(0, 10);

function lastRunLine() {
  const h = runHistory(state.sites);
  document.getElementById('lastRun').textContent = h.length
    ? `Last weekly check ${fmtDate(h[0].date)} · next ${fmtDate(nextWeek(h[0].date))}`
    : 'No checks yet';
}
function nextWeek(d) { const x = new Date(d + 'T12:00:00'); x.setDate(x.getDate() + 7); return x.toISOString().slice(0, 10); }

function sitesView() {
  const s = summary(state.sites);
  const groups = [
    ['Needs you', (st) => st === STATUS.FOUND || st === STATUS.CAME_BACK || st === STATUS.COULDNT],
    ['Waiting on the site', (st) => st === STATUS.REQUESTED],
    ['Clean', (st) => st === STATUS.GONE || st === STATUS.NOT_FOUND || st === STATUS.NEVER],
  ];
  const sorted = sortSites(state.sites);
  app.innerHTML = `
    <div class="tiles">
      <div class="tile"><b>${s.listed}</b><span>listing you</span></div>
      <div class="tile"><b>${s.action}</b><span>need you</span></div>
      <div class="tile"><b>${s.couldnt}</b><span>couldn't check</span></div>
      <div class="tile"><b>${s.clean}</b><span>clean</span></div>
    </div>
    ${groups.map(([title, f]) => {
      const rows = sorted.filter((x) => f(siteStatus(x)));
      if (!rows.length) return '';
      return `<h2>${title} (${rows.length})</h2><div class="list">${rows.map(rowHtml).join('')}</div>`;
    }).join('')}`;
  app.querySelectorAll('[data-site]').forEach((b) => b.addEventListener('click', () => go(`#site/${b.dataset.site}`)));
}

function rowHtml(site) {
  const st = siteStatus(site);
  const checks = sortedChecks(site);
  const last = checks[checks.length - 1];
  let meta = site.shows ? esc(site.shows) : 'No listing for you';
  if (st === STATUS.COULDNT) meta = `Blocked: tried ${site.tried?.length ?? 0} of 7 ladder steps`;
  if (st === STATUS.REQUESTED) meta = `Opt-out sent ${fmtDate(site.optOutSentOn)} · still listed`;
  if (st === STATUS.CAME_BACK) meta = `Was gone, listed again ${fmtDate(last.date)}`;
  return `<button class="row" data-site="${site.id}">
      <div class="grow"><div class="name">${esc(site.name)}</div><div class="meta">${meta}</div></div>
      ${pill(st)}
    </button>`;
}

function siteView(id) {
  const site = state.sites.find((x) => x.id === id);
  if (!site) return go('#sites');
  const st = siteStatus(site);
  const checks = sortedChecks(site);
  const last = checks[checks.length - 1];
  const listed = [STATUS.FOUND, STATUS.CAME_BACK, STATUS.REQUESTED].includes(st);

  let ladder = '';
  if (st === STATUS.COULDNT) {
    const tried = new Set(site.tried || []);
    const next = [1, 2, 3, 4, 5, 6, 7].find((n) => !tried.has(n));
    ladder = `<div class="card"><b>Couldn't check this week.</b> This is never counted as "not found".
      <ol class="ladder">${LADDER.slice(1).map((l, i) => {
        const n = i + 1;
        const cls = tried.has(n) ? 'failed' : n === next ? 'next' : '';
        return `<li class="${cls}">${esc(l)}${n === next ? ' ← next' : ''}</li>`;
      }).join('')}</ol>
      ${next === 6 ? `<button class="btn" id="loop">Open it so I can solve the check</button>` : ''}
      ${next === 7 ? `<p class="note">Only paid options left. Nothing is spent without your yes.</p><button class="btn ghost" id="paid">Ask me about a paid option</button>` : ''}
      <div class="ok" id="loopMsg"></div></div>`;
  } else if (last) {
    ladder = `<p class="note">Checked ${fmtDate(last.date)} using step ${last.step}: ${esc(LADDER[last.step])}.</p>`;
  }

  app.innerHTML = `
    <button class="back" id="back">‹ All sites</button>
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:8px">
        <h3 style="margin:0">${esc(site.name)}</h3>${pill(st)}
      </div>
      ${listed ? `<p><b>What it shows:</b> ${esc(site.shows)}</p>` : st === STATUS.COULDNT ? '' : `<p>No listing for you here.</p>`}
      ${ladder}
      <div class="hist">${checks.map((c) => `<i class="${c.result}" title="${fmtDate(c.date)}: ${c.result.replace('_', ' ')}"></i>`).join('')}</div>
      <div class="legend">Last ${checks.length} weeks, oldest first. Red found · green not there · amber couldn't check</div>
    </div>
    ${listed ? `<div class="card">
      <b>Opt out</b>
      <p class="note">You send opt-outs yourself. Broker Watch only reads.</p>
      <a class="btn" href="${esc(site.optOut)}" target="_blank" rel="noopener">Open ${esc(site.name)} opt-out page</a>
      <div style="margin-top:10px">
        ${site.optOutSentOn
          ? `<p class="note">You marked it sent on ${fmtDate(site.optOutSentOn)}. The weekly check will show when it's gone.</p>
             <button class="btn ghost" id="unsent">Undo: I didn't send it</button>`
          : `<button class="btn ghost" id="sent">I sent the opt-out</button>`}
      </div>
    </div>` : ''}
    <div class="card"><b>History</b><table><tr><th>Week</th><th>Result</th><th>Step</th></tr>
      ${[...checks].reverse().map((c) => `<tr><td>${fmtDate(c.date)}</td><td>${c.result === RESULT.FOUND ? 'Found' : c.result === RESULT.NOT_FOUND ? 'Not there' : "Couldn't check"}</td><td>${c.result === RESULT.COULDNT ? 'Blocked at every step tried' : esc(LADDER[c.step] ?? '')}</td></tr>`).join('')}
    </table></div>`;

  document.getElementById('back').onclick = () => go('#sites');
  const sent = document.getElementById('sent');
  if (sent) sent.onclick = () => { site.optOutSentOn = today(); save(); siteView(id); };
  const unsent = document.getElementById('unsent');
  if (unsent) unsent.onclick = () => { delete site.optOutSentOn; save(); siteView(id); };
  const loop = document.getElementById('loop');
  if (loop) loop.onclick = () => { document.getElementById('loopMsg').textContent = 'In the real app this opens the page for you to solve the check, then asks "Is this you?" with one tap.'; };
  const paid = document.getElementById('paid');
  if (paid) paid.onclick = () => { document.getElementById('loopMsg').textContent = 'In the real app this sends Reed a request; he comes back with a price for your yes or no.'; };
}

function runsView() {
  const h = runHistory(state.sites);
  app.innerHTML = `
    <h2>Weekly checks</h2>
    <div class="card"><table>
      <tr><th>Week</th><th class="n">Found</th><th class="n">Not there</th><th class="n">Couldn't check</th></tr>
      ${h.map((r) => `<tr><td>${fmtDate(r.date)}</td><td class="n">${r.found}</td><td class="n">${r.not_found}</td><td class="n">${r.couldnt_check}</td></tr>`).join('')}
    </table>
    <p class="note">Every run checks all ${state.sites.length} sites. If a run fails or doesn't happen, Reed gets an alert.</p></div>`;
}

function meView() {
  const p = state.person;
  app.innerHTML = `
    <h2>What the weekly check searches for</h2>
    <div class="card">
      <p class="note">Entered here once, never in chat. Stored only in your own account.</p>
      <label for="names">Name variants (one per line)</label>
      <textarea id="names" rows="3">${esc(p.names.join('\n'))}</textarea>
      <label for="addrs">Current and past addresses (one per line)</label>
      <textarea id="addrs" rows="3">${esc(p.addresses.join('\n'))}</textarea>
      <label for="phone">Phone</label>
      <input id="phone" value="${esc(p.phone)}" inputmode="tel" autocomplete="off">
      <div style="margin-top:12px"><button class="btn" id="saveMe">Save</button></div>
      <div class="err" id="meErr"></div><div class="ok" id="meOk"></div>
    </div>`;
  document.getElementById('saveMe').onclick = () => {
    const names = document.getElementById('names').value.split('\n').map((s) => s.trim()).filter(Boolean);
    const addrs = document.getElementById('addrs').value.split('\n').map((s) => s.trim()).filter(Boolean);
    const phone = document.getElementById('phone').value.trim();
    const err = document.getElementById('meErr'), ok = document.getElementById('meOk');
    err.textContent = ''; ok.textContent = '';
    if (!names.length) return (err.textContent = 'Add at least one name.');
    if (phone && phone.replace(/\D/g, '').length !== 10) return (err.textContent = 'Phone needs 10 digits, like (555) 010-0199.');
    state.person = { names, addresses: addrs, phone };
    save();
    ok.textContent = `Saved. Next weekly check searches ${names.length} name${names.length > 1 ? 's' : ''}.`;
  };
}

function go(hash) { if (location.hash !== hash) location.hash = hash; else route(); }
function route() {
  const h = location.hash || '#sites';
  const tab = h.startsWith('#runs') ? 'runs' : h.startsWith('#me') ? 'me' : 'sites';
  document.querySelectorAll('nav button').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === tab)));
  lastRunLine();
  if (h.startsWith('#site/')) siteView(h.slice(6));
  else if (tab === 'runs') runsView();
  else if (tab === 'me') meView();
  else sitesView();
  window.scrollTo(0, 0);
}
document.querySelectorAll('nav button').forEach((b) => (b.onclick = () => go('#' + b.dataset.tab)));
window.addEventListener('hashchange', route);
route();

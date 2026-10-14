import { siteStatus, sortSites, summary, runHistory, sortedChecks, fmtDate, STATUS, LADDER, RESULT, addPhone, addAddress, fmtPhone } from './logic.js';
import { createStore } from './store.js';
import { SUPABASE_URL, SUPABASE_KEY } from './config.js';

const sb = window.supabase.createClient(SUPABASE_URL, SUPABASE_KEY);
const store = createStore(sb);
const app = document.getElementById('app');
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// Real state, loaded from the database after sign-in. Same shapes the prototype used.
let state = { sites: [], runs: [], profile: null };
let user = null;
async function reload() {
  delete document.body.dataset.loaded;
  try {
    state = await store.load();
  } catch (e) {
    app.innerHTML = `<div class="card err">Couldn't load your results: ${esc(e.message)}. <a href="#" onclick="location.reload()">Try again</a></div>`;
    return;
  }
  document.body.dataset.loaded = '1';
  route();
}
async function act(fn) { // every write: do it, then reload from the database so the screen shows what's stored
  try { await fn(); } catch (e) { alert(`Didn't save: ${e.message}`); }
  await reload();
}

const CLS = {
  [STATUS.FOUND]: 's-found', [STATUS.CAME_BACK]: 's-came-back', [STATUS.COULDNT]: 's-couldnt',
  [STATUS.REQUESTED]: 's-requested', [STATUS.GONE]: 's-gone', [STATUS.NOT_FOUND]: 's-not-found', [STATUS.NEVER]: 's-never',
};
const pill = (st) => `<span class="pill ${CLS[st]}">${esc(st)}</span>`;
const today = () => day(new Date());
const listedNow = (site) => [STATUS.FOUND, STATUS.CAME_BACK, STATUS.REQUESTED].includes(siteStatus(site));

const day = (ts) => new Date(ts).toLocaleDateString('en-CA'); // local YYYY-MM-DD
function lastRunLine() {
  const ok = state.runs.find((r) => r.status === 'ok');
  document.getElementById('lastRun').textContent = !user ? ''
    : ok ? `Last weekly check ${fmtDate(day(ok.finished_at))} · next ${fmtDate(nextSunday())}`
    : 'No weekly check yet · first one Sunday';
}
function nextSunday() { const x = new Date(); x.setDate(x.getDate() + ((7 - x.getDay()) % 7 || 7)); return day(x); }

function sitesView() {
  const s = summary(state.sites);
  const groups = [
    ['Needs you', (st) => st === STATUS.FOUND || st === STATUS.CAME_BACK || st === STATUS.COULDNT],
    ['Waiting on the site', (st) => st === STATUS.REQUESTED],
    ['Clean', (st) => st === STATUS.GONE || st === STATUS.NOT_FOUND || st === STATUS.NEVER],
  ];
  const sorted = sortSites(state.sites);
  if (!state.runs.length) {
    app.innerHTML = `<div class="card" data-testid="welcome"><b>No weekly check has run yet.</b>
      <p class="note">The check runs Sundays at 10am on your PC and fills this page. Meanwhile, check <a href="#me">My details</a>.</p></div>`;
    return;
  }
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
  if (site.siteGone) meta = 'Site shut down (court order)';
  return `<button class="row" data-site="${site.id}" data-testid="row">
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
      ${next === 6 && site.url ? `<a class="btn" href="${esc(site.url)}" target="_blank" rel="noopener">Open it so I can solve the check</a>` : ''}
      ${site.captcha ? `<p class="note">The site showed a CAPTCHA or bot wall this week.</p>` : ''}
      ${next === 7 ? `<p class="note">Only paid options left. Nothing is spent without your yes.</p><button class="btn ghost" id="paid">Ask me about a paid option</button>` : ''}
      <div class="ok" id="loopMsg"></div></div>`;
  } else if (last) {
    ladder = `<p class="note">Checked ${fmtDate(last.date)}${last.step ? ` using step ${last.step}: ${esc(LADDER[last.step])}` : ''}.</p>
      ${listedNow(site) && site.url ? `<p><a href="${esc(site.url)}" target="_blank" rel="noopener">See the page it found</a></p>` : ''}`;
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
      <div class="legend">Last ${checks.length} week${checks.length === 1 ? "" : "s"}, oldest first. Red found · green not there · amber couldn't check</div>
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
  if (sent) sent.onclick = () => act(() => store.markSent(user.id, site.name, today()));
  const unsent = document.getElementById('unsent');
  if (unsent) unsent.onclick = () => act(() => store.unmarkSent(site.name));
  const paid = document.getElementById('paid');
  if (paid) paid.onclick = () => { document.getElementById('loopMsg').textContent = 'Coming in a later slice. For now, tell Reed in chat: he comes back with a price for your yes or no.'; };
}

function runsView() {
  const rows = state.runs;
  app.innerHTML = `
    <h2>Weekly checks</h2>
    <div class="card"><table data-testid="runs">
      <tr><th>Week</th><th class="n">Found</th><th class="n">Not there</th><th class="n">Couldn't check</th><th class="n">CAPTCHAs</th></tr>
      ${rows.map((r) => r.status === 'ok'
        ? `<tr><td>${fmtDate(day(r.started_at))}</td><td class="n">${r.found}</td><td class="n">${r.not_found + r.gone}</td><td class="n">${r.couldnt}</td><td class="n">${r.captchas}</td></tr>`
        : `<tr><td>${fmtDate(day(r.started_at))}</td><td colspan="4" class="${r.status === 'failed' ? 'err' : 'note'}">${r.status === 'failed' ? 'Failed. Reed was alerted.' : 'Running now...'}</td></tr>`).join('')
        || '<tr><td colspan="5" class="note">No runs yet.</td></tr>'}
    </table>
    <p class="note">Every run checks all ${state.sites.length} sites. If a run fails or doesn't happen, Reed gets an alert.</p></div>`;
}

const parseYear = (s) => { const y = Number(String(s).trim()); return Number.isInteger(y) && y >= 1900 && y <= 2020 ? y : null; };

// A list of identifiers with "+ Add another": its own <form>, so Return on the iPhone keyboard adds the item.
function listBlock(key, label, items, show, placeholder, mode) {
  return `<div class="list" data-list="${key}">
      <label for="${key}New">${label}</label>
      <ul class="items" data-testid="${key}-list">${items.map((x, i) => `<li><span>${esc(show(x))}</span>
        <button type="button" class="x" data-del="${key}" data-i="${i}" aria-label="Remove ${esc(show(x))}">Remove</button></li>`).join('')
        || '<li class="note">None yet.</li>'}</ul>
      <form class="add" id="${key}Form" novalidate>
        <input id="${key}New" placeholder="${placeholder}" inputmode="${mode}" enterkeyhint="done" autocomplete="off">
        <button class="btn ghost" type="submit" id="${key}Add">+ Add</button>
      </form>
    </div>`;
}

// My details saves itself (slice 2, Mike 2026-10-14: "autosave everything, drop the Save button"). In slice 1 his
// edits never reached the database because Save was easy to miss. Each change writes only its own field, the screen
// then shows the row the database sent back, and a bad value is never written.
const meStatus = { text: '', kind: '' };   // survives re-renders: 'Saved 2:14 PM' / "Didn't save: ..."
let saveChain = Promise.resolve();         // saves run one at a time, in the order they were made

function meView() {
  const p = state.profile || {};
  const KEEP = ['names', 'cityState', 'birthYear', 'phonesNew', 'addressesNew'];
  const keep = KEEP.map((id) => document.getElementById(id)?.value);
  const focusId = KEEP.includes(document.activeElement?.id) ? document.activeElement.id : null; // a save landing mid-typing keeps your cursor
  app.innerHTML = `
    <h2>What the weekly check searches for</h2>
    <div class="card">
      <p class="note">Entered here once, never in chat. Stored only in your own account. Changes save as you make them.${state.profile ? '' : ' <b>Not filled in yet:</b> until you do, the check uses the details Reed set up on your PC.'}</p>
      <label for="names">Name variants (one per line, full name first)</label>
      <textarea id="names" rows="3">${esc((p.names || []).join('\n'))}</textarea>
      <label for="cityState">Current city and state</label>
      <input id="cityState" value="${esc(p.city_state || '')}" placeholder="Springfield, IL" autocomplete="off" enterkeyhint="done">
      <label for="birthYear">Birth year (to tell you apart from relatives with your name)</label>
      <input id="birthYear" value="${esc(p.birth_year || '')}" inputmode="numeric" placeholder="1980" autocomplete="off" enterkeyhint="done">
      ${listBlock('phones', 'Phones (each one is searched on the sites that look up numbers)', p.phones || [], fmtPhone, '(555) 010-0199', 'tel')}
      ${listBlock('addresses', 'Current and past addresses (each city is searched too)', p.addresses || [], (x) => x, '123 Main St, Springfield IL, 62701', 'text')}
      <div class="err" id="meErr"></div>
      <div class="${meStatus.kind === 'err' ? 'err' : 'ok'}" id="meStatus" data-testid="me-status">${esc(meStatus.text)}</div>
    </div>`;
  KEEP.forEach((id, i) => { if (keep[i] !== undefined) document.getElementById(id).value = keep[i]; }); // re-render keeps what's typed
  if (focusId) document.getElementById(focusId).focus();
  const err = document.getElementById('meErr');
  const show = (text, kind) => {
    Object.assign(meStatus, { text, kind });
    const el = document.getElementById('meStatus');
    if (el) { el.textContent = text; el.className = kind === 'err' ? 'err' : 'ok'; }
  };
  // `change` gets the latest saved row, so two quick adds can't build on the same old list and drop one.
  const save = (change, after) => {
    err.textContent = ''; show('Saving…', 'ok');
    saveChain = saveChain.then(async () => {
      try {
        const fields = change(state.profile || {});
        if (fields.error) throw new Error(fields.error);
        state.profile = await store.saveFields(user.id, fields);
        show(`Saved ${new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}.`, 'ok');
      } catch (x) {
        show(`Didn't save: ${x.message}. Nothing was changed.`, 'err');
      }
      if ((location.hash || '').startsWith('#me')) { meView(); after?.(); }
    });
    return saveChain;
  };
  // Lists: add or remove writes the whole list for that field.
  const adders = { phones: addPhone, addresses: addAddress };
  for (const key of Object.keys(adders)) {
    const box = document.getElementById(`${key}New`);
    const add = (keepFocus) => {
      const v = box.value;
      if (!v.trim()) return;
      const r = adders[key](p[key] || [], v);   // checked now for the friendly error; rebuilt from the latest row below
      if (r.error) { err.textContent = r.error; return; }
      box.value = '';
      save((cur) => { const x = adders[key](cur[key] || [], v); return x.error ? x : { [key]: x.list }; },
        keepFocus ? () => document.getElementById(`${key}New`).focus() : null);
    };
    // Chrome fires `change` on Return before `submit`, so both paths go through add(); the second finds an empty box.
    // Return keeps the cursor here for the next one; typed-then-tapped-elsewhere still saves (the slice-1 miss).
    document.getElementById(`${key}Form`).onsubmit = (e) => { e.preventDefault(); add(true); };
    box.onchange = () => add(document.activeElement === box);
  }
  app.querySelectorAll('[data-del]').forEach((b) => {
    b.onclick = () => {
      const key = b.dataset.del, gone = (p[key] || [])[Number(b.dataset.i)];
      save((cur) => ({ [key]: (cur[key] || []).filter((x) => x !== gone) }));   // by value, not position
    };
  });
  // Single fields: save when you leave the field (or press Return), after our own check.
  const fields = {
    names: () => {
      const names = document.getElementById('names').value.split('\n').map((s) => s.trim()).filter(Boolean);
      return !names.length || names[0].split(/\s+/).length < 2 ? { error: 'Add at least one full name, like Jordan A. Sample.' } : { value: names };
    },
    cityState: () => {
      const v = document.getElementById('cityState').value.trim();
      return /^[A-Za-z .'-]+,?\s+[A-Za-z]{2}$/.test(v) ? { value: v } : { error: 'City and state like Springfield, IL.' };
    },
    birthYear: () => {
      const y = parseYear(document.getElementById('birthYear').value);
      return y ? { value: y } : { error: 'Birth year as 4 digits, like 1980.' };
    },
  };
  for (const [id, read] of Object.entries(fields)) {
    const el = document.getElementById(id);
    el.onchange = () => {
      const r = read();
      if (r.error) { err.textContent = r.error; show("Not saved: fix the field above.", 'err'); return; }
      save(() => ({ [id]: r.value }));
    };
    if (el.tagName === 'INPUT') el.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); el.blur(); } };
  }
}

// Sign in: email -> 6-digit code typed here (same as People CRM; one login for both apps).
function loginView() {
  meView.draft = null;
  user = null; state = { sites: [], runs: [], profile: null };
  document.querySelector('nav').hidden = true; document.getElementById('me').textContent = ''; lastRunLine();
  app.innerHTML = `<form class="card" id="lf" novalidate>
      <p>Sign in with your email. We'll send a 6-digit code.</p>
      <input id="email" type="email" autocomplete="email" inputmode="email" placeholder="you@example.com">
      <div style="margin-top:10px"><button class="btn" type="submit" style="width:100%">Email me a code</button></div>
      <div class="err" id="lerr"></div>
    </form>`;
  document.getElementById('lf').onsubmit = async (e) => {
    e.preventDefault();
    const email = document.getElementById('email').value.trim().toLowerCase();
    const err = document.getElementById('lerr');
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) { err.textContent = "That email doesn't look right."; return; }
    err.textContent = 'Sending...';
    const { error } = await sb.auth.signInWithOtp({ email, options: { shouldCreateUser: false } });
    if (error) { err.textContent = /signups? not allowed|not found/i.test(error.message) ? "That email isn't set up for this app." : error.message; return; }
    codeView(email);
  };
}
function codeView(email) {
  app.innerHTML = `<form class="card" id="cf" novalidate>
      <p>Code sent to <b>${esc(email)}</b>. Type it here.</p>
      <input id="code" inputmode="numeric" autocomplete="one-time-code" maxlength="8" placeholder="••••••" style="letter-spacing:.3em;font-size:22px;text-align:center">
      <div style="margin-top:10px"><button class="btn" type="submit" style="width:100%">Sign in</button></div>
      <div class="err" id="cerr"></div>
      <p class="note"><a href="#" id="again">Use a different email</a></p>
    </form>`;
  document.getElementById('code').focus();
  document.getElementById('again').onclick = (e) => { e.preventDefault(); loginView(); };
  document.getElementById('cf').onsubmit = async (e) => {
    e.preventDefault();
    const token = document.getElementById('code').value.replace(/\D/g, '');
    const { error } = await sb.auth.verifyOtp({ email, token, type: 'email' });
    if (error) document.getElementById('cerr').textContent = "That code didn't work. Check it, or send a new one.";
  };
}
async function enter(session) {
  user = session.user;
  document.querySelector('nav').hidden = false;
  document.getElementById('me').innerHTML = `${esc(user.email)} · <a href="#" id="signout">Sign out</a>`;
  document.getElementById('signout').onclick = async (e) => { e.preventDefault(); await sb.auth.signOut(); };
  app.innerHTML = '<div class="note">Loading...</div>';
  await reload();
}

function go(hash) { if (location.hash !== hash) location.hash = hash; else route(); }
function route() {
  if (!user) return;
  const h = location.hash || '#sites';
  const tab = h.startsWith('#runs') ? 'runs' : h.startsWith('#me') ? 'me' : 'sites';
  document.querySelectorAll('nav button').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === tab)));
  lastRunLine();
  if (!document.body.dataset.loaded) return;
  if (h.startsWith('#site/')) siteView(h.slice(6));
  else if (tab === 'runs') runsView();
  else if (tab === 'me') meView();
  else sitesView();
  window.scrollTo(0, 0);
}
document.querySelectorAll('nav button').forEach((b) => (b.onclick = () => go('#' + b.dataset.tab)));
window.addEventListener('hashchange', route);

let current;
sb.auth.onAuthStateChange((event, session) => {
  const id = session?.user?.id || null;
  if (id === current) return; // token refreshes don't redraw
  current = id;
  setTimeout(() => (session ? enter(session) : loginView()), 0);
});
// Test hook: lets the hosted end-to-end check drive the real code screen without spending the email quota.
window.__bw_codeView = codeView;

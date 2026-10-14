import { test } from 'node:test';
import assert from 'node:assert/strict';
import { siteStatus, STATUS, summary, runHistory, sortSites, needsSolve } from '../site/logic.js';
import { SITES } from './seed.js';

const site = (results, extra = {}) => ({
  name: 'X',
  checks: results.map((r, i) => ({ date: `2026-09-${String(10 + i).padStart(2, '0')}`, result: r })),
  ...extra,
});

test('golden 3: a blocked site is "couldn\'t check", never "not found"', () => {
  assert.equal(siteStatus(site(['couldnt_check'])), STATUS.COULDNT);
  assert.equal(siteStatus(site(['not_found', 'couldnt_check'])), STATUS.COULDNT);
  assert.equal(siteStatus(site(['found', 'couldnt_check'])), STATUS.COULDNT);
});

test('found, gone, came back', () => {
  assert.equal(siteStatus(site(['found'])), STATUS.FOUND);
  assert.equal(siteStatus(site(['found', 'not_found'])), STATUS.GONE);
  assert.equal(siteStatus(site(['found', 'not_found', 'found'])), STATUS.CAME_BACK);
  assert.equal(siteStatus(site(['not_found', 'not_found'])), STATUS.NOT_FOUND);
  assert.equal(siteStatus(site(['not_found', 'found'])), STATUS.FOUND, 'new listing, not came back');
});

test('a blocked week in between does not count as gone', () => {
  assert.equal(siteStatus(site(['found', 'couldnt_check', 'found'])), STATUS.FOUND);
});

test('opt-out sent while still listed is "requested"; gone after that is "gone"', () => {
  assert.equal(siteStatus(site(['found'], { optOutSentOn: '2026-09-11' })), STATUS.REQUESTED);
  assert.equal(siteStatus(site(['found', 'not_found'], { optOutSentOn: '2026-09-10' })), STATUS.GONE);
});

test('no checks yet', () => assert.equal(siteStatus({ name: 'X', checks: [] }), STATUS.NEVER));

test('dates compare as times, not strings (out-of-order history)', () => {
  const s = { name: 'X', checks: [{ date: '2026-10-06', result: 'not_found' }, { date: '2026-09-29', result: 'found' }] };
  assert.equal(siteStatus(s), STATUS.GONE);
});

test('fake seed: summary and order', () => {
  const s = summary(SITES);
  assert.deepEqual(s, { listed: 7, action: 7, couldnt: 2, unreachable: 0, clean: 6 });
  assert.equal(sortSites(SITES)[0].name, 'BeenVerified', 'came back sorts first');
  const h = runHistory(SITES);
  assert.equal(h.length, 5);
  assert.equal(h[0].date, '2026-10-13');
  assert.equal(h[0].found + h[0].not_found + h[0].couldnt_check, 15);
});

test('phones: any common format becomes 10 digits; short, long and empty are refused with a friendly error', async () => {
  const { normPhone, addPhone, fmtPhone } = await import('../site/logic.js');
  assert.equal(normPhone('(555) 010-0199'), '5550100199');
  assert.equal(normPhone('+1 555.010.0199'), '5550100199');
  assert.equal(normPhone('555-0199'), null);
  assert.equal(normPhone('25550100199'), null);
  assert.equal(fmtPhone('5550100199'), '(555) 010-0199');
  let r = addPhone([], '555 010 0199'); assert.deepEqual(r, { list: ['5550100199'], error: '' });
  r = addPhone(r.list, '(555) 010-0199'); assert.deepEqual(r.list, ['5550100199'], 'same number twice is kept once');
  r = addPhone(r.list, '555 010 0200'); assert.equal(r.list.length, 2);
  r = addPhone(r.list, '123'); assert.match(r.error, /10 digits/); assert.equal(r.list.length, 2);
});

test('addresses: street + city + state required (the check searches each old city); zip optional', async () => {
  const { parseAddress, addAddress } = await import('../site/logic.js');
  assert.deepEqual(parseAddress('123 Example St, Springfield IL, 62701'), { street: '123 Example St', city: 'Springfield', state: 'IL', zip: '62701' });
  assert.deepEqual(parseAddress('45 Old Rd, Glen Ellyn, il 60137'), { street: '45 Old Rd', city: 'Glen Ellyn', state: 'IL', zip: '60137' });
  assert.deepEqual(parseAddress('9 Elm Ave Apt 2, Shelbyville, IL'), { street: '9 Elm Ave Apt 2', city: 'Shelbyville', state: 'IL', zip: '' });
  assert.equal(parseAddress('Springfield IL'), null);
  assert.equal(parseAddress('Main St, Springfield IL'), null, 'a street needs a number');
  assert.equal(parseAddress('123 Main St, 62701'), null);
  let r = addAddress([], '123 Example St, Springfield IL, 62701'); assert.equal(r.list.length, 1);
  r = addAddress(r.list, '123 example st,  Springfield IL, 62701'); assert.equal(r.list.length, 1, 'same address twice is kept once');
  r = addAddress(r.list, 'somewhere'); assert.match(r.error, /city and state/); assert.equal(r.list.length, 1);
});

// Slice 2: why a site couldn't be checked. Neither reason may ever read as "not found".
const why = (results, reason) => ({ name: 'X', checks: results.map((r, i) => ({ date: `2026-09-${10 + i}`, result: r,
  reason: i === results.length - 1 ? reason : null })) });

test('site unreachable is its own state, never not found, and a site that answers again leaves it', () => {
  assert.equal(siteStatus(why(['couldnt_check'], 'unreachable')), STATUS.UNREACHABLE);
  assert.equal(siteStatus(why(['found', 'couldnt_check'], 'unreachable')), STATUS.UNREACHABLE);
  assert.notEqual(siteStatus(why(['found', 'couldnt_check'], 'unreachable')), STATUS.GONE);
  assert.equal(siteStatus(why(['couldnt_check', 'found'], null)), STATUS.FOUND);
  const s = summary([why(['couldnt_check'], 'unreachable'), why(['couldnt_check'], 'captcha')]);
  assert.deepEqual([s.unreachable, s.couldnt, s.clean, s.action], [1, 1, 0, 1]); // unreachable isn't "needs you"
});

test('step 6: only a CAPTCHA stop asks the owner to solve; unreachable and plain blocks do not', () => {
  assert.equal(needsSolve(why(['couldnt_check'], 'captcha')), true);
  assert.equal(siteStatus(why(['couldnt_check'], 'captcha')), STATUS.COULDNT);
  assert.equal(needsSolve(why(['couldnt_check'], 'unreachable')), false);
  assert.equal(needsSolve(why(['couldnt_check'], null)), false);
  assert.equal(needsSolve(why(['couldnt_check', 'found'], null)), false);   // solved and found: done
});

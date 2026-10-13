import { test } from 'node:test';
import assert from 'node:assert/strict';
import { siteStatus, STATUS, summary, runHistory, sortSites } from '../site/logic.js';
import { SITES } from '../site/seed.js';

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
  assert.deepEqual(s, { listed: 7, action: 7, couldnt: 2, clean: 6 });
  assert.equal(sortSites(SITES)[0].name, 'BeenVerified', 'came back sorts first');
  const h = runHistory(SITES);
  assert.equal(h.length, 5);
  assert.equal(h[0].date, '2026-10-13');
  assert.equal(h[0].found + h[0].not_found + h[0].couldnt_check, 15);
});

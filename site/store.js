// The only file that talks to the database. It returns the same shapes the prototype used, so logic.js is unchanged.
import { OPT_OUT, SITE_NAMES } from "./sites.js";

const id = (name) => name.toLowerCase();

// Rows -> [{ id, name, optOut, optOutSentOn, shows, checks: [{date, result, step}], tried, url, gated, captcha }]
export function assemble(checks, optouts) {
  const sent = Object.fromEntries(optouts.map((o) => [o.site, o.sent_on]));
  const bySite = {};
  for (const c of checks) (bySite[c.site] ||= []).push(c);
  return SITE_NAMES.map((name) => {
    const rows = (bySite[name] || []).slice().sort((a, b) => new Date(a.checked_on) - new Date(b.checked_on));
    const last = rows[rows.length - 1];
    const site = {
      id: id(name), name, optOut: OPT_OUT[name],
      // A site shut down (court order) holds no listing of the owner: clean, with its own note.
      checks: rows.map((r) => ({ date: r.checked_on, result: r.result === "gone" ? "not_found" : r.result, step: r.step })),
      siteGone: !!last && last.result === "gone",
      shows: last && last.result === "found" ? (last.gated ? "Listed (details behind a paywall)" : "Listed") : "",
      tried: last ? last.tried : [], url: last ? last.url : null, captcha: !!last?.captcha,
    };
    if (sent[name]) site.optOutSentOn = sent[name];
    return site;
  });
}

export function createStore(sb) {
  const must = ({ data, error }) => { if (error) throw error; return data; };
  return {
    async load() {
      const [checks, optouts, runs, profile] = await Promise.all([
        sb.from("bw_checks").select("site,checked_on,result,step,tried,url,gated,captcha").order("checked_on").then(must),
        sb.from("bw_optouts").select("site,sent_on").then(must),
        sb.from("bw_runs").select("*").order("started_at", { ascending: false }).limit(52).then(must),
        sb.from("bw_profile").select("*").maybeSingle().then(must),
      ]);
      return { sites: assemble(checks, optouts), runs, profile };
    },
    // owner is sent only so upsert can find the existing row; row security refuses any owner but the signed-in one.
    async markSent(owner, site, day) { must(await sb.from("bw_optouts").upsert({ owner, site, sent_on: day })); },
    async unmarkSent(site) { must(await sb.from("bw_optouts").delete().eq("site", site)); },
    async saveProfile(owner, p) {
      must(await sb.from("bw_profile").upsert({ owner, names: p.names, addresses: p.addresses, city_state: p.cityState,
        phones: p.phones, birth_year: p.birthYear, updated_at: new Date().toISOString() }));
    },
  };
}

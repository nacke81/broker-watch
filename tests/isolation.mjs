// Privacy test for the four bw_* tables (they share People CRM's project and login, so this is the guard).
// A second account and the logged-out key must read/change 0 of the owner's rows. Positive control: the owner reads his own.
// Needs SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SECRET_KEY. Creates throwaway accounts and deletes them. Exit 1 on any leak.
import { createClient } from "@supabase/supabase-js";

const { SUPABASE_URL: URL, SUPABASE_ANON_KEY: KEY, SUPABASE_SECRET_KEY: SECRET } = process.env;
const run = Date.now().toString(36);
const opts = { auth: { persistSession: false, autoRefreshToken: false } };
const mk = () => createClient(URL, KEY, opts);
const admin = createClient(URL, SECRET, opts);
const results = [];
const check = (name, ok, detail = "") => { results.push(ok); console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? "  (" + detail + ")" : ""}`); };
const made = [];
async function account(tag) {
  const email = `bw-${tag}-${run}@spike.test`, password = "bw-" + run + "-pw";
  const { data, error } = await admin.auth.admin.createUser({ email, password, email_confirm: true });
  if (error) throw new Error(`create ${tag}: ${error.message}`);
  made.push(data.user.id);
  const c = mk();
  const s = await c.auth.signInWithPassword({ email, password });
  if (s.error) throw new Error(`sign in ${tag}: ${s.error.message}`);
  return { c, id: data.user.id };
}

try {
  const owner = await account("owner");
  const intruder = await account("intruder");
  const anon = mk();

  // The job writes with the secret key, owner stamped explicitly (as job/run.py does).
  const runRow = (await admin.from("bw_runs").insert({ owner: owner.id, status: "ok", found: 1 }).select().single()).data;
  await admin.from("bw_checks").insert({ owner: owner.id, run_id: runRow.id, site: "Spokeo", checked_on: "2026-10-18", result: "found", url: "https://example.com/listing" });
  // The owner writes his own details and an opt-out through the app's key.
  const p = await owner.c.from("bw_profile").upsert({ owner: owner.id, names: ["Test Owner"], city_state: "Springfield, IL", birth_year: 1980 });
  check("owner saves his details", !p.error, p.error?.message);
  const o = await owner.c.from("bw_optouts").upsert({ owner: owner.id, site: "Spokeo", sent_on: "2026-10-19" });
  check("owner marks an opt-out sent", !o.error, o.error?.message);

  const T = ["bw_runs", "bw_checks", "bw_profile", "bw_optouts"];
  for (const t of T) {
    const own = await owner.c.from(t).select("*");
    check(`CONTROL ${t}: owner reads his own row`, (own.data || []).length === 1, `got ${own.data?.length}`);
    const i = await intruder.c.from(t).select("*");
    check(`${t}: intruder reads 0`, (i.data || []).length === 0, `got ${i.data?.length}`);
    const io = await intruder.c.from(t).select("*").eq("owner", owner.id);
    check(`${t}: intruder filtering owner = victim reads 0`, (io.data || []).length === 0, `got ${io.data?.length}`);
    const iu = await intruder.c.from(t).update({ owner: intruder.id }).eq("owner", owner.id).select();
    check(`${t}: intruder takes ownership of 0`, (iu.data || []).length === 0, `got ${iu.data?.length}`);
    const id = await intruder.c.from(t).delete().eq("owner", owner.id).select();
    check(`${t}: intruder deletes 0`, (id.data || []).length === 0, `got ${id.data?.length}`);
    const a = await anon.from(t).select("*");
    check(`${t}: logged out reads 0`, (a.data || []).length === 0, a.error ? "refused" : `got ${a.data?.length}`);
  }
  const plant = await intruder.c.from("bw_optouts").insert({ owner: owner.id, site: "Whitepages", sent_on: "2026-10-19" }).select();
  check("intruder plants a row owned by the victim -> refused", !!plant.error, plant.error ? "refused" : "ACCEPTED");
  const prof = await intruder.c.from("bw_profile").upsert({ owner: owner.id, names: ["pwned"], city_state: "X, IL" }).select();
  check("intruder overwrites the victim's details -> refused", !!prof.error, prof.error ? "refused" : "ACCEPTED");
  const after = await owner.c.from("bw_profile").select("names").single();
  check("owner's details untouched", after.data?.names?.[0] === "Test Owner", JSON.stringify(after.data));
} finally {
  for (const id of made) await admin.auth.admin.deleteUser(id); // rows go too (on delete cascade)
}
const passed = results.filter(Boolean).length;
console.log(`\nISOLATION SCORE: ${passed} of ${results.length}`);
process.exit(passed === results.length ? 0 : 1);

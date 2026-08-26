#!/usr/bin/env node
// Scans known ATS boards for new intern/co-op postings and diffs against
// previously-seen job IDs. Prints only what's NEW since the last run.
//
// Usage: node scripts/intern_scan.mjs
// State is persisted in scripts/.intern_seen.json (committed so state
// survives across sessions).

import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const STATE_PATH = path.join(__dirname, '.intern_seen.json');

const INTERN_RE = /intern|co-?op/i;
const FALSE_POSITIVE_RE = /international|internal/i;

// ---- Board config -------------------------------------------------------

const GREENHOUSE_BOARDS = {
  'Stoke Space': 'stokespacetechnologies',
  'Relativity Space': 'relativity',
  'Vast': 'vast',
  'K2 Space': 'k2spacecorporation',
  'Rocket Lab': 'rocketlab',
  'Muon Space': 'muonspace',
  'Astranis': 'astranis',
  'Rendezvous Robotics': 'rendezvousrobotics',
  'Varda Space Industries': 'vardaspace',
  'Anduril': 'andurilindustries',
  'Katalyst Space Technologies': 'katalyst',
  'Samara Aerospace': 'samaraaerospace',
  'Agility Robotics': 'agilityrobotics',
  'Epirus': 'epirus',
  'Vannevar Labs': 'vannevarlabs',
  'Zone 5 Technologies': 'zone5technologies',
  'Terran Orbital': 'terranorbitalcorporation',
  'SimScale': 'simscale',
  'Freeform': 'freeformfuturecorp',
  'Zipline': 'flyzipline',
  'Gravitics': 'graviticsinc',
};

const LEVER_BOARDS = {
  'Hermeus': 'hermeus',
  'Pivotal': 'pivotal',
  'Shield AI': 'shieldai',
  'Palantir': 'palantir',
};

const ASHBY_BOARDS = {
  'Applied Intuition': 'applied',
  'Starpath Robotics': 'starpath.space',
  'Xona Space Systems': 'xona-space',
  '1X Technologies': '1x',
};

// Workday CXS tenants: { tenant, site }
const WORKDAY_BOARDS = {
  'Nvidia': { host: 'nvidia.wd5', tenant: 'nvidia', site: 'NVIDIAExternalCareerSite' },
  'Sierra Space': { host: 'sierraspace.wd1', tenant: 'sierraspace', site: 'Sierra_Space_External_Career_Site' },
  'Boeing': { host: 'boeing.wd1', tenant: 'boeing', site: 'EXTERNAL_CAREERS' },
  'Leidos': { host: 'leidos.wd5', tenant: 'leidos', site: 'External' },
  'GE Aerospace': { host: 'geaerospace.wd5', tenant: 'geaerospace', site: 'GE_ExternalSite' },
  'Draper Laboratory': { host: 'draper.wd5', tenant: 'draper', site: 'Draper_Careers' },
  'AeroVironment': { host: 'avav.wd1', tenant: 'avav', site: 'AVAV' },
  'Booz Allen Hamilton': { host: 'boozallen.wd1', tenant: 'boozallen', site: 'BAH_Jobs' },
  'Teledyne FLIR': { host: 'flir.wd1', tenant: 'flir', site: 'flircareers' },
  'GDIT': { host: 'gdit.wd5', tenant: 'gdit', site: 'External_Career_Site' },
  'Sierra Nevada Corporation': { host: 'snc.wd1', tenant: 'snc', site: 'SNC_External_Career_Site' },
  'The Aerospace Corporation': { host: 'aero.wd5', tenant: 'aero', site: 'External' },
  'Amentum': { host: 'pae.wd1', tenant: 'pae', site: 'Amentum_Careers' },
};

// Eightfold-style: GET search API, domain + query param
const EIGHTFOLD_BOARDS = {
  'Northrop Grumman': 'https://jobs.northropgrumman.com/api/pcsx/search?domain=ngc.com&query=2027%20intern&limit=100',
};

// ---- Fetchers -------------------------------------------------------------

async function fetchGreenhouse(slug) {
  const r = await fetch(`https://boards-api.greenhouse.io/v1/boards/${slug}/jobs`);
  if (!r.ok) return { ok: false, status: r.status };
  const d = await r.json();
  const jobs = d.jobs
    .filter(j => INTERN_RE.test(j.title) && !FALSE_POSITIVE_RE.test(j.title))
    .map(j => ({ id: `gh:${slug}:${j.id}`, title: j.title, location: j.location?.name || '', posted: (j.first_published || '').slice(0, 10), url: j.absolute_url }));
  return { ok: true, jobs };
}

async function fetchLever(slug) {
  const r = await fetch(`https://api.lever.co/v0/postings/${slug}?mode=json`);
  if (!r.ok) return { ok: false, status: r.status };
  const d = await r.json();
  const jobs = d
    .filter(j => INTERN_RE.test(j.text) && !FALSE_POSITIVE_RE.test(j.text))
    .map(j => ({ id: `lever:${slug}:${j.id}`, title: j.text, location: j.categories?.location || '', posted: '', url: j.hostedUrl }));
  return { ok: true, jobs };
}

async function fetchAshby(slug) {
  const r = await fetch(`https://api.ashbyhq.com/posting-api/job-board/${slug}?includeCompensation=false`);
  if (!r.ok) return { ok: false, status: r.status };
  const d = await r.json();
  const jobs = d.jobs
    .filter(j => INTERN_RE.test(j.title) && !FALSE_POSITIVE_RE.test(j.title))
    .map(j => ({ id: `ashby:${slug}:${j.id}`, title: j.title, location: j.location || '', posted: (j.publishedAt || '').slice(0, 10), url: j.jobUrl }));
  return { ok: true, jobs };
}

async function fetchWorkday({ host, tenant, site }, searchText = 'intern') {
  const url = `https://${host}.myworkdayjobs.com/wday/cxs/${tenant}/${site}/jobs`;
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ appliedFacets: {}, limit: 20, offset: 0, searchText }),
  });
  if (!r.ok) return { ok: false, status: r.status };
  const d = await r.json();
  const postings = d.jobPostings || [];
  const jobs = postings
    .filter(j => INTERN_RE.test(j.title) && !FALSE_POSITIVE_RE.test(j.title))
    .map(j => ({
      id: `wd:${host}:${j.externalPath}`,
      title: j.title,
      location: j.locationsText || '',
      posted: j.postedOn || '',
      url: `https://${host}.myworkdayjobs.com/en-US/${site}${j.externalPath}`,
    }));
  return { ok: true, jobs, total: d.total };
}

async function fetchEightfold(url) {
  const r = await fetch(url);
  if (!r.ok) return { ok: false, status: r.status };
  const d = await r.json();
  const positions = d.data?.positions || [];
  const jobs = positions
    .filter(p => INTERN_RE.test(p.name) && !FALSE_POSITIVE_RE.test(p.name))
    .map(p => ({ id: `ef:${p.id}`, title: p.name, location: (p.standardizedLocations || []).join('/'), posted: '', url: `https://jobs.northropgrumman.com${p.positionUrl}` }));
  return { ok: true, jobs };
}

// ---- Main -----------------------------------------------------------------

function loadState() {
  if (!existsSync(STATE_PATH)) return {};
  try { return JSON.parse(readFileSync(STATE_PATH, 'utf8')); } catch { return {}; }
}

function saveState(state) {
  writeFileSync(STATE_PATH, JSON.stringify(state, null, 2) + '\n');
}

async function main() {
  const state = loadState();
  const newFindings = [];
  const errors = [];

  async function process(company, result) {
    if (!result.ok) {
      errors.push(`${company}: HTTP ${result.status}`);
      return;
    }
    for (const job of result.jobs) {
      if (!state[job.id]) {
        state[job.id] = { title: job.title, seenAt: new Date().toISOString().slice(0, 10) };
        newFindings.push({ company, ...job });
      }
    }
  }

  await Promise.all(Object.entries(GREENHOUSE_BOARDS).map(async ([company, slug]) => {
    try { await process(company, await fetchGreenhouse(slug)); }
    catch (e) { errors.push(`${company}: ${e.message}`); }
  }));

  await Promise.all(Object.entries(LEVER_BOARDS).map(async ([company, slug]) => {
    try { await process(company, await fetchLever(slug)); }
    catch (e) { errors.push(`${company}: ${e.message}`); }
  }));

  await Promise.all(Object.entries(ASHBY_BOARDS).map(async ([company, slug]) => {
    try { await process(company, await fetchAshby(slug)); }
    catch (e) { errors.push(`${company}: ${e.message}`); }
  }));

  await Promise.all(Object.entries(WORKDAY_BOARDS).map(async ([company, cfg]) => {
    try { await process(company, await fetchWorkday(cfg)); }
    catch (e) { errors.push(`${company}: ${e.message}`); }
  }));

  await Promise.all(Object.entries(EIGHTFOLD_BOARDS).map(async ([company, url]) => {
    try { await process(company, await fetchEightfold(url)); }
    catch (e) { errors.push(`${company}: ${e.message}`); }
  }));

  saveState(state);

  console.log(JSON.stringify({ newFindings, errors, checkedAt: new Date().toISOString() }, null, 2));
}

main();

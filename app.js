'use strict';

/* ── Platform config ──────────────────────────────────────────────────── */

const PLATFORMS = {
  github:    { sourceOk: true,  destOk: true,  urlVar: null,          tokenVar: 'GITHUB_TOKEN',  extraVars: null },
  gitea:     { sourceOk: true,  destOk: true,  urlVar: 'GITEA_URL',   tokenVar: 'GITEA_TOKEN',   extraVars: null },
  gitlab:    { sourceOk: true,  destOk: true,  urlVar: 'GITLAB_URL',  tokenVar: 'GITLAB_TOKEN',  extraVars: null },
  bitbucket: { sourceOk: true,  destOk: true,  urlVar: null,          tokenVar: null,            extraVars: ['BITBUCKET_WORKSPACE', 'BITBUCKET_USERNAME', 'BITBUCKET_APP_PASSWORD'] },
  forgejo:   { sourceOk: false, destOk: true,  urlVar: 'FORGEJO_URL', tokenVar: 'FORGEJO_TOKEN', extraVars: null },
};

/* URL input IDs for migrate tab, keyed by urlVar */
const URL_INPUTS = {
  GITEA_URL:   'm-gitea-url',
  GITLAB_URL:  'm-gitlab-url',
  FORGEJO_URL: 'm-forgejo-url',
};

/* URL input IDs for delete tab, keyed by urlVar */
const D_URL_INPUTS = {
  GITEA_URL:   'd-gitea-url',
  GITLAB_URL:  'd-gitlab-url',
  FORGEJO_URL: 'd-forgejo-url',
};

/* ── Theme ────────────────────────────────────────────────────────────── */

const root      = document.documentElement;
const toggleBtn = document.getElementById('theme-toggle');

function applyTheme(dark) {
  root.setAttribute('data-theme', dark ? 'dark' : 'light');
  toggleBtn.textContent = dark ? '☀️ Light' : '🌙 Dark';
}

(function initTheme() {
  const saved = localStorage.getItem('theme');
  if (saved) {
    applyTheme(saved === 'dark');
  } else {
    applyTheme(window.matchMedia('(prefers-color-scheme: dark)').matches);
  }
}());

toggleBtn.addEventListener('click', () => {
  const isDark = root.getAttribute('data-theme') === 'dark';
  applyTheme(!isDark);
  localStorage.setItem('theme', isDark ? 'light' : 'dark');
});

/* ── Tabs ─────────────────────────────────────────────────────────────── */

document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => {
      b.classList.remove('active');
      b.setAttribute('aria-selected', 'false');
    });
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    btn.setAttribute('aria-selected', 'true');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
    update();
  });
});

/* ── Collapsibles ─────────────────────────────────────────────────────── */

document.querySelectorAll('.collapsible-header').forEach(header => {
  function toggle() {
    const col  = header.closest('.collapsible');
    const open = col.classList.toggle('open');
    header.setAttribute('aria-expanded', String(open));
  }
  header.addEventListener('click', toggle);
  header.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
  });
});

/* ── Migrate tab: field show/hide ─────────────────────────────────────── */

const mSource = document.getElementById('m-source');
const mDest   = document.getElementById('m-dest');
const mMode   = document.getElementById('m-mode');

function updateMigrateFields() {
  const src  = mSource.value;
  const dest = mDest.value;
  const mode = mMode.value;

  setVisible('f-gitea-url-src',  src === 'gitea'     || dest === 'gitea');
  setVisible('f-gitlab-url',     src === 'gitlab'    || dest === 'gitlab');
  setVisible('f-forgejo-url',    dest === 'forgejo');
  setVisible('f-bitbucket-note', src === 'bitbucket' || dest === 'bitbucket');
  setVisible('m-github-dest-warning', dest === 'github');

  setVisible('f-org',  mode === 'org'  || mode === 'star');
  setVisible('f-user', mode === 'user' || mode === 'star');
  setVisible('f-repo', mode === 'repo');

  const starBlocked = src === 'bitbucket' && mode === 'star';
  const starHint    = document.getElementById('m-star-hint');
  if (starHint) starHint.hidden = !starBlocked;

  const starOpt = mMode.querySelector('option[value="star"]');
  if (starOpt) starOpt.disabled = src === 'bitbucket';
  if (src === 'bitbucket' && mode === 'star') mMode.value = '';
}

mSource.addEventListener('change', () => { updateMigrateFields(); update(); });
mDest.addEventListener('change',   () => { updateMigrateFields(); update(); });
mMode.addEventListener('change',   () => { updateMigrateFields(); update(); });

/* ── Delete tab: URL fields show/hide ─────────────────────────────────── */

const dDest = document.getElementById('d-dest');

function updateDeleteFields() {
  const dest = dDest.value;
  setVisible('f-d-gitea-url',      dest === 'gitea');
  setVisible('f-d-gitlab-url',     dest === 'gitlab');
  setVisible('f-d-forgejo-url',    dest === 'forgejo');
  setVisible('f-d-bitbucket-note', dest === 'bitbucket');
  setVisible('f-d-github-note',    dest === 'github');
}

dDest.addEventListener('change', () => { updateDeleteFields(); update(); });

/* ── Generic input change listener ───────────────────────────────────── */

document.querySelectorAll('input, select').forEach(el => {
  el.addEventListener('input',  update);
  el.addEventListener('change', update);
});

/* ── Helpers ──────────────────────────────────────────────────────────── */

function setVisible(id, visible) {
  const el = document.getElementById(id);
  if (el) el.classList.toggle('hidden', !visible);
}

function val(id) {
  const el = document.getElementById(id);
  return el ? el.value.trim() : '';
}

function checked(id) {
  const el = document.getElementById(id);
  return el ? el.checked : false;
}

function activeTab() {
  const btn = document.querySelector('.tab-btn.active');
  return btn ? btn.dataset.tab : 'migrate';
}

/* ── Env var collection ───────────────────────────────────────────────── */

function envVarsForPlatform(platform, urlInputMap) {
  if (!platform || !PLATFORMS[platform]) return [];
  const cfg  = PLATFORMS[platform];
  const vars = [];

  if (cfg.urlVar) {
    const inputId = urlInputMap[cfg.urlVar];
    const urlVal  = inputId ? val(inputId) : '';
    vars.push({ name: cfg.urlVar, value: urlVal || null });
  }

  if (cfg.extraVars) {
    cfg.extraVars.forEach(v => vars.push({ name: v, value: null }));
  } else if (cfg.tokenVar) {
    vars.push({ name: cfg.tokenVar, value: null });
  }

  return vars;
}

/* Merge var lists, deduplicating by name */
function mergeVars(srcVars, destVars) {
  const seen   = new Set(srcVars.map(v => v.name));
  const merged = [...srcVars];
  for (const v of destVars) {
    if (!seen.has(v.name)) { merged.push(v); seen.add(v.name); }
  }
  return merged;
}

/* ── DOM-based code block renderer ───────────────────────────────────── */

/* Append a text node */
function txt(parent, text) {
  parent.appendChild(document.createTextNode(text));
}

/* Append a span with a CSS class and text content */
function span(parent, cls, text) {
  const s = document.createElement('span');
  s.className = cls;
  s.textContent = text;
  parent.appendChild(s);
}

function renderExportsToDom(container, vars) {
  container.textContent = '';
  vars.forEach((v, i) => {
    if (i > 0) txt(container, '\n');
    span(container, 'code-keyword', 'export');
    txt(container, ' ');
    span(container, 'code-var', v.name);
    txt(container, '=');
    if (v.value) {
      txt(container, v.value);
    } else {
      span(container, 'code-placeholder', '<your-' + v.name.toLowerCase().replace(/_/g, '-') + '>');
    }
  });
}

function renderCommandToDom(container, args) {
  container.textContent = '';
  span(container, 'code-cmd', 'docker compose run');
  txt(container, ' --rm gitporter');
  args.forEach((arg, i) => {
    txt(container, ' \\\n  ' + arg + (i < args.length - 1 ? '' : ''));
  });
}

/* Plain-text versions for clipboard */
function exportsToText(vars) {
  return vars.map(v => {
    const value = v.value || ('<your-' + v.name.toLowerCase().replace(/_/g, '-') + '>');
    return 'export ' + v.name + '=' + value;
  }).join('\n');
}

function commandToText(args) {
  return 'docker compose run --rm gitporter \\\n' + args.map((a, i) => '  ' + a + (i < args.length - 1 ? ' \\' : '')).join('\n');
}

/* ── Build migrate command ────────────────────────────────────────────── */

function buildMigrate() {
  const src  = val('m-source');
  const dest = val('m-dest');
  const mode = val('m-mode');
  if (!src || !dest || !mode) return null;

  const vars = mergeVars(
    envVarsForPlatform(src,  URL_INPUTS),
    envVarsForPlatform(dest, URL_INPUTS)
  );

  const args = ['migrate --source ' + src + ' --dest ' + dest];

  let modeArg = '--mode ' + mode;
  const orgVal  = val('m-org');
  const userVal = val('m-user');
  const repoVal = val('m-repo');
  if (orgVal)  modeArg += ' -o ' + orgVal;
  if (userVal) modeArg += ' -u ' + userVal;
  if (repoVal) modeArg += ' -r ' + repoVal;
  args.push(modeArg);

  const vis = val('m-visibility') || 'public';
  if (vis !== 'public') args.push('--visibility ' + vis);

  const filters = [];
  const filterName  = val('m-filter-name');
  const filterLang  = val('m-filter-lang');
  const filterTopic = val('m-filter-topic');
  const ignoreRepos = val('m-ignore-repos');
  const cleanup     = val('m-cleanup');
  if (filterName)  filters.push('--filter-name "' + filterName + '"');
  if (filterLang)  filters.push('--filter-language ' + filterLang);
  if (filterTopic) filters.push('--filter-topic ' + filterTopic);
  if (ignoreRepos) filters.push('--ignore-repos "' + ignoreRepos + '"');
  if (cleanup)     filters.push('--cleanup-action ' + cleanup);
  if (checked('m-lfs'))      filters.push('--lfs');
  if (checked('m-releases')) filters.push('--include-releases');
  if (filters.length) args.push(filters.join(' '));

  const advanced = [];
  if (checked('m-dry-run'))           advanced.push('--dry-run');
  if (checked('m-disable-workflows')) advanced.push('--disable-workflows');
  if (checked('m-verbose'))           advanced.push('--verbose');
  if (advanced.length) args.push(advanced.join(' '));

  return { vars, args };
}

/* ── Build delete command ─────────────────────────────────────────────── */

function buildDelete() {
  const dest = val('d-dest');
  const org  = val('d-org');
  if (!dest || !org) return null;

  const vars = envVarsForPlatform(dest, D_URL_INPUTS);

  const args = ['delete --dest ' + dest + ' -o ' + org];

  const flags = [];
  if (checked('d-dry-run')) flags.push('--dry-run');
  if (checked('d-force'))   flags.push('--force');
  if (checked('d-verbose')) flags.push('--verbose');
  if (flags.length) args.push(flags.join(' '));

  return { vars, args };
}

/* ── Update output ────────────────────────────────────────────────────── */

const outPlaceholder = document.getElementById('output-placeholder');
const outContent     = document.getElementById('output-content');
const outExportsEl   = document.getElementById('output-exports');
const outCommandEl   = document.getElementById('output-command');

let lastExportsText = '';
let lastCommandText = '';

function update() {
  const tab    = activeTab();
  const result = tab === 'delete' ? buildDelete() : buildMigrate();

  if (!result) {
    outPlaceholder.classList.remove('hidden');
    outContent.classList.add('hidden');
    return;
  }

  const { vars, args } = result;

  renderExportsToDom(outExportsEl, vars);
  renderCommandToDom(outCommandEl, args);
  lastExportsText = exportsToText(vars);
  lastCommandText = commandToText(args);

  outPlaceholder.classList.add('hidden');
  outContent.classList.remove('hidden');
}

/* ── Copy to clipboard ────────────────────────────────────────────────── */

function makeCopyHandler(btnId, originalLabel, getText) {
  const btn = document.getElementById(btnId);
  btn.addEventListener('click', () => {
    navigator.clipboard.writeText(getText()).then(() => {
      btn.textContent = 'Copied!';
      btn.classList.add('copied');
      setTimeout(() => {
        btn.textContent = originalLabel;
        btn.classList.remove('copied');
      }, 1800);
    });
  });
}

makeCopyHandler('copy-exports', 'Copy exports', () => lastExportsText);
makeCopyHandler('copy-command', 'Copy command', () => lastCommandText);

/* ── Init ─────────────────────────────────────────────────────────────── */

updateMigrateFields();
updateDeleteFields();
update();

/* Shared site nav + footer + staleness-banner logic for all three pages.
   Each page mounts <div id="site-nav"></div> / <div id="site-footer"></div>
   and, once it knows its data's scrape timestamp, calls
   ModelCompassNav.checkStaleness(scrapedAtISOString). */
(function () {
  const PAGES = [
    { href: 'index.html', label: 'Picker', sub: 'Describe a task, get a model' },
    { href: 'shortlist.html', label: 'Shortlist', sub: 'Curated top models' },
    { href: 'models.html', label: 'All Models', sub: 'Full benchmark table' },
  ];

  function currentFile() {
    const path = location.pathname.split('/').pop();
    return path === '' ? 'index.html' : path;
  }

  function renderNav() {
    const mount = document.getElementById('site-nav');
    if (!mount) return;
    const current = currentFile();
    const currentPage = PAGES.find(p => p.href === current) || PAGES[0];
    mount.innerHTML =
      '<a class="brand" href="index.html">' +
        '<span class="brand-tile" aria-hidden="true">🧭</span>' +
        '<span class="brand-text">' +
          '<span class="brand-name">Model Compass</span>' +
          '<span class="brand-sub">' + currentPage.sub + '</span>' +
        '</span>' +
      '</a>' +
      '<nav class="tabs">' +
      PAGES.map(p => '<a class="tab' + (p.href === current ? ' active' : '') + '" href="' + p.href + '">' + p.label + '</a>').join('') +
      '</nav>' +
      '<div class="nav-actions">' +
        '<a class="btn btn-ghost" href="https://github.com/" target="_blank" rel="noopener">GitHub ↗</a>' +
        '<button class="theme-toggle" id="theme-toggle" type="button" aria-label="Switch theme" title="Switch theme"></button>' +
      '</div>';

    applyTheme(currentTheme());
    const btn = document.getElementById('theme-toggle');
    if (btn) btn.addEventListener('click', toggleTheme);
  }

  function renderFooter() {
    const mount = document.getElementById('site-footer');
    if (!mount) return;
    mount.innerHTML =
      '<span>Data: <a href="https://artificialanalysis.ai/models" target="_blank" rel="noopener">Artificial Analysis</a></span>' +
      '<span id="footer-scrape-date"></span>';
    applyStaleness(); // in case checkStaleness() already ran before this mount existed
  }

  // Moved here from each page (was duplicated 2x) so the >8-day staleness
  // check exists in exactly one place. Pages call checkStaleness() once they
  // know their data's scrape timestamp. Some pages call it synchronously
  // during initial parse (before #site-footer is mounted on DOMContentLoaded),
  // so the timestamp is cached and (re-)applied whenever the footer mounts.
  let lastScrapedAt = null;

  function applyStaleness() {
    if (!lastScrapedAt) return;
    const scraped = new Date(lastScrapedAt);
    if (isNaN(scraped.getTime())) return;

    const footerDate = document.getElementById('footer-scrape-date');
    if (footerDate) footerDate.textContent = 'Last scrape: ' + lastScrapedAt.slice(0, 10);

    const banner = document.getElementById('staleness-banner');
    const text = document.getElementById('staleness-text');
    if (!banner || !text) return;
    const ageDays = (Date.now() - scraped.getTime()) / 86400000;
    if (ageDays > 8) {
      text.textContent = 'Data from ' + lastScrapedAt.slice(0, 10) + ' (' + Math.floor(ageDays) + ' days old) — weekly scrape may be failing.';
      banner.hidden = false;
    } else {
      banner.hidden = true;
    }
  }

  function checkStaleness(scrapedAtISO) {
    if (!scrapedAtISO) return;
    lastScrapedAt = scrapedAtISO;
    applyStaleness();
  }

  /* ---- Theme toggle: 2-state light <-> dark, seeded from OS, sticky once clicked ---- */
  const THEME_KEY = 'mc-theme';

  function systemTheme() {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  // The stored value wins; absent one, we are following the OS.
  function currentTheme() {
    try { return localStorage.getItem(THEME_KEY) || systemTheme(); }
    catch (e) { return systemTheme(); }
  }
  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    const btn = document.getElementById('theme-toggle');
    if (btn) btn.textContent = theme === 'dark' ? '☀' : '☾'; // show the destination
  }
  function toggleTheme() {
    const next = currentTheme() === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem(THEME_KEY, next); } catch (e) {}
    applyTheme(next);
  }

  window.ModelCompassNav = { checkStaleness };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { renderNav(); renderFooter(); });
  } else {
    renderNav();
    renderFooter();
  }
})();

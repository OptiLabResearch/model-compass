/* Shared site nav + footer + staleness-banner logic for all three pages.
   Each page mounts <div id="site-nav"></div> / <div id="site-footer"></div>
   and, once it knows its data's scrape timestamp, calls
   ModelCompassNav.checkStaleness(scrapedAtISOString). */
(function () {
  const PAGES = [
    { href: 'index.html', label: 'Picker' },
    { href: 'shortlist.html', label: 'Shortlist' },
    { href: 'models.html', label: 'All Models' },
  ];

  function currentFile() {
    const path = location.pathname.split('/').pop();
    return path === '' ? 'index.html' : path;
  }

  function renderNav() {
    const mount = document.getElementById('site-nav');
    if (!mount) return;
    const current = currentFile();
    mount.innerHTML =
      '<a class="brand" href="index.html">Model Compass</a>' +
      '<div class="tabs">' +
      PAGES.map(p => '<a class="tab' + (p.href === current ? ' active' : '') + '" href="' + p.href + '">' + p.label + '</a>').join('') +
      '</div>' +
      '<a class="gh-link" href="https://github.com/" target="_blank" rel="noopener">GitHub ↗</a>';
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

  window.ModelCompassNav = { checkStaleness };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { renderNav(); renderFooter(); });
  } else {
    renderNav();
    renderFooter();
  }
})();

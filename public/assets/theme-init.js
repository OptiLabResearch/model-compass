  (function () {
    try {
      var t = localStorage.getItem('mc-theme');
      if (t === 'dark' || t === 'light') document.documentElement.setAttribute('data-theme', t);
    } catch (e) {}
  })();

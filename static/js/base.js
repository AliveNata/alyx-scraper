/* ── Footer copyright (runs after DOM is ready) ── */
(function () {
  var el = document.getElementById('footerCopyright');
  if (el) {
    var year = new Date().getFullYear();
    el.innerHTML =
      '&copy; ' + year +
      ' <a href="https://alyxlabs.tech/" target="_blank">AlyxLabs</a>.' +
      ' All rights reserved.';
  }
})();

/* ── SHARED: Theme + Lang ── */
let currentLang = localStorage.getItem('ax_lang') || 'id';

const BASE_L = {
  id: { footer_desc:'Multi-platform scraper untuk riset dan analisis data.', footer_docs:'Docs', footer_sociabuzz:'Dukungan SociaBuzz', footer_donate:'Dukung AlyxLabs', footer_disc:'Gunakan dengan etika.' },
  en: { footer_desc:'Multi-platform scraper for research and data analysis.', footer_docs:'Docs', footer_sociabuzz:'Support via SociaBuzz', footer_donate:'Support AlyxLabs', footer_disc:'Use ethically.' }
};

function getL(){
  const p = window.PAGE_L || { id:{}, en:{} };
  return { id:{...BASE_L.id,...p.id}, en:{...BASE_L.en,...p.en} };
}
function tr(k){ const L=getL(); return(L[currentLang]||L.id)[k]||(L.id[k])||k }

function applyLang(){
  document.querySelectorAll('[data-i18n]').forEach(el=>{ const v=tr(el.getAttribute('data-i18n')); if(v)el.textContent=v });
  document.querySelectorAll('[data-i18n-ph]').forEach(el=>{ const v=tr(el.getAttribute('data-i18n-ph')); if(v)el.placeholder=v });
  if(window.onLangChange) window.onLangChange();
}

function toggleLang(){
  currentLang = currentLang === 'id' ? 'en' : 'id';
  document.getElementById('langBtn').innerHTML =
    currentLang === 'id'
      ? '<span class="fi fi-id"></span>'
      : '<span class="fi fi-gb"></span>';

  localStorage.setItem('ax_lang', currentLang);
  applyLang();
}

function toggleTheme(){
  const dark = document.documentElement.getAttribute('data-theme')==='dark';
  const next = dark?'light':'dark';
  document.documentElement.setAttribute('data-theme', next);
  document.getElementById('themeIcon').className = next==='dark'?'bi bi-moon-fill':'bi bi-sun-fill';
  localStorage.setItem('ax_theme', next);
  if(window.onThemeChange) window.onThemeChange(next);
}

(function(){
  const t = localStorage.getItem('ax_theme')||'light';
  document.documentElement.setAttribute('data-theme', t);
  document.getElementById('themeIcon').className = t==='dark'?'bi bi-moon-fill':'bi bi-sun-fill';
  document.getElementById('langBtn').innerHTML = currentLang === 'id' ? '<span class="fi fi-id"></span>' : '<span class="fi fi-gb"></span>';
  // DOMContentLoaded guarantees window.PAGE_L (set in extra_js) is ready
  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', function(){ applyLang(); applyTickerSpeed(); });
  } else {
    applyLang();
    applyTickerSpeed();
  }
})();

function applyTickerSpeed(){
  try{
    var v = localStorage.getItem('tickerDuration');
    if(v){
      var track = document.querySelector('.ticker-track');
      if(track) track.style.animationDuration = parseInt(v,10) + 's';
    }
  }catch(e){}
}

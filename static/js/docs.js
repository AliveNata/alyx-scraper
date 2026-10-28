// Sidebar labels that follow the navbar language toggle
window.PAGE_L = {
  id: { doc_fitur:'Fitur', doc_newfeat:'Fitur Baru', doc_citation:'Sitasi', doc_notif:'Notifikasi' },
  en: { doc_fitur:'Features', doc_newfeat:'New Features', doc_citation:'Citation', doc_notif:'Notifications' }
};
// Rich doc content swaps via a data-lang attribute + CSS (keeps HTML formatting intact)
window.onLangChange = function(){ document.documentElement.setAttribute('data-lang', currentLang); };
document.documentElement.setAttribute('data-lang', currentLang);

// Sidebar active highlight on scroll
(function(){
  const sections = document.querySelectorAll('.doc-section');
  const links = document.querySelectorAll('.sidebar a[href^="#"]');
  window.addEventListener('scroll', () => {
    let cur = '';
    sections.forEach(s => { if(window.scrollY >= s.offsetTop - 100) cur = s.id });
    links.forEach(a => { a.classList.toggle('active', a.getAttribute('href') === '#' + cur) });
  });
})();

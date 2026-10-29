/* window.ENABLED_PLATFORMS is injected inline by the template before this file loads */

function applyEnabledPlatforms(){
  const en = window.ENABLED_PLATFORMS || [];
  document.querySelectorAll('.pcb').forEach(cb=>{
    const chip = cb.closest('.chip');
    if(!en.includes(cb.value)){ cb.checked=false; if(chip) chip.style.display='none'; }
  });
  document.querySelectorAll('.plat-row').forEach(row=>{
    const vis=[...row.querySelectorAll('.chip')].some(c=>c.style.display!=='none');
    if(!vis) row.style.display='none';
  });
}
applyEnabledPlatforms();

window.PAGE_L = {
id:{
  stat_results:'Total Hasil',stat_platforms:'Platform Aktif',stat_keywords:'Keywords',stat_duration:'Durasi',
  keywords_label:'Keywords (pisah koma)',keywords_ph:'contoh: teknologi, AI, startup',
  location_label:'Lokasi',location_ph:'Jakarta',location_optional:'(opsional)',location_hint:'Kosongkan = pencarian umum · pisah koma untuk multi-lokasi',start_btn:'Mulai Scraping',stop_btn:'Berhenti Scraping',
  save_search:'Simpan Pencarian',saved_searches:'Pencarian Tersimpan',save_name_label:'Nama Preset',save_name_ph:'cth: Bengkel Jakarta',save_btn:'Simpan',cancel_btn:'Batal',no_saved:'Belum ada preset.',load_btn:'Muat',
  dl_all_platforms:'Semua platform',cite_btn_title:'Salin sitasi',cite_copied:'Sitasi disalin!',
  notify_title:'Notifikasi saat selesai',notify_email_label:'Email penerima',notify_email_ph:'email@contoh.com',notify_webhook_label:'Webhook URL (opsional)',notify_webhook_ph:'https://hooks.slack.com/...',notify_hint:'Kirim ringkasan hasil via email atau webhook setelah scraping selesai.',
  platforms_label:'Pilih Platform',cat_news:'Berita',cat_forum:'Forum',cat_social:'Sosial',cat_ref:'Referensi',cat_journal:'Jurnal',cat_video:'Video',
  meta_title:'Catatan Koleksi',meta_cite:'Salin',meta_keyword:'Keyword',meta_source:'Sumber',meta_location:'Lokasi',meta_time:'Waktu koleksi',meta_total:'Total hasil',fulltext_label:'Ambil teks lengkap artikel',fulltext_hint:'(lebih lambat, sumber berita saja)',date_from_label:'Dari tanggal',date_to_label:'Sampai tanggal',date_optional:'(opsional)',date_hint:'Filter diterapkan ke semua hasil. Kosongkan untuk ambil semua tanggal.',analysis_title:'Analisis: Kata Terbanyak',timeline_title:'Distribusi Waktu',
  status_ready:'Siap untuk scraping.',results_title:'Hasil Scraping',
  filter_all:'Semua',search_ph:'Cari...',
  col_platform:'Platform',col_title:'Judul',col_keyword:'Keyword',col_date:'Tanggal',
  empty_state:'Belum ada hasil.',
  img_search:'Cari Gambar',img_query_ph:'Kata kunci gambar...',img_url:'Scrape dari URL',
  img_upload:'Upload & Cari',img_drop:'Klik atau drag & drop gambar',
  img_results:'Hasil Gambar',img_empty:'Cari atau upload gambar.',img_open:'Buka',img_related:'Cari Mirip',
  detail_title:'Detail Hasil',
  donate_nudge_pre:'Gratis selamanya - kalau berguna, ',donate_nudge_cta:'dukung AlyxLabs'
},
en:{
  stat_results:'Total Results',stat_platforms:'Active Platforms',stat_keywords:'Keywords',stat_duration:'Duration',
  keywords_label:'Keywords (comma separated)',keywords_ph:'e.g.: technology, AI, startup',
  location_label:'Location',location_ph:'Jakarta',location_optional:'(optional)',location_hint:'Leave empty for general search · comma-separate for multi-location',start_btn:'Start Scraping',stop_btn:'Stop Scraping',
  save_search:'Save Search',saved_searches:'Saved Searches',save_name_label:'Preset Name',save_name_ph:'e.g.: Bengkel Jakarta',save_btn:'Save',cancel_btn:'Cancel',no_saved:'No saved presets.',load_btn:'Load',
  dl_all_platforms:'All platforms',cite_btn_title:'Copy citation',cite_copied:'Citation copied!',
  notify_title:'Notify when done',notify_email_label:'Recipient email',notify_email_ph:'email@example.com',notify_webhook_label:'Webhook URL (optional)',notify_webhook_ph:'https://hooks.slack.com/...',notify_hint:'Send a summary via email or webhook when scraping finishes.',
  platforms_label:'Select Platforms',cat_news:'News',cat_forum:'Forums',cat_social:'Social',cat_ref:'Reference',cat_journal:'Journals',cat_video:'Video',
  meta_title:'Collection Record',meta_cite:'Copy',meta_keyword:'Keyword',meta_source:'Sources',meta_location:'Location',meta_time:'Collected at',meta_total:'Total results',fulltext_label:'Fetch full article text',fulltext_hint:'(slower, news sources only)',date_from_label:'From date',date_to_label:'To date',date_optional:'(optional)',date_hint:'Filter applied to all results. Leave empty to include all dates.',analysis_title:'Analysis: Top Terms',timeline_title:'Timeline',
  status_ready:'Ready to scrape.',results_title:'Scraping Results',
  filter_all:'All',search_ph:'Search...',
  col_platform:'Platform',col_title:'Title',col_keyword:'Keyword',col_date:'Date',
  empty_state:'No results yet.',
  img_search:'Search Images',img_query_ph:'Image keywords...',img_url:'Scrape from URL',
  img_upload:'Upload & Search',img_drop:'Click or drag & drop image',
  img_results:'Image Results',img_empty:'Search or upload images.',img_open:'Open',img_related:'Find Similar',
  detail_title:'Result Details',
  donate_nudge_pre:'Always free - if useful, ',donate_nudge_cta:'support AlyxLabs'
}
};

window.onLangChange = function(){
  rebuildFilterChips();
  if(allMeta) renderMeta(allMeta);
  renderSavedSearches();
  // Update donate nudge text
  const pre = document.getElementById('donateNudgeText');
  const cta = document.getElementById('donateNudgeLink');
  if(pre) pre.textContent = tr('donate_nudge_pre');
  if(cta) cta.textContent = tr('donate_nudge_cta');
};

let currentJob=null, pollTimer=null, allResults=[], allMeta=null, selImgUrl='';
let filterPlatform='', scrapeStart=null, _viewData=[];
const PAGE_SIZE=50;
let currentPage=0;
let citeFormat='apa7';

function showTab(tab){
  document.getElementById('tab-scraper').style.display=tab==='scraper'?'':'none';
  document.getElementById('tab-images').style.display=tab==='images'?'':'none';
  ['navScraper','navImages','mNavScraper','mNavImages'].forEach(id=>{
    const el=document.getElementById(id);if(el)el.classList.remove('active');
  });
  document.getElementById(tab==='scraper'?'navScraper':'navImages')?.classList.add('active');
  document.getElementById(tab==='scraper'?'mNavScraper':'mNavImages')?.classList.add('active');
}

document.querySelectorAll('.chip').forEach(b=>{
  b.addEventListener('click',()=>{
    const c=b.querySelector('input');c.checked=!c.checked;
    b.classList.toggle('active',c.checked);updatePlatformsStat();
  });
});

function updatePlatformsStat(){ document.getElementById('statPlatforms').textContent=document.querySelectorAll('.pcb:checked').length }
function updateKeywordsStat(){
  const v=document.getElementById('keywords').value.trim();
  document.getElementById('statKeywords').textContent=v?v.split(',').filter(k=>k.trim()).length:0;
}

function esc(s){return s!=null?String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'):''}

function platCat(p){
  if(p==='Google News')return 'cat-n';
  if(p==='News Sites')return 'cat-ns';
  if(p==='GDELT')return 'cat-n';
  if(p==='Wikipedia')return 'cat-n';
  if(['OpenAlex','Semantic Scholar'].includes(p))return 'cat-n';
  if(p==='YouTube')return 'cat-n';
  if(p==='Kaskus')return 'cat-f';
  return 'cat-d';
}

function setStatus(m,loading){
  document.getElementById('statusBar').innerHTML=(loading?'<div class="spin"></div>':'<i class="bi bi-info-circle"></i>')+'<span>'+esc(m)+'</span>';
}

function showProg(show,indet=false){
  const w=document.getElementById('progWrap'),b=document.getElementById('progBar');
  w.style.display=show?'':'none';
  b.className='prog-bar'+(indet?' indet':'');
  if(!indet)b.style.width='0%';
}

function toast(msg,type='info',dur=3500){
  const ctr=document.getElementById('toastCtr');
  const icons={info:'<i class="bi bi-info-circle ti-info"></i>',ok:'<i class="bi bi-check-circle-fill ti-ok"></i>',err:'<i class="bi bi-x-circle-fill ti-err"></i>'};
  const el=document.createElement('div');
  el.className='toast'+(type==='ok'?' t-ok':type==='err'?' t-err':'');
  el.innerHTML=(icons[type]||icons.info)+esc(msg);
  ctr.appendChild(el);
  setTimeout(()=>{el.style.transition='opacity .3s';el.style.opacity='0';setTimeout(()=>el.remove(),300)},dur);
}

function openModal(id){document.getElementById(id).classList.add('open')}
function closeModal(id){document.getElementById(id).classList.remove('open')}
document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeModal('detailModal');closeModal('imgModal')}});

document.getElementById('filterChips').addEventListener('click',e=>{
  const chip=e.target.closest('.fchip');if(!chip)return;
  filterPlatform=chip.dataset.plat||'';
  document.querySelectorAll('.fchip').forEach(f=>f.classList.remove('active'));
  chip.classList.add('active');filterResults();
});

function shakeDates(){
  ['dateFrom','dateTo'].forEach(id=>{
    const el=document.getElementById(id);
    el.style.borderColor='#ef4444';
    el.animate([{transform:'translateX(0)'},{transform:'translateX(-6px)'},{transform:'translateX(6px)'},
      {transform:'translateX(-4px)'},{transform:'translateX(4px)'},{transform:'translateX(0)'}],{duration:400});
    setTimeout(()=>{el.style.borderColor='';},1500);
  });
  document.getElementById('dateFrom').scrollIntoView({block:'center'});
}

function setScrapingState(active){
  const btn=document.getElementById('startBtn');
  if(!btn)return;
  const icon=btn.querySelector('i');
  const label=btn.querySelector('span[data-i18n]')||btn.querySelector('span');
  if(active){
    btn.className='btn-stop';
    btn.onclick=stopScraping;
    if(icon){icon.className='bi bi-stop-fill';}
    if(label){label.setAttribute('data-i18n','stop_btn');label.textContent=tr('stop_btn');}
  } else {
    btn.className='btn-p';
    btn.onclick=startScraping;
    btn.disabled=false;
    if(icon){icon.className='bi bi-play-fill';}
    if(label){label.setAttribute('data-i18n','start_btn');label.textContent=tr('start_btn');}
  }
}

async function stopScraping(){
  if(!currentJob)return;
  if(pollTimer){clearInterval(pollTimer);pollTimer=null;}
  setStatus(currentLang==='id'?'Menghentikan...':'Stopping...',true);
  try{await fetch('/api/cancel/'+currentJob,{method:'POST'});}catch(e){}
  setTimeout(()=>{
    showProg(false);
    setScrapingState(false);
    setStatus(currentLang==='id'?'Scraping dihentikan.':'Scraping stopped.');
  },800);
}

async function startScraping(){
  const kw=document.getElementById('keywords').value.trim();
  const loc=document.getElementById('location').value.trim();
  const pls=Array.from(document.querySelectorAll('.pcb:checked')).map(e=>e.value);
  if(!kw){toast(currentLang==='id'?'Masukkan keywords!':'Enter keywords!','err');return}
  if(!pls.length){toast(currentLang==='id'?'Pilih minimal 1 platform!':'Select at least 1 platform!','err');return}
  const notifyEmail=(document.getElementById('notifyEmail')?.value||'').trim();
  const notifyWebhook=(document.getElementById('notifyWebhook')?.value||'').trim();
  const df=document.getElementById('dateFrom').value, dt=document.getElementById('dateTo').value;
  if(pls.some(p=>['GDELT','OpenAlex','Semantic Scholar'].includes(p)) && (!df||!dt)){
    shakeDates();
    toast(currentLang==='id'?'Pilih rentang tanggal (dari & sampai) untuk GDELT/Jurnal':'Pick a date range (from & to) for GDELT/Journal','err');
    return;
  }
  setStatus(currentLang==='id'?'Memulai...':'Starting...',true);
  showProg(true,true);
  scrapeStart=Date.now();
  try{
    const notifyFormat=(document.getElementById('dlFormat')?.value||'csv');
    const r=await fetch('/api/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({keywords:kw,location:loc,platforms:pls,full_text:document.getElementById('fullTextToggle').checked,date_from:document.getElementById('dateFrom').value||'',date_to:document.getElementById('dateTo').value||'',notify_email:notifyEmail,notify_webhook:notifyWebhook,notify_format:notifyFormat})});
    const d=await r.json();
    if(!d.ok){setStatus('Error: '+(d.error||''));showProg(false);document.getElementById('startBtn').disabled=false;toast('Error: '+(d.error||''),'err');return}
    currentJob=d.job_id;
    setScrapingState(true);
    if(pollTimer)clearInterval(pollTimer);
    pollTimer=setInterval(poll,2000);poll();
  }catch(e){setStatus('Error: '+e.message);showProg(false);setScrapingState(false);toast('Error: '+e.message,'err')}
}

function _showNotifyToast(result, addr){
  if(result==='sent'){
    toast((currentLang==='id'?'Email terkirim ke ':'Email sent to ')+(addr||''),'ok');
  }else if(result==='failed'){
    toast(currentLang==='id'?'Gagal kirim email - cek pengaturan SMTP':'Email failed - check SMTP settings','err');
  }
}

async function poll(){
  if(!currentJob)return;
  try{
    const r=await fetch('/api/status/'+currentJob),j=await r.json();
    if(!j.ok)return;
    setStatus(j.message+' ('+j.count+')',j.status==='running');
    if(j.status==='finished'){
      clearInterval(pollTimer);pollTimer=null;showProg(false);
      await loadResults();
      setScrapingState(false);
      const dur=scrapeStart?((Date.now()-scrapeStart)/1000).toFixed(1)+'s':'-';
      document.getElementById('statDuration').textContent=dur;
      toast((currentLang==='id'?'Selesai! ':'Done! ')+j.count+' hasil','ok');
      if(j.notify_result){
        _showNotifyToast(j.notify_result, j.notify_email_addr);
      }else if(document.getElementById('notifyEmail')?.value.trim()){
        // email still sending - poll a few more times
        let tries=0;
        const waitEmail=setInterval(async()=>{
          tries++;
          try{
            const rs=await fetch('/api/status/'+currentJob), jj=await rs.json();
            if(jj.notify_result){clearInterval(waitEmail);_showNotifyToast(jj.notify_result,jj.notify_email_addr);}
          }catch(e){}
          if(tries>=10)clearInterval(waitEmail);
        },2000);
      }
    }else if(j.status==='cancelled'){
      clearInterval(pollTimer);pollTimer=null;showProg(false);
      setScrapingState(false);
      setStatus(currentLang==='id'?'Scraping dihentikan.':'Scraping stopped.');
    }else if(j.status==='error'){
      clearInterval(pollTimer);pollTimer=null;showProg(false);
      setScrapingState(false);
      toast('Error: '+j.message,'err');
    }
  }catch(e){}
}

async function loadResults(){
  const r=await fetch('/api/results/'+currentJob),j=await r.json();
  if(!j.ok)return;
  allResults=j.results||[];
  allMeta=j.metadata||null;renderMeta(allMeta);renderAnalysis(allResults);renderTimeline(allResults);
  document.getElementById('statResults').textContent=allResults.length;
  filterPlatform='';rebuildFilterChips();filterResults();
}

function renderMeta(m){
  const box=document.getElementById('collectionMeta');
  if(!m){box.style.display='none';return}
  const per=Object.entries(m.per_source||{}).map(([k,v])=>esc(k)+': '+v).join(', ');
  const rows=[[tr('meta_keyword'),esc((m.keywords||[]).join(', '))||'-']];
  if(m.location)rows.push([tr('meta_location'),esc(m.location)]);
  rows.push([tr('meta_source'),esc((m.sources||[]).join(', '))]);
  rows.push([tr('meta_time'),esc(m.collected_at||'-')]);
  rows.push([tr('meta_total'),(m.total_results||0)+(per?' ('+per+')':'')]);
  document.getElementById('collectionMetaBody').innerHTML=
    rows.map(([k,v])=>'<div><strong>'+k+':</strong> '+v+'</div>').join('');
  box.style.display='';
}

const STOPWORDS=new Set(('yang di ke dari dan atau untuk pada dengan ini itu ada tidak akan juga sudah saya kami kita mereka dia ia nya para adalah dalam oleh sebagai karena agar bahwa jika maka namun tetapi serta atas bawah antara hingga sampai lebih paling sangat bisa dapat harus telah masih saat ketika setelah sebelum tersebut yaitu yakni bagi hal ini itu satu dua tiga per apa siapa kapan bagaimana mengapa kenapa the a an of to in and or for on with is are was were be been being at by from as it its this that these those you your we our they their he she his her but not no if then than so such about into over under out up down more most very can could will would should has have had do does did been '+
  'com www https http net org id co').split(/\s+/).filter(Boolean));
function computeTopTerms(results,n=15){
  const freq={};
  results.forEach(r=>{
    const text=((r.title||'')+' '+(r.content||'')+' '+(r.full_text||'')).toLowerCase();
    (text.match(/[a-zÀ-ɏ]{3,}/g)||[]).forEach(w=>{
      if(STOPWORDS.has(w))return;
      freq[w]=(freq[w]||0)+1;
    });
  });
  return Object.entries(freq).sort((a,b)=>b[1]-a[1]).slice(0,n);
}
function renderAnalysis(results){
  const box=document.getElementById('analysisPanel');
  if(!results||!results.length){box.style.display='none';return}
  const terms=computeTopTerms(results);
  if(!terms.length){box.style.display='none';return}
  const max=terms[0][1];
  document.getElementById('analysisBody').innerHTML=terms.map(([w,c])=>
    '<div style="display:flex;align-items:center;gap:8px;margin:3px 0">'+
      '<div style="width:130px;color:var(--t1);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+esc(w)+'</div>'+
      '<div style="flex:1;background:var(--glass-b);border-radius:4px;height:14px;overflow:hidden">'+
        '<div style="width:'+Math.round(c/max*100)+'%;height:100%;background:var(--accent)"></div></div>'+
      '<div style="width:34px;text-align:right;color:var(--t2)">'+c+'</div>'+
    '</div>').join('');
  box.style.display='';
}

function renderTimeline(results){
  const box=document.getElementById('timelinePanel');
  const buckets={};
  results.forEach(r=>{
    const d=(r.date||'').trim();
    let key='';
    if(d.length>=7 && d[4]==='-') key=d.slice(0,7);
    else if(/^\d{4}$/.test(d.slice(0,4))) key=d.slice(0,4);
    if(key) buckets[key]=(buckets[key]||0)+1;
  });
  const rows=Object.entries(buckets).sort((a,b)=>a[0].localeCompare(b[0]));
  if(rows.length<2){box.style.display='none';return}
  const max=Math.max(...rows.map(r=>r[1]));
  document.getElementById('timelineBody').innerHTML=rows.map(([k,c])=>
    '<div style="display:flex;align-items:center;gap:8px;margin:3px 0">'+
      '<div style="width:72px;color:var(--t1)">'+esc(k)+'</div>'+
      '<div style="flex:1;background:var(--glass-b);border-radius:4px;height:14px;overflow:hidden">'+
        '<div style="width:'+Math.round(c/max*100)+'%;height:100%;background:var(--accent)"></div></div>'+
      '<div style="width:34px;text-align:right;color:var(--t2)">'+c+'</div>'+
    '</div>').join('');
  box.style.display='';
}

function copyCitation(){
  if(!allMeta)return;
  const m=allMeta, kw=(m.keywords||[]).join(', '), src=(m.sources||[]).join(', ');
  const cite=currentLang==='id'
    ? 'Data dikumpulkan pada '+(m.collected_at||'-')+' menggunakan AlyxLabs Scraper (keyword: "'+kw+'"; sumber: '+src+'; '+(m.total_results||0)+' item). Diakses dari https://scraper.alyxlabs.tech.'
    : 'Data collected on '+(m.collected_at||'-')+' using AlyxLabs Scraper (keyword: "'+kw+'"; sources: '+src+'; '+(m.total_results||0)+' items). Retrieved from https://scraper.alyxlabs.tech.';
  navigator.clipboard.writeText(cite).then(
    ()=>toast(currentLang==='id'?'Sitasi disalin!':'Citation copied!'),
    ()=>toast(currentLang==='id'?'Gagal menyalin':'Copy failed','err')
  );
}

function rebuildFilterChips(){
  const ps=[...new Set(allResults.map(r=>r.platform))];
  const counts={};allResults.forEach(r=>counts[r.platform]=(counts[r.platform]||0)+1);
  const ctr=document.getElementById('filterChips');
  ctr.innerHTML='<span class="fchip'+(filterPlatform===''?' active':'')+'" data-plat=""><i class="bi bi-grid"></i> '+tr('filter_all')+'</span>';
  ps.forEach(p=>{
    const cat=platCat(p);const el=document.createElement('span');
    el.className='fchip'+(filterPlatform===p?' active':'');el.dataset.plat=p;
    el.innerHTML='<span class="ptag '+cat+'">'+esc(p)+'</span><span class="fchip-count">'+counts[p]+'</span>';
    ctr.appendChild(el);
  });
  const dlSel=document.getElementById('dlPlatform');
  if(dlSel){
    const cur=dlSel.value;
    dlSel.innerHTML='<option value="">'+esc(tr('dl_all_platforms'))+'</option>'+
      ps.map(p=>'<option value="'+esc(p)+'"'+(p===cur?' selected':'')+'>'+esc(p)+'</option>').join('');
  }
}

function filterResults(){
  const q=document.getElementById('filterSearch').value.toLowerCase();
  let f=allResults;
  if(filterPlatform)f=f.filter(r=>r.platform===filterPlatform);
  if(q)f=f.filter(r=>(r.title||'').toLowerCase().includes(q)||(r.content||'').toLowerCase().includes(q)||(r.keyword||'').toLowerCase().includes(q));
  render(f);
}

function render(data){
  _viewData=data;
  currentPage=0;
  document.getElementById('resultCount').textContent=data.length;
  if(!data.length){
    document.getElementById('resultsBody').innerHTML='';
    document.getElementById('emptyState').style.display='';
    renderPagination();
    return;
  }
  document.getElementById('emptyState').style.display='none';
  renderPage();
  renderPagination();
}

function renderPage(){
  const tb=document.getElementById('resultsBody');
  const start=currentPage*PAGE_SIZE;
  const slice=_viewData.slice(start,start+PAGE_SIZE);
  tb.innerHTML=slice.map((r,i)=>{
    const gi=start+i;
    const cat=platCat(r.platform);
    const title=esc((r.title||'').substring(0,75)+(r.title&&r.title.length>75?'...':''));
    const link=r.url?'<a href="'+esc(r.url)+'" target="_blank" onclick="event.stopPropagation()" style="color:var(--accent)"><i class="bi bi-box-arrow-up-right"></i></a>':'';
    const cite='<button class="btn-cite" onclick="copyCiteRow('+gi+');event.stopPropagation()" title="'+esc(tr('cite_btn_title'))+'"><i class="bi bi-quote"></i></button>';
    return '<tr data-i="'+gi+'"><td style="color:var(--t3);font-size:.77rem">'+(gi+1)+'</td><td><span class="ptag '+cat+'">'+esc(r.platform)+'</span></td><td title="'+esc(r.content||r.title)+'">'+title+'</td><td><span style="font-size:.78rem;color:var(--t3)">'+esc(r.keyword)+'</span></td><td><span style="font-size:.78rem;color:var(--t3)">'+esc(r.date)+'</span></td><td style="white-space:nowrap">'+link+cite+'</td></tr>';
  }).join('');
  tb.querySelectorAll('tr').forEach(row=>row.addEventListener('click',()=>openDetail(parseInt(row.dataset.i))));
}

function renderPagination(){
  const pg=document.getElementById('paginationBar');
  if(!pg)return;
  const total=_viewData.length;
  if(total<=PAGE_SIZE){pg.style.display='none';return}
  pg.style.display='';
  const totalPages=Math.ceil(total/PAGE_SIZE);
  const start=currentPage*PAGE_SIZE+1;
  const end=Math.min((currentPage+1)*PAGE_SIZE,total);
  pg.innerHTML=
    '<button class="btn-pg" onclick="goToPage('+(currentPage-1)+')"'+(currentPage===0?' disabled':'')+'>'+
      '<i class="bi bi-chevron-left"></i></button>'+
    '<span class="pg-info">'+start+'-'+end+' / '+total+'</span>'+
    '<button class="btn-pg" onclick="goToPage('+(currentPage+1)+')"'+(currentPage>=totalPages-1?' disabled':'')+'>'+
      '<i class="bi bi-chevron-right"></i></button>';
}

function goToPage(p){
  const totalPages=Math.ceil(_viewData.length/PAGE_SIZE);
  if(p<0||p>=totalPages)return;
  currentPage=p;
  renderPage();
  renderPagination();
  const tw=document.querySelector('.table-wrap');
  if(tw)tw.scrollTop=0;
}

function openDetail(i){
  const r=_viewData[i];if(!r)return;
  const cat=platCat(r.platform);
  document.getElementById('detailBody').innerHTML=
    '<div class="d-row"><div class="d-lbl">Platform</div><div class="d-val"><span class="ptag '+cat+'">'+esc(r.platform)+'</span></div></div>'+
    '<div class="d-row"><div class="d-lbl">Keyword</div><div class="d-val">'+esc(r.keyword)+'</div></div>'+
    '<div class="d-row"><div class="d-lbl">Judul</div><div class="d-val" style="font-weight:600">'+esc(r.title)+'</div></div>'+
    (r.content?'<div class="d-row"><div class="d-lbl">Konten</div><div class="d-val" style="color:var(--t2)">'+esc(r.content.substring(0,500))+(r.content.length>500?'...':'')+'</div></div>':'')+
    (r.full_text?'<div class="d-row"><div class="d-lbl">'+(currentLang==='id'?'Teks Lengkap':'Full Text')+'</div><div class="d-val" style="color:var(--t2);max-height:300px;overflow-y:auto;white-space:pre-wrap;line-height:1.6">'+esc(r.full_text)+'</div></div>':'')+
    '<div class="d-row"><div class="d-lbl">Tanggal</div><div class="d-val">'+esc(r.date)+'</div></div>'+
    (r.source?'<div class="d-row"><div class="d-lbl">Sumber</div><div class="d-val">'+esc(r.source)+'</div></div>':'')+
    (r.url?'<div class="d-row"><div class="d-lbl">URL</div><div class="d-val"><a href="'+esc(r.url)+'" target="_blank" style="color:var(--accent);word-break:break-all">'+esc(r.url)+'</a></div></div>':'');
  openModal('detailModal');
}

function clearResults(){
  allResults=[];_viewData=[];filterPlatform='';
  render([]);rebuildFilterChips();setStatus(tr('status_ready'));
  document.getElementById('statResults').textContent='0';
  document.getElementById('statDuration').textContent='-';
  currentJob=null;
}

function dl(f){
  if(!currentJob||!allResults.length){toast(currentLang==='id'?'Belum ada data!':'No data!','err');return}
  const plat=(document.getElementById('dlPlatform')?.value||'').trim();
  window.location='/api/download/'+currentJob+'/'+f+(plat?'?platform='+encodeURIComponent(plat):'');
}

function imgStatus(m,show=true){
  const e=document.getElementById('imgStatus');
  e.style.display=show?'':'none';
  e.innerHTML='<div class="spin"></div><span>'+esc(m)+'</span>';
}

function renderImgs(imgs){
  const g=document.getElementById('imgGrid'),em=document.getElementById('imgEmpty');
  document.getElementById('imgCount').textContent=imgs.length;
  if(!imgs.length){g.innerHTML='';em.style.display='';return}
  em.style.display='none';document.getElementById('imgStatus').style.display='none';
  g.innerHTML=imgs.map(img=>'<div class="img-card" data-url="'+esc(img.url)+'" data-alt="'+esc(img.alt||'')+'"><img src="'+esc(img.url)+'" alt="'+esc(img.alt)+'" loading="lazy" onerror="this.parentElement.style.display=\'none\'"><div class="img-card-info">'+esc(img.alt||img.domain||'Image')+'</div></div>').join('');
  g.querySelectorAll('.img-card').forEach(c=>c.addEventListener('click',()=>openImgModal(c.dataset.url,c.dataset.alt)));
}

async function searchImages(){const q=document.getElementById('imgQuery').value.trim();if(!q)return;imgStatus(currentLang==='id'?'Mencari...':'Searching...');try{const r=await fetch('/api/images/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:q})}),j=await r.json();renderImgs(j.ok?j.images:[])}catch(e){imgStatus('Error')}}
async function scrapeUrl(){const u=document.getElementById('imgUrl').value.trim();if(!u)return;imgStatus('Scraping...');try{const r=await fetch('/api/images/scrape-url',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:u})}),j=await r.json();renderImgs(j.ok?j.images:[])}catch(e){imgStatus('Error')}}

async function uploadImg(inp){
  const f=inp.files[0];if(!f)return;
  document.getElementById('uploadPreview').style.display='';
  document.getElementById('upImg').src=URL.createObjectURL(f);
  document.getElementById('upName').textContent=f.name;
  imgStatus(currentLang==='id'?'Mengupload...':'Uploading...');
  const fd=new FormData();fd.append('file',f);
  try{const r=await fetch('/api/images/upload',{method:'POST',body:fd}),j=await r.json();renderImgs(j.ok?j.related_images:[])}catch(e){imgStatus('Error')}
}

function openImgModal(url,alt){
  selImgUrl=url;
  document.getElementById('imgModalImg').src=url;
  document.getElementById('imgModalTitle').textContent=alt||'Image';
  document.getElementById('imgModalLink').href=url;
  openModal('imgModal');
}

async function findRelated(){
  if(!selImgUrl)return;closeModal('imgModal');
  imgStatus(currentLang==='id'?'Mencari mirip...':'Finding similar...');
  try{const r=await fetch('/api/images/related',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image_url:selImgUrl})}),j=await r.json();renderImgs(j.ok?j.images:[])}catch(e){imgStatus('Error')}
}

const uz=document.getElementById('uploadZone');
uz.addEventListener('dragover',e=>{e.preventDefault();uz.classList.add('drag-over')});
uz.addEventListener('dragleave',()=>uz.classList.remove('drag-over'));
uz.addEventListener('drop',e=>{
  e.preventDefault();uz.classList.remove('drag-over');
  if(e.dataTransfer.files.length){const dt=new DataTransfer();dt.items.add(e.dataTransfer.files[0]);document.getElementById('fileInput').files=dt.files;uploadImg(document.getElementById('fileInput'))}
});

// ── Citation ────────────────────────────────────────────────
function toggleCiteFormat(){
  citeFormat=citeFormat==='apa7'?'mendikbud':'apa7';
  const btn=document.getElementById('citeFmtBtn');
  if(btn)btn.textContent=citeFormat==='apa7'?'APA 7':'Mendikbud';
}

function _parseCiteDate(d){
  d=(d||'').trim();
  const year=d.length>=4&&/^\d{4}/.test(d)?d.slice(0,4):'';
  let full=d;
  if(d.length>=10){
    try{
      const dt=new Date(d);
      if(!isNaN(dt.getTime())){
        const mAbbr=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
        const mAbbrID=['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Agt','Sep','Okt','Nov','Des'];
        const mID=['Januari','Februari','Maret','April','Mei','Juni','Juli','Agustus','September','Oktober','November','Desember'];
        const mEN=['January','February','March','April','May','June','July','August','September','October','November','December'];
        if(citeFormat==='apa7'){
          full=currentLang==='id'
            ?(year+', '+mAbbrID[dt.getMonth()]+' '+dt.getDate())
            :(year+', '+mAbbr[dt.getMonth()]+' '+dt.getDate());
        }else{
          full=currentLang==='id'
            ?(dt.getDate()+' '+mID[dt.getMonth()]+' '+year)
            :(dt.getDate()+' '+mEN[dt.getMonth()]+' '+year);
        }
      }
    }catch(e){}
  }
  return{year,full};
}

function formatCite(r){
  const{year,full}=_parseCiteDate(r.date);
  const title=r.title||'';
  const platform=r.platform||'';
  const url=r.url||'';
  const dateStr=full||year||'n.d.';
  if(citeFormat==='apa7'){
    return title+'. ('+dateStr+'). '+platform+'. '+url;
  }else{
    const acc=currentLang==='id'?'Diakses '+dateStr+', ':'Retrieved '+dateStr+', from ';
    return '"'+title+'." '+platform+'. '+acc+url;
  }
}

function copyCiteRow(i){
  const r=_viewData[i];if(!r)return;
  navigator.clipboard.writeText(formatCite(r)).then(
    ()=>toast(tr('cite_copied'),'ok',2500),
    ()=>toast(currentLang==='id'?'Gagal menyalin':'Copy failed','err')
  );
}

// ── Saved Searches ──────────────────────────────────────────
const SS_KEY = 'alyx_saved_searches';
const SS_MAX = 10;

function getSavedSearches(){
  try{ return JSON.parse(localStorage.getItem(SS_KEY)||'[]'); }catch(e){ return []; }
}

function renderSavedSearches(){
  const list = getSavedSearches();
  const el = document.getElementById('savedSearchList');
  if(!el) return;
  if(!list.length){
    el.innerHTML = '<div class="ss-empty">'+esc(tr('no_saved'))+'</div>';
    return;
  }
  el.innerHTML = list.map((s,i)=>
    '<div class="ss-item">'+
      '<div class="ss-name" title="'+esc(s.keyword)+(s.location?' | '+esc(s.location):'')+'">'+
        '<span class="ss-title">'+esc(s.name)+'</span>'+
        '<span class="ss-meta">'+esc(s.keyword)+(s.location?' · '+esc(s.location):'')+'</span>'+
      '</div>'+
      '<div class="ss-actions">'+
        '<button class="btn-g" style="padding:5px 10px;font-size:.8rem" onclick="loadSearch('+i+')">'+esc(tr('load_btn'))+'</button>'+
        '<button class="btn-g" style="padding:5px 8px;color:#ef4444" onclick="deleteSearch('+i+')" title="Hapus"><i class="bi bi-trash3"></i></button>'+
      '</div>'+
    '</div>'
  ).join('');
}

function openSaveModal(){
  const kw = document.getElementById('keywords').value.trim();
  if(!kw){ toast(currentLang==='id'?'Isi keyword dulu!':'Enter keywords first!','err'); return; }
  document.getElementById('saveSearchName').value = '';
  openModal('saveSearchModal');
  setTimeout(()=>document.getElementById('saveSearchName').focus(), 100);
}

function confirmSaveSearch(){
  const name = document.getElementById('saveSearchName').value.trim();
  if(!name){ toast(currentLang==='id'?'Isi nama preset!':'Enter a preset name!','err'); return; }
  const kw = document.getElementById('keywords').value.trim();
  const loc = document.getElementById('location').value.trim();
  const platforms = Array.from(document.querySelectorAll('.pcb:checked')).map(e=>e.value);
  const list = getSavedSearches();
  const existing = list.findIndex(s=>s.name===name);
  const preset = {name, keyword:kw, location:loc, platforms};
  if(existing>=0) list[existing]=preset;
  else list.unshift(preset);
  if(list.length>SS_MAX) list.length=SS_MAX;
  try{ localStorage.setItem(SS_KEY, JSON.stringify(list)); }catch(e){}
  closeModal('saveSearchModal');
  renderSavedSearches();
  const panel = document.getElementById('savedSearchPanel');
  if(panel) panel.style.display='';
  toast(currentLang==='id'?'Preset "'+name+'" disimpan!':'Preset "'+name+'" saved!','ok');
}

function loadSearch(i){
  const list = getSavedSearches();
  const s = list[i]; if(!s) return;
  document.getElementById('keywords').value = s.keyword;
  document.getElementById('location').value = s.location||'';
  updateKeywordsStat();
  document.querySelectorAll('.pcb').forEach(cb=>{
    const chip = cb.closest('.chip');
    const active = s.platforms.includes(cb.value) && chip && chip.style.display!=='none';
    cb.checked = active;
    if(chip) chip.classList.toggle('active', active);
  });
  updatePlatformsStat();
  document.getElementById('savedSearchPanel').style.display='none';
  toast(currentLang==='id'?'Preset "'+s.name+'" dimuat!':'Preset "'+s.name+'" loaded!','ok');
}

function deleteSearch(i){
  const list = getSavedSearches();
  const name = list[i]&&list[i].name;
  list.splice(i,1);
  try{ localStorage.setItem(SS_KEY, JSON.stringify(list)); }catch(e){}
  renderSavedSearches();
  if(!list.length) document.getElementById('savedSearchPanel').style.display='none';
  toast(currentLang==='id'?'"'+name+'" dihapus.':'"'+name+'" deleted.');
}

// show saved searches panel on load if presets exist
(function(){
  const list = getSavedSearches();
  if(list.length){
    const panel = document.getElementById('savedSearchPanel');
    if(panel) panel.style.display='';
    renderSavedSearches();
  }
})();

updatePlatformsStat();

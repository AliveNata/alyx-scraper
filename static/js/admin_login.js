window.PAGE_L = {
  id:{
    login_sub:'Admin Dashboard - masukkan password untuk lanjut',
    login_pw_label:'Password', login_pw_ph:'Masukkan password',
    login_btn:'Masuk', login_back:'Kembali ke AlyxLabs',
    login_forgot:'Lupa Password?',
    fp_title:'Email Terkirim!',
  },
  en:{
    login_sub:'Admin Dashboard - enter password to continue',
    login_pw_label:'Password', login_pw_ph:'Enter password',
    login_btn:'Sign In', login_back:'Back to AlyxLabs',
    login_forgot:'Forgot Password?',
    fp_title:'Email Sent!',
  }
};

async function sendForgotPassword(){
  const toast  = document.getElementById('fpToast');
  const msgEl  = document.getElementById('fpMsg');
  const lang   = typeof currentLang !== 'undefined' ? currentLang : 'id';
  const titleEl = toast.querySelector('[data-i18n="fp_title"]');

  if(titleEl) titleEl.textContent = lang === 'id' ? 'Mengirim...' : 'Sending...';
  msgEl.textContent = lang === 'id' ? 'Mohon tunggu sebentar...' : 'Please wait...';
  toast.style.display = '';

  try {
    const r = await fetch('/api/forgot-password', { method: 'POST' });
    const j = await r.json();
    if(j.ok){
      if(titleEl) titleEl.textContent = lang === 'id' ? 'Email Terkirim!' : 'Email Sent!';
      msgEl.textContent = lang === 'id'
        ? `Link reset password telah dikirim ke ${j.recipient}`
        : `Password reset link has been sent to ${j.recipient}`;
      toast.style.borderColor = 'rgba(34,197,94,.4)';
    } else {
      if(titleEl) titleEl.textContent = lang === 'id' ? 'Gagal Mengirim' : 'Failed to Send';
      const notConfigured = j.error && j.error.includes('belum dikonfigurasi');
      msgEl.innerHTML = notConfigured
        ? (lang === 'id'
            ? 'Email belum dikonfigurasi. <a href="/admin/dashboard" style="color:#6366f1">Buka Admin > Settings > Email Config</a>'
            : 'Email not configured. <a href="/admin/dashboard" style="color:#6366f1">Open Admin > Settings > Email Config</a>')
        : (j.error || 'Terjadi kesalahan');
      toast.style.borderColor = 'rgba(239,68,68,.4)';
    }
  } catch(e) {
    if(titleEl) titleEl.textContent = 'Error';
    msgEl.textContent = 'Network error - pastikan server berjalan.';
    toast.style.borderColor = 'rgba(239,68,68,.4)';
  }

  // Auto-hide after 8 seconds
  setTimeout(() => {
    toast.style.display = 'none';
    toast.style.borderColor = '';
    if(titleEl) titleEl.textContent = lang === 'id' ? 'Email Terkirim!' : 'Email Sent!';
  }, 8000);
}

function togglePw(){
  const inp=document.getElementById('password'),icon=document.getElementById('eyeIcon');
  if(inp.type==='password'){inp.type='text';icon.className='bi bi-eye-slash'}
  else{inp.type='password';icon.className='bi bi-eye'}
}

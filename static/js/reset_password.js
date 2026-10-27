window.PAGE_L = { id:{}, en:{} };

function togglePw(inputId, iconId){
  const inp = document.getElementById(inputId);
  const icon = document.getElementById(iconId);
  if(inp.type === 'password'){ inp.type = 'text'; icon.className = 'bi bi-eye-slash'; }
  else { inp.type = 'password'; icon.className = 'bi bi-eye'; }
}

function checkStrength(pw){
  const bar = document.getElementById('pwStrength');
  const lbl = document.getElementById('pwStrengthLabel');
  if(!bar) return;
  if(!pw){ bar.className = 'pw-strength'; lbl.textContent = ''; return; }
  let score = 0;
  if(pw.length >= 6) score++;
  if(pw.length >= 10) score++;
  if(/[A-Z]/.test(pw) && /[0-9]/.test(pw)) score++;
  if(/[^A-Za-z0-9]/.test(pw)) score++;
  const levels = [
    ['pw-s1','Lemah'],['pw-s2','Cukup'],['pw-s3','Kuat'],['pw-s4','Sangat Kuat']
  ];
  const [cls, label] = levels[Math.min(score, 3)];
  bar.className = 'pw-strength ' + cls;
  lbl.textContent = label;
}

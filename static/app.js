let mode='AUTO';
let busy=false;
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmtNum=n=>n==null?'—':new Intl.NumberFormat('en-GB',{maximumFractionDigits:0}).format(n);
const fmtPct=n=>n==null?'—':`${n>=0?'+':''}${Number(n).toFixed(2)}%`;

function clocks(){
 const now=new Date();
 $('ukClock').textContent=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/London',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(now);
 $('nyClock').textContent=new Intl.DateTimeFormat('en-GB',{timeZone:'America/New_York',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(now);
 $('ukDate').textContent=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/London',weekday:'short',day:'2-digit',month:'short'}).format(now);
 $('nyDate').textContent=new Intl.DateTimeFormat('en-GB',{timeZone:'America/New_York',weekday:'short',day:'2-digit',month:'short'}).format(now);
}

function render(data){
 $('session').textContent=data.session||'—';
 $('source').textContent=data.source||'';
 $('note').textContent=data.note||'';
 $('note').classList.toggle('hidden',!data.note);
 const body=$('rows'); body.innerHTML='';
 const rows=Array.isArray(data.rows)?data.rows:[];
 $('empty').classList.toggle('hidden',rows.length>0);
 rows.forEach((r,i)=>{
  const tr=document.createElement('tr');
  if(i<3) tr.className='hot';
  const candle=(r.candle||'').toUpperCase();
  tr.innerHTML=`
   <td>${i+1}</td>
   <td class="ticker">${esc(r.ticker)}</td>
   <td class="${candle==='GREEN'?'green':candle==='RED'?'red':''}">${esc(candle||'—')}</td>
   <td class="momentum ${r.move15>=0?'green':'red'}">${fmtPct(r.move15)}</td>
   <td>${fmtNum(r.vol15)}</td>
   <td>${fmtNum(r.prev_vol15)}</td>
   <td class="${r.vol_change>=0?'green':'red'}">${fmtPct(r.vol_change)}</td>
   <td class="${r.high_change>=0?'green':'red'}">${fmtPct(r.high_change)}</td>
   <td class="blue">${esc(r.bar_start||'—')}</td>`;
  body.appendChild(tr);
 });
}

async function load(){
 if(busy)return; busy=true;
 try{
  $('refreshStatus').textContent='Refreshing…';
  const r=await fetch(`/api/scan?mode=${encodeURIComponent(mode)}&t=${Date.now()}`,{cache:'no-store',signal:AbortSignal.timeout(20000)});
  const data=await r.json();
  render(data);
  $('refreshStatus').textContent=r.ok?'Updated '+new Date().toLocaleTimeString('en-GB')+' · 20s':'Feed unavailable';
 }catch(e){
  render({session:mode,source:'Unavailable',rows:[],note:'Cannot reach scanner feed.'});
  $('refreshStatus').textContent='Connection error';
 }finally{busy=false;}
}

document.querySelectorAll('.tab').forEach(b=>b.addEventListener('click',()=>{
 document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
 b.classList.add('active'); mode=b.dataset.mode; load();
}));

clocks(); setInterval(clocks,1000); load(); setInterval(load,20000);

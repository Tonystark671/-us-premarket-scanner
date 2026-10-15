let mode='AUTO';
let busy=false, generation=0;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const $=id=>document.getElementById(id);
const fmtNum=n=>n==null?'—':new Intl.NumberFormat('en-GB',{maximumFractionDigits:0}).format(n);
const fmtPrice=n=>n==null?'—':'$'+Number(n).toFixed(n<10?2:2);
const fmtPct=n=>n==null?'—':`${n>=0?'+':''}${Number(n).toFixed(2)}%`;

function parts(date,tz){return Object.fromEntries(new Intl.DateTimeFormat('en-GB',{timeZone:tz,weekday:'short',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).formatToParts(date).filter(x=>x.type!=='literal').map(x=>[x.type,x.value]));}
function offsetMin(date,tz){const p=parts(date,tz);return (Date.UTC(+p.year,+p.month-1,+p.day,+p.hour,+p.minute,+p.second)-date.getTime())/60000;}
function nyToLondon(date,h,m){const p=parts(date,'America/New_York');let guess=Date.UTC(+p.year,+p.month-1,+p.day,h,m,0);for(let i=0;i<3;i++){guess=Date.UTC(+p.year,+p.month-1,+p.day,h,m,0)-offsetMin(new Date(guess),'America/New_York')*60000}return new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/London',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(guess));}
function detectSession(){const now=new Date(),p=parts(now,'America/New_York'),m=+p.hour*60+(+p.minute),day=new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',weekday:'short'}).format(now);if(['Sat','Sun'].includes(day))return'CLOSED';if(m>=1200||m<240)return'OVERNIGHT';if(m<570)return'PRE-MARKET';if(m<960)return'MARKET';if(m<1200)return'AFTER-HOURS';return'CLOSED';}
function clocks(){const now=new Date();$('ukClock').textContent=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/London',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(now);$('nyClock').textContent=new Intl.DateTimeFormat('en-GB',{timeZone:'America/New_York',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(now);$('ukDate').textContent=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/London',weekday:'long',day:'2-digit',month:'short',year:'numeric'}).format(now);$('nyDate').textContent=new Intl.DateTimeFormat('en-GB',{timeZone:'America/New_York',weekday:'long',day:'2-digit',month:'short',year:'numeric'}).format(now);const current=detectSession();const segs=[['OVERNIGHT',`${nyToLondon(now,20,0)}–${nyToLondon(now,4,0)}`,'purple'],['PRE-MARKET',`${nyToLondon(now,4,0)}–${nyToLondon(now,9,30)}`,'amber'],['MARKET',`${nyToLondon(now,9,30)}–${nyToLondon(now,16,0)}`,'green'],['AFTER-HOURS',`${nyToLondon(now,16,0)}–${nyToLondon(now,20,0)}`,'blue']];$('timeline').innerHTML=segs.map(([s,t,c])=>`<div class="segment ${s===current?'active':''}"><b class="${c}">${s}</b><span>${t} UK</span></div>`).join('');}
function render(data){$('session').textContent=data.session;$('session').className='session '+(data.session==='AFTER-HOURS'?'blue':data.session==='PRE-MARKET'?'amber':data.session==='OVERNIGHT'?'purple':data.session==='MARKET'?'green':'red');$('source').textContent=`Source: ${data.source}${data.demo?' • demo fallback':''}`;$('note').textContent=data.note||'';$('note').classList.toggle('hidden',!data.note);const body=$('rows');body.innerHTML='';$('empty').classList.toggle('hidden',data.rows.length>0);data.rows.forEach((r,i)=>{const tr=document.createElement('tr');if(i<3)tr.className='hot';tr.innerHTML=`<td>${i+1}</td><td class="ticker">${esc(r.ticker)}</td><td>${esc(r.company)}</td><td>${fmtPrice(r.price)}</td><td class="momentum ${r.move15>=0?'green':'red'}">${fmtPct(r.move15)}</td><td class="${r.total_move>=0?'green':'red'}">${fmtPct(r.total_move)}</td><td>${fmtNum(r.vol15)}</td><td>${fmtNum(r.total_volume)}</td><td>${r.rel_vol==null?'—':Number(r.rel_vol).toFixed(2)+'×'}</td><td>${fmtPrice(r.ema20)}</td><td>${fmtPrice(r.ema50)}</td><td>${fmtPrice(r.upper_bb)}</td><td>${(r.signals||[]).map(s=>`<span class="tag">${esc(s)}</span>`).join('')}</td><td class="blue">${r.signal_time||'—'}</td><td class="news"><button class="news-button" data-ticker="${esc(r.ticker)}">Headline</button></td>`;body.appendChild(tr);});}
async function load(){
 if(busy)return; busy=true; const ticket=generation;
 try{
  $('refreshStatus').textContent='Refreshing…';
  const r=await fetch(`/api/scan?mode=${encodeURIComponent(mode)}`,{cache:'no-store',signal:AbortSignal.timeout(20000)});
  const data=await r.json(); if(ticket!==generation)return;
  if(!Array.isArray(data.rows))throw new Error('Invalid response');
  render(data); $('refreshStatus').textContent=r.ok?'Checked '+new Date().toLocaleTimeString('en-GB')+' · 30s':'Feed unavailable';
 }catch(e){if(ticket!==generation)return;render({session:mode,source:'Unavailable',rows:[],note:'Cannot reach the scanner. Previous results cleared.'});$('refreshStatus').textContent='Connection error';}
 finally{busy=false;if(ticket!==generation)load();}
}
$('rows').addEventListener('click',async e=>{const b=e.target.closest('.news-button');if(!b)return;b.disabled=true;try{const r=await fetch('/api/news/'+encodeURIComponent(b.dataset.ticker));const d=await r.json();b.parentElement.textContent=d.headline||'No headline available';}catch{b.disabled=false;b.textContent='Retry headline';}});
document.querySelectorAll('.tab').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));b.classList.add('active');mode=b.dataset.mode;generation++;$('rows').innerHTML='';load();}));
clocks();setInterval(clocks,1000);load();setInterval(load,30000);

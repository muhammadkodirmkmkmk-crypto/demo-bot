"""
CRM veb-interfeysi: /crm (kompyuter va telefon). Kirish — botdagi /crm buyrug'i bergan bir martalik havola orqali.
Ma'lumot va amallar — admin.py API (/admin/api/...) orqali, sessiya cookie bilan.
"""
import urllib.parse

core = None


def init(bot_module):
    global core
    core = bot_module


def handle_get(h):
    u = urllib.parse.urlparse(h.path)
    path = u.path.rstrip("/")
    q = urllib.parse.parse_qs(u.query)
    if path == "/crm/login":
        sid = core.BILL.login((q.get("t") or [""])[0])
        if not sid:
            core.IG.respond_html(h, 200, LOGIN_PAGE.replace("{{MSG}}", "Ссылка устарела или уже использована. "
                                                            "Напишите боту команду /crm — он пришлёт новую."))
            return True
        core.IG.respond_html(h, 302, "", headers={
            "Location": "/crm", "Cache-Control": "no-store",
            "Set-Cookie": f"crm_s={sid}; Path=/; Max-Age={core.BILL.SESSION_DAYS * 86400}; HttpOnly; Secure; SameSite=Lax"})
        return True
    if path == "/crm/logout":
        core.BILL.logout(core.BILL.cookie_sid(h))
        core.IG.respond_html(h, 302, "", headers={"Location": "/crm", "Set-Cookie": "crm_s=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax"})
        return True
    if path == "/crm":
        if not core.BILL.session_ok(h):
            core.IG.respond_html(h, 200, LOGIN_PAGE.replace("{{MSG}}", "Чтобы войти, напишите боту команду /crm и нажмите «Открыть CRM»."),
                                 headers={"Cache-Control": "no-store"})
            return True
        core.IG.respond_html(h, 200, PAGE, headers={"Cache-Control": "no-store"})
        return True
    core.IG.respond_html(h, 404, "not found", ctype="text/plain")
    return True


LOGIN_PAGE = r"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Business CRM — вход</title><style>
body{margin:0;min-height:100vh;display:grid;place-items:center;font:16px/1.5 -apple-system,system-ui,Segoe UI,Roboto,sans-serif;background:#f4f6fb;color:#111827}
.box{background:#fff;border-radius:18px;padding:32px 28px;max-width:380px;margin:16px;box-shadow:0 10px 30px rgba(17,24,39,.08);text-align:center}
.logo{width:56px;height:56px;border-radius:16px;background:#2563eb;color:#fff;display:grid;place-items:center;font-weight:800;font-size:22px;margin:0 auto 14px}
h1{font-size:20px;margin:0 0 8px}p{color:#6b7280;margin:0}code{background:#eef2ff;color:#2563eb;padding:2px 6px;border-radius:6px}
@media(prefers-color-scheme:dark){body{background:#0b1020;color:#e5e7eb}.box{background:#151b2e;box-shadow:none}p{color:#9ca3af}code{background:#1e2a4a}}
</style></head><body><div class="box"><div class="logo">AI</div><h1>AI Business CRM</h1><p>{{MSG}}</p>
<p style="margin-top:14px">Бот: <code>@aibusinessuzbot</code> → <code>/crm</code></p></div></body></html>"""


PAGE = r"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>AI Business CRM</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{--bg:#f4f6fb;--card:#fff;--line:#e8ebf2;--tx:#111827;--mut:#6b7280;--soft:#f1f4f9;--ac:#2563eb;--ac2:#eef3ff;
--ok:#16a34a;--okbg:#e8f7ee;--warn:#d97706;--warnbg:#fdf3e2;--bad:#dc2626;--badbg:#fdecec;--tg:#229ed9;--ig:#d6337a;--man:#8b93a1;
--sh:0 1px 2px rgba(17,24,39,.04),0 4px 14px rgba(17,24,39,.05);--r:14px}
@media(prefers-color-scheme:dark){:root{--bg:#0b1020;--card:#141a2c;--line:#232b42;--tx:#e8ebf3;--mut:#94a0b8;--soft:#1b2337;--ac:#5b8cff;--ac2:#1c2850;
--okbg:#12301f;--warnbg:#33260f;--badbg:#3a1717;--sh:none}}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--tx);font:14px/1.45 Inter,-apple-system,system-ui,Segoe UI,Roboto,sans-serif}
button,input,select,textarea{font:inherit;color:inherit}a{color:var(--ac)}
.app{display:grid;grid-template-columns:232px 1fr;min-height:100vh}
.side{background:var(--card);border-right:1px solid var(--line);padding:18px 12px;position:sticky;top:0;height:100vh;display:flex;flex-direction:column;gap:2px}
.brand{display:flex;align-items:center;gap:10px;padding:4px 10px 18px}.brand .lg{width:34px;height:34px;border-radius:10px;background:var(--ac);color:#fff;display:grid;place-items:center;font-weight:800}
.brand b{font-size:15px}.brand span{display:block;font-size:12px;color:var(--mut)}
.nav{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:10px;cursor:pointer;color:var(--mut);font-weight:500;border:0;background:none;text-align:left;width:100%}
.nav:hover{background:var(--soft);color:var(--tx)}.nav.on{background:var(--ac2);color:var(--ac);font-weight:600}
.nav .ic{width:20px;text-align:center}.nav .cnt{margin-left:auto;background:var(--bad);color:#fff;border-radius:10px;font-size:11px;padding:0 7px;line-height:18px}
.side .foot{margin-top:auto;padding:10px 12px;font-size:12px;color:var(--mut)}
.main{min-width:0}
.top{position:sticky;top:0;z-index:5;background:color-mix(in srgb,var(--bg) 88%,transparent);backdrop-filter:blur(8px);display:flex;align-items:center;gap:10px;padding:14px 24px;border-bottom:1px solid var(--line)}
.top h1{font-size:20px;margin:0;font-weight:700}.top .sp{flex:1}
.burger{display:none;border:0;background:var(--card);border-radius:10px;width:38px;height:38px;font-size:18px}
.seg{display:flex;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:3px}
.seg button{border:0;background:none;padding:6px 10px;border-radius:7px;color:var(--mut);cursor:pointer;white-space:nowrap}.seg button.on{background:var(--ac);color:#fff}
.btn{border:1px solid var(--line);background:var(--card);border-radius:10px;padding:8px 14px;cursor:pointer;font-weight:500;white-space:nowrap;display:inline-flex;align-items:center;gap:6px;text-decoration:none;color:var(--tx)}
.btn:hover{border-color:var(--ac)}.btn.pri{background:var(--ac);border-color:var(--ac);color:#fff}.btn.ok{background:var(--ok);border-color:var(--ok);color:#fff}
.btn.sm{padding:5px 10px;font-size:13px;border-radius:8px}.btn.ghost{border-color:transparent;background:var(--soft)}.btn.danger{color:var(--bad)}
.wrap{padding:20px 24px 60px;max-width:1400px}
.grid{display:grid;gap:14px}.g6{grid-template-columns:repeat(6,1fr)}.g4{grid-template-columns:repeat(4,1fr)}.g3{grid-template-columns:repeat(3,1fr)}.g2{grid-template-columns:repeat(2,1fr)}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:16px 18px;box-shadow:var(--sh);min-width:0}
.card h3{margin:0 0 12px;font-size:15px;font-weight:600;display:flex;align-items:center;gap:8px}.card h3 .sp{flex:1}
.kpi .v{font-size:24px;font-weight:700;font-variant-numeric:tabular-nums;letter-spacing:-.3px}.kpi .l{color:var(--mut);font-size:13px;margin-top:2px}.kpi .s{font-size:12px;margin-top:6px;color:var(--mut)}
.mut{color:var(--mut)}.sm{font-size:12px}.ok{color:var(--ok)}.bad{color:var(--bad)}.warn{color:var(--warn)}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}th{color:var(--mut);font-weight:500;font-size:12px;text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:10px;border-bottom:1px solid var(--line);vertical-align:middle}tr:last-child td{border-bottom:0}.num{text-align:right}tr.click{cursor:pointer}tr.click:hover td{background:var(--soft)}
.pill{display:inline-flex;align-items:center;gap:5px;border-radius:999px;padding:2px 9px;font-size:12px;font-weight:600;white-space:nowrap;background:var(--soft);color:var(--mut)}
.p-ok{background:var(--okbg);color:var(--ok)}.p-warn{background:var(--warnbg);color:var(--warn)}.p-bad{background:var(--badbg);color:var(--bad)}.p-ac{background:var(--ac2);color:var(--ac)}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;vertical-align:middle}
.empty{padding:28px;text-align:center;color:var(--mut)}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.row.sb{justify-content:space-between}
.inp,select.inp,textarea.inp{border:1px solid var(--line);background:var(--card);border-radius:10px;padding:8px 11px;width:100%;outline:none}.inp:focus{border-color:var(--ac)}
label.f{display:block;font-size:12px;color:var(--mut);margin:10px 0 4px}
.fbar{height:10px;border-radius:6px;background:var(--soft);overflow:hidden}.fbar i{display:block;height:100%;background:var(--ac);border-radius:6px}
.fn{display:grid;grid-template-columns:170px 1fr 90px;gap:10px;align-items:center;margin:8px 0}
.kan{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(250px,1fr);gap:12px;overflow-x:auto;padding-bottom:10px;align-items:start}
.col{background:var(--soft);border-radius:var(--r);padding:10px;min-height:120px}.col.drop{outline:2px dashed var(--ac)}
.col .hd{display:flex;justify-content:space-between;align-items:center;padding:2px 4px 10px;font-weight:600}.col .hd span{color:var(--mut);font-weight:500;font-size:12px}
.dc{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 12px;margin-bottom:8px;cursor:grab;box-shadow:var(--sh)}
.dc:active{cursor:grabbing}.dc b{display:block;margin-bottom:2px}.dc .sm{color:var(--mut)}
.prog{height:5px;border-radius:4px;background:var(--line);margin-top:8px;overflow:hidden}.prog i{display:block;height:100%;background:var(--ok)}
.task{display:flex;gap:12px;align-items:center;padding:12px 4px;border-bottom:1px solid var(--line)}.task:last-child{border-bottom:0}
.task .who{flex:1;min-width:0}.task .who b{cursor:pointer}.task .acts{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}
.av{width:36px;height:36px;border-radius:50%;display:grid;place-items:center;font-weight:700;color:#fff;flex:none;font-size:14px}
.chart{display:flex;gap:14px;align-items:flex-end;height:170px;padding-top:10px}.chart .c{flex:1;display:flex;flex-direction:column;align-items:center;gap:6px}
.chart .bars{display:flex;gap:4px;align-items:flex-end;height:140px}.chart .bars i{width:16px;border-radius:5px 5px 0 0;display:block}
.drawer{position:fixed;inset:0;z-index:30;display:none}.drawer.on{display:block}.drawer .bg{position:absolute;inset:0;background:rgba(10,15,30,.38)}
.drawer .pn{position:absolute;right:0;top:0;bottom:0;width:min(620px,100%);background:var(--bg);overflow:auto;box-shadow:-10px 0 30px rgba(0,0,0,.15)}
.pn .ph{background:var(--card);padding:18px 22px;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:2}
.pn .pb{padding:18px 22px 60px}
.tabs{display:flex;gap:4px;margin-top:14px}.tabs button{border:0;background:none;padding:8px 12px;border-radius:9px;cursor:pointer;color:var(--mut);font-weight:500}.tabs button.on{background:var(--ac2);color:var(--ac)}
.msg{max-width:85%;padding:8px 11px;border-radius:12px;background:var(--card);border:1px solid var(--line);margin:6px 0;white-space:pre-wrap;word-wrap:break-word}
.msg.a{margin-left:auto;background:var(--ac2);border-color:transparent}.msg .t{font-size:11px;color:var(--mut);margin-bottom:2px}
.modal{position:fixed;inset:0;z-index:40;display:none;place-items:center;background:rgba(10,15,30,.42);padding:16px}.modal.on{display:grid}
.modal .mb{background:var(--card);border-radius:18px;padding:22px;width:min(480px,100%);max-height:92vh;overflow:auto}
.modal h2{margin:0 0 6px;font-size:18px}
.toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);background:#111827;color:#fff;padding:10px 16px;border-radius:12px;z-index:50;display:none}
.menu{position:relative}.menu .dd{position:absolute;right:0;top:44px;background:var(--card);border:1px solid var(--line);border-radius:12px;box-shadow:0 10px 30px rgba(0,0,0,.12);padding:6px;min-width:200px;display:none;z-index:10}
.menu.on .dd{display:block}.dd button{display:block;width:100%;text-align:left;border:0;background:none;padding:9px 12px;border-radius:8px;cursor:pointer}.dd button:hover{background:var(--soft)}
.note{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 12px;margin:8px 0}
.two{display:grid;grid-template-columns:1fr 1fr;gap:0 12px}
.botbar{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:10px 12px;border-radius:12px;background:var(--okbg);margin-top:12px}.botbar.off{background:var(--badbg)}
@media(max-width:1100px){.g6{grid-template-columns:repeat(3,1fr)}.g4{grid-template-columns:repeat(2,1fr)}.g3{grid-template-columns:1fr 1fr}}
@media(max-width:860px){.app{grid-template-columns:1fr}.side{position:fixed;left:0;top:0;z-index:35;width:260px;transform:translateX(-100%);transition:.2s;box-shadow:10px 0 30px rgba(0,0,0,.15)}
 .side.on{transform:none}.burger{display:block}.top{padding:10px 14px;flex-wrap:wrap}.top h1{font-size:17px}.wrap{padding:14px 12px 60px}
 .g6,.g4{grid-template-columns:1fr 1fr}.g3,.g2{grid-template-columns:1fr}.two{grid-template-columns:1fr}.fn{grid-template-columns:110px 1fr 70px}
 .hide-m{display:none}.seg{order:5;width:100%;overflow-x:auto}.task{flex-wrap:wrap}.task .acts{width:100%;justify-content:flex-start}}
</style></head><body>
<div class="app">
 <aside class="side" id="side">
  <div class="brand"><div class="lg">AI</div><div><b>AI Business</b><span>CRM</span></div></div>
  <div id="nav"></div>
  <div class="foot"><a href="/crm/logout" class="mut">Выйти</a></div>
 </aside>
 <div class="main">
  <div class="top">
   <button class="burger" onclick="$('#side').classList.toggle('on')">☰</button>
   <h1 id="title">Сводка</h1><div class="sp"></div>
   <div class="seg" id="per"></div>
   <button class="btn" onclick="load()" title="Обновить">↻</button>
   <div class="menu" id="addm"><button class="btn pri" onclick="$('#addm').classList.toggle('on')">＋ Добавить</button>
    <div class="dd"><button onclick="openNewClient()">👤 Клиента</button><button onclick="openPay()">💵 Платёж</button>
    <button onclick="openSub()">💳 Подписку</button><button onclick="openExp()">📉 Расход</button></div></div>
  </div>
  <div class="wrap" id="app"><div class="empty">Загрузка…</div></div>
 </div>
</div>
<div class="drawer" id="drawer"><div class="bg" onclick="closeDrawer()"></div><div class="pn" id="pn"></div></div>
<div class="modal" id="modal" onclick="if(event.target.id=='modal')closeModal()"><div class="mb" id="mb"></div></div>
<div class="toast" id="toast"></div>
<script>
const $=s=>document.querySelector(s);
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const money=(v,d=0)=>(v<0?"−":"")+"$"+Math.abs(Number(v||0)).toLocaleString("ru",{minimumFractionDigits:d,maximumFractionDigits:d});
const pct=(a,b)=>b?Math.round(100*a/b)+"%":"—";
const dt=ts=>ts?new Date(ts*1000).toLocaleDateString("ru",{day:"2-digit",month:"2-digit"}):"";
const dtt=ts=>ts?new Date(ts*1000).toLocaleString("ru",{day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"}):"";
const dday=s=>s?new Date(s+"T12:00").toLocaleDateString("ru",{day:"2-digit",month:"short"}):"";
const today=()=>{const d=new Date(),z=n=>String(n).padStart(2,"0");return d.getFullYear()+"-"+z(d.getMonth()+1)+"-"+z(d.getDate())};
const localDT=d=>{const z=n=>String(n).padStart(2,"0");return d.getFullYear()+"-"+z(d.getMonth()+1)+"-"+z(d.getDate())+"T"+z(d.getHours())+":"+z(d.getMinutes())};
const COL={tg:"var(--tg)",ig:"var(--ig)",manual:"var(--man)"};
const CHN={tg:"Telegram",ig:"Instagram",manual:"Вручную"};
const AVC=["#2563eb","#7c3aed","#db2777","#ea580c","#16a34a","#0891b2","#4f46e5"];
const av=n=>{n=n||"?";let h=0;for(const c of n)h=(h*31+c.charCodeAt(0))%997;return `<div class="av" style="background:${AVC[h%AVC.length]}">${esc(n.trim()[0]||"?").toUpperCase()}</div>`};
const PAGES=[["dash","🏠","Сводка"],["tasks","📞","Звонки и задачи"],["deals","🗂","Сделки"],["clients","👥","Клиенты"],["subs","💳","Подписки"],["pay","💵","Платежи"],["exp","📉","Расходы"],["bot","🤖","Бот"]];
const PER=[["today","Сегодня"],["7d","7 дней"],["month","Месяц"],["30d","30 дней"]];
let S={page:"dash",per:"month",d:null,q:"",stage:"",ch:"",showDialog:false,ctab:"profile",ckey:null};
try{Object.assign(S,JSON.parse(localStorage.getItem("crm")||"{}"),{d:null,ckey:null})}catch(e){}
function save(){try{localStorage.setItem("crm",JSON.stringify({page:S.page,per:S.per,showDialog:S.showDialog}))}catch(e){}}
function toast(t){const x=$("#toast");x.textContent=t;x.style.display="block";clearTimeout(x._t);x._t=setTimeout(()=>x.style.display="none",2200)}
async function api(path,body){
 const r=await fetch("/admin/api/"+path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body||{}),credentials:"same-origin"});
 if(r.status==403){location.reload();return null}
 if(!r.ok){toast("Не получилось сохранить");return null}return r.json();
}
async function load(){
 const r=await fetch("/admin/api?period="+S.per,{credentials:"same-origin"});
 if(r.status==403){location.reload();return}
 S.d=await r.json();render();
 if(S.ckey&&$("#drawer").classList.contains("on"))drawer(S.ckey);
}
function chrome(){
 const d=S.d,todo=d?d.calls.filter(x=>x.todo).length:0,od=d?d.subs_overdue:0;
 $("#nav").innerHTML=PAGES.map(([k,i,n])=>`<button class="nav ${S.page==k?"on":""}" onclick="go('${k}')"><span class="ic">${i}</span>${n}
  ${k=="tasks"&&todo?`<span class="cnt">${todo}</span>`:""}${k=="subs"&&od?`<span class="cnt">${od}</span>`:""}</button>`).join("");
 $("#per").innerHTML=PER.map(([k,n])=>`<button class="${S.per==k?"on":""}" onclick="S.per='${k}';save();load()">${n}</button>`).join("");
 $("#title").textContent=(PAGES.find(p=>p[0]==S.page)||PAGES[0])[2];
}
function go(p){S.page=p;save();$("#side").classList.remove("on");render();window.scrollTo(0,0)}
function render(){chrome();if(!S.d)return;const V={dash,tasks,deals,clients,subs,pay,exp,bot};$("#app").innerHTML=(V[S.page]||dash)(S.d);
 if(S.page=="deals")dnd();const q=$("#q");if(q&&S.qf){q.focus();q.setSelectionRange(q.value.length,q.value.length);S.qf=false}}
document.addEventListener("click",e=>{if(!e.target.closest("#addm"))$("#addm").classList.remove("on")});
const stName=s=>(S.d.pipe.find(p=>p[0]==s)||["",s])[1];
const stPill=s=>`<span class="pill ${s=="won"?"p-ok":s=="lost"?"":s=="new"?"p-bad":s=="dialog"?"":"p-ac"}">${stName(s)}</span>`;
const cl=k=>S.d.crm.find(x=>x.key==k)||{facts:{},notes:[],tail:[],deal:{},payments:[]};

/* ------------------------------ СВОДКА ------------------------------ */
function funnelRows(d){
 const [st,en]=[d.period?periodStart(d):0,1e12];
 const L=d.crm.filter(x=>x.first>=st&&x.ch!="manual");
 const talked=x=>x.called||["offer","pay","won"].includes(x.stage)||x.notes.length>0;
 const steps=[["Написали боту",L.length],["Стали лидами (контакт)",L.filter(x=>x.stage!="dialog").length],["Я поговорил",L.filter(talked).length],
  ["Предложение",L.filter(x=>["offer","pay","won"].includes(x.stage)).length],["Ждут оплаты",L.filter(x=>["pay","won"].includes(x.stage)).length],["Купили",L.filter(x=>x.stage=="won").length]];
 const top=Math.max(1,steps[0][1]);
 return steps.map(([n,v],i)=>`<div class="fn"><div>${n}</div><div class="fbar"><i style="width:${100*v/top}%;background:${i==5?"var(--ok)":"var(--ac)"}"></i></div>
  <div class="num"><b>${v}</b> <span class="mut sm">${i?pct(v,steps[i-1][1]):""}</span></div></div>`).join("");
}
function periodStart(d){return new Date(d.days[0]+"T00:00").getTime()/1000}
function dash(d){
 const cashProfit=d.received-d.spend, a=d.agent, subsSpend=(d.by_cat.ai||0)+(d.by_cat.server||0)+(d.by_cat.voice||0);
 const fullLead=a.leads?(a.cost+subsSpend)/a.leads:0, adsSpend=(d.by_cat.ads_ig||0)+(d.by_cat.ads_tg||0)+(d.by_cat.ads_other||0);
 const todo=d.calls.filter(x=>x.todo), due=d.calls.filter(x=>x.remind_due), od=d.subs.filter(s=>s.state=="overdue"), soon=d.subs.filter(s=>s.state=="soon");
 const mx=Math.max(1,...d.cash.map(c=>Math.max(c.in,c.out)));
 return `<div class="grid g6">
  ${kpi(money(d.received),"Получено денег","в т.ч. подписки "+money(d.received_subs))}
  ${kpi(money(d.totals.revenue),"Продано (договоры)",d.totals.won+" сделок")}
  ${kpi(money(d.debt_total),"Должны клиенты",d.debts.length+" клиентов",d.debt_total?"warn":"")}
  ${kpi(money(d.mrr),"MRR подписок",d.subs_active+" активных")}
  ${kpi(money(d.spend),"Расходы","реклама "+money(adsSpend))}
  ${kpi(money(cashProfit),"Прибыль (касса)","получено − расходы",cashProfit>=0?"ok":"bad")}
 </div>
 <div class="grid g3" style="margin-top:14px">
  <div class="card"><h3>📌 Сегодня</h3>
   ${line("📞 Ждут звонка",todo.length,"tasks")}${line("⏰ Напоминания на сейчас",due.length,"tasks")}
   ${line("🔴 Просроченные подписки",od.length,"subs",od.length?money(d.subs_overdue_sum):"")}${line("🟡 Оплата подписки скоро",soon.length,"subs")}
   ${line("💸 Должники",d.debts.length,"pay",d.debt_total?money(d.debt_total):"")}</div>
  <div class="card"><h3>🤖 Работа ИИ-агента <span class="mut sm" style="font-weight:400">за период</span></h3>
   <table><tr><td>Обработал диалогов</td><td class="num"><b>${a.dialogs}</b></td></tr><tr><td>Ответов клиентам</td><td class="num">${a.replies}</td></tr>
   <tr><td>Голосовых ответов</td><td class="num">${a.voice_out}</td></tr><tr><td>Дожимов</td><td class="num">${a.followups}</td></tr>
   <tr><td>Лидов (оставили контакт)</td><td class="num"><b>${a.leads}</b> <span class="mut sm">${pct(a.leads,a.dialogs)}</span></td></tr>
   <tr><td>Расход агента (ИИ + голос)</td><td class="num">${money(a.cost,2)}</td></tr>
   <tr><td>Цена лида с подписками сервисов</td><td class="num"><b>${a.leads?money(fullLead,2):"—"}</b></td></tr></table></div>
  <div class="card"><h3>🧭 Воронка продаж</h3>${funnelRows(d)}<div class="mut sm">Диалоги, начатые за период. «Я поговорил» — был звонок, заметка или дальше по этапам.</div></div>
 </div>
 <div class="grid g2" style="margin-top:14px">
  <div class="card"><h3>💰 Касса по месяцам <span class="sp"></span><span class="sm mut" style="font-weight:400"><span class="dot" style="background:var(--ok)"></span>получено <span class="dot" style="background:#f87171;margin-left:8px"></span>расходы</span></h3>
   <div class="chart">${d.cash.map(c=>`<div class="c"><div class="bars"><i style="height:${130*c.in/mx}px;background:var(--ok)" title="${money(c.in)}"></i><i style="height:${130*c.out/mx}px;background:#f87171" title="${money(c.out)}"></i></div>
   <div class="sm mut">${new Date(c.m+"-15").toLocaleDateString("ru",{month:"short"})}</div><div class="sm ${c.in-c.out>=0?"ok":"bad"}">${money(c.in-c.out)}</div></div>`).join("")}</div></div>
  <div class="card"><h3>⚠️ Требует внимания</h3>
   ${[...od.map(s=>`<div class="task">${av(s.name)}<div class="who"><b onclick="go('subs')">${esc(s.name)}</b><div class="sm bad">Подписка просрочена на ${s.overdue_days} дн. · ${money(s.price)}</div></div><div class="acts"><button class="btn sm ok" onclick="openSubPay('${s.id}')">Оплатил</button></div></div>`),
     ...d.debts.slice(0,5).map(x=>`<div class="task">${av(x.who)}<div class="who"><b onclick="drawer('${x.key}')">${esc(x.who)}</b><div class="sm warn">Должен ${money(x.left)} из ${money(x.price)}</div></div><div class="acts"><button class="btn sm" onclick="openPay('${x.key}')">Принять оплату</button></div></div>`),
     ...due.slice(0,5).map(x=>`<div class="task">${av(x.who)}<div class="who"><b onclick="drawer('${x.key}')">${esc(x.who)}</b><div class="sm">⏰ ${dtt(x.remind_ts)} ${esc(x.remind_text)}</div></div><div class="acts">${callBtn(x)}</div></div>`)].join("")||`<div class="empty">Всё под контролем 👍</div>`}
  </div></div>`;
}
const kpi=(v,l,s,cls="")=>`<div class="card kpi"><div class="v ${cls}">${v}</div><div class="l">${l}</div>${s?`<div class="s">${s}</div>`:""}</div>`;
const line=(n,v,p,extra="")=>`<div class="row sb" style="padding:8px 0;border-bottom:1px solid var(--line);cursor:pointer" onclick="go('${p}')"><span>${n}</span><span><b>${v}</b> <span class="mut sm">${extra}</span></span></div>`;
const callBtn=x=>x.tel?`<a class="btn sm ok" href="tel:${esc(x.tel)}">📞 ${esc(x.phone)}</a>`:"";

/* ------------------------------ ЗАДАЧИ ------------------------------ */
function tasks(d){
 const due=d.calls.filter(x=>x.remind_due),first=d.calls.filter(x=>x.todo&&!x.remind_due),later=d.calls.filter(x=>!x.todo&&x.remind_ts).sort((a,b)=>a.remind_ts-b.remind_ts),
  done=d.calls.filter(x=>!x.todo&&!x.remind_ts).slice(0,10);
 const row=x=>`<div class="task">${av(x.who)}<div class="who"><b onclick="drawer('${x.key}')">${esc(x.who)}</b> <span class="dot" style="background:${COL[x.ch]};margin-left:4px"></span>
   <div class="sm">🎯 ${esc(x.want)}${x.call_time?` · <span class="mut">удобно: ${esc(x.call_time)}</span>`:""}${x.budget?` · <span class="mut">💰 ${esc(x.budget)}</span>`:""}</div>
   ${x.remind_ts?`<div class="sm ${x.remind_due?"warn":"mut"}">⏰ ${dtt(x.remind_ts)} ${esc(x.remind_text)}</div>`:""}</div>
  <div class="acts">${callBtn(x)}${x.todo?`<button class="btn sm" onclick="act('deal',{key:'${x.key}',status:'called'},'Отмечено: позвонили')">✓ Позвонил</button>`:""}
   <button class="btn sm ghost" onclick="openRemind('${x.key}')">⏰ ${x.remind_ts?"Изменить":"Напомнить"}</button>
   ${x.deal?`<span class="pill ${x.deal=="won"?"p-ok":""}">${x.deal=="won"?"Купил":"Отказ"}</span>`:""}</div></div>`;
 const sec=(t,L,e)=>`<div class="card" style="margin-bottom:14px"><h3>${t} <span class="pill">${L.length}</span></h3>${L.map(row).join("")||`<div class="empty">${e}</div>`}</div>`;
 return sec("⏰ Пора перезвонить",due,"Нет напоминаний на сейчас")+sec("📞 Ждут первого звонка",first,"Все новые лиды обработаны 👍")+
  sec("🗓 Запланировано",later,"Нет запланированных звонков")+sec("✓ Недавно обработаны",done,"—");
}
async function act(path,body,msg){if(await api(path,body)){toast(msg||"Сохранено");load()}}

/* ------------------------------ СДЕЛКИ (канбан) ------------------------------ */
function deals(d){
 const cols=d.pipe.filter(p=>S.showDialog||p[0]!="dialog");
 return `<div class="row sb" style="margin-bottom:12px"><span class="mut">Перетаскивайте карточки между этапами. Нажмите на карточку — откроется клиент.</span>
  <label class="row" style="gap:6px"><input type="checkbox" ${S.showDialog?"checked":""} onchange="S.showDialog=this.checked;save();render()"> Показать «Диалог с ботом»</label></div>
 <div class="kan">${cols.map(([k,n])=>{const L=d.crm.filter(x=>x.stage==k);const sum=L.reduce((s,x)=>s+Number(x.deal.amount||0),0);
  return `<div class="col" data-st="${k}"><div class="hd">${n} <span>${L.length}${sum?" · "+money(sum):""}</span></div>
  ${L.slice(0,80).map(x=>{const price=Number(x.deal.amount||0);return `<div class="dc" draggable="true" data-k="${esc(x.key)}" onclick="drawer('${x.key}')">
   <b>${esc(x.name||"Клиент")}</b><div class="sm"><span class="dot" style="background:${COL[x.ch]}"></span>${esc(x.phone||CHN[x.ch])}</div>
   ${x.facts.need||x.facts.business?`<div class="sm" style="margin-top:4px">${esc(((x.facts.business?x.facts.business+" · ":"")+(x.facts.need||"")).slice(0,90))}</div>`:""}
   ${price?`<div class="row sb sm" style="margin-top:6px"><span>${money(price)}</span><span class="${x.paid>=price?"ok":"warn"}">оплачено ${money(x.paid)}</span></div><div class="prog"><i style="width:${Math.min(100,100*x.paid/price)}%"></i></div>`:""}
   ${x.remind_ts?`<div class="sm warn" style="margin-top:4px">⏰ ${dtt(x.remind_ts)}</div>`:""}</div>`}).join("")}
  ${L.length>80?`<div class="mut sm">и ещё ${L.length-80}…</div>`:""}</div>`}).join("")}</div>`;
}
function dnd(){
 document.querySelectorAll(".dc").forEach(c=>c.addEventListener("dragstart",e=>{e.dataTransfer.setData("k",c.dataset.k)}));
 document.querySelectorAll(".col").forEach(col=>{
  col.addEventListener("dragover",e=>{e.preventDefault();col.classList.add("drop")});col.addEventListener("dragleave",()=>col.classList.remove("drop"));
  col.addEventListener("drop",async e=>{e.preventDefault();col.classList.remove("drop");const k=e.dataTransfer.getData("k"),st=col.dataset.st;if(!k)return;
   if(st=="won"){openWon(k);return}
   if(await api("client",{key:k,stage:st})){toast("Этап: "+stName(st));load()}});
 });
}
function openWon(k){const x=cl(k);modal(`<h2>🎉 Продажа: ${esc(x.name||"клиент")}</h2><div class="mut">Укажите сумму договора и, если есть, сколько уже оплачено.</div>
 <label class="f">Сумма договора, $</label><input class="inp" id="w-price" type="number" value="${x.deal.amount||""}">
 <label class="f">Оплачено сейчас, $ (необязательно)</label><input class="inp" id="w-paid" type="number" placeholder="0">
 <label class="f">Способ оплаты</label>${methodSel("w-m")}
 <div class="row" style="margin-top:16px"><button class="btn ok" onclick="saveWon('${k}')">Сохранить</button><button class="btn" onclick="closeModal()">Отмена</button></div>`)}
async function saveWon(k){const price=Number($("#w-price").value);if(!(price>0)){$("#w-price").focus();return}
 await api("client",{key:k,stage:"won",amount:price});const paid=Number($("#w-paid").value);
 if(paid>0)await api("pay",{key:k,amount:paid,method:$("#w-m").value,price});closeModal();toast("Продажа сохранена");load()}

/* ------------------------------ КЛИЕНТЫ ------------------------------ */
function clients(d){
 const q=S.q.trim().toLowerCase();
 let L=d.crm.filter(x=>(!S.stage||x.stage==S.stage)&&(!S.ch||x.ch==S.ch));
 if(q)L=L.filter(x=>[x.name,x.username,x.phone,x.tel,x.facts.business,x.facts.need,...x.notes.map(n=>n.t)].join(" ").toLowerCase().includes(q));
 return `<div class="card"><div class="row" style="margin-bottom:12px">
  <input id="q" class="inp" style="flex:1;min-width:200px" placeholder="🔍 Поиск: имя, телефон, бизнес, заметка" value="${esc(S.q)}" oninput="S.q=this.value;S.qf=true;render()">
  <select class="inp" style="width:auto" onchange="S.stage=this.value;render()"><option value="">Все этапы</option>${d.pipe.map(p=>`<option value="${p[0]}" ${S.stage==p[0]?"selected":""}>${p[1]}</option>`).join("")}</select>
  <select class="inp" style="width:auto" onchange="S.ch=this.value;render()"><option value="">Все каналы</option>${Object.entries(CHN).map(([k,n])=>`<option value="${k}" ${S.ch==k?"selected":""}>${n}</option>`).join("")}</select>
  <button class="btn" onclick="exportCsv(this)">📤 Excel</button><button class="btn pri" onclick="openNewClient()">＋ Клиент</button></div>
  <div class="mut sm" style="margin-bottom:6px">${L.length} клиентов</div>
  <div style="overflow-x:auto"><table><tr><th>Клиент</th><th>Телефон</th><th class="hide-m">Что хочет</th><th>Этап</th><th class="num">Сумма</th><th class="num hide-m">Оплачено</th><th class="hide-m">Последнее</th><th class="hide-m">Бот</th></tr>
  ${L.slice(0,300).map(x=>{const price=Number(x.deal.amount||0);return `<tr class="click" onclick="drawer('${x.key}')"><td><div class="row" style="gap:8px;flex-wrap:nowrap">${av(x.name)}<div><b>${esc(x.name||"—")}</b><div class="sm mut"><span class="dot" style="background:${COL[x.ch]}"></span>${CHN[x.ch]}${x.username?" · @"+esc(x.username):""}</div></div></div></td>
   <td style="white-space:nowrap">${esc(x.phone||"—")}</td><td class="hide-m sm">${esc(((x.facts.business?x.facts.business+" · ":"")+(x.facts.need||"")).slice(0,70))}</td>
   <td>${stPill(x.stage)}</td><td class="num">${price?money(price):"—"}</td><td class="num hide-m ${price&&x.paid<price?"warn":""}">${x.paid?money(x.paid):"—"}</td>
   <td class="hide-m sm mut">${dt(x.last)}</td><td class="hide-m">${x.ch=="manual"?"":x.bot_off?`<span class="pill p-bad">стоп</span>`:`<span class="pill p-ok">вкл</span>`}</td></tr>`}).join("")}</table></div>
  ${L.length?"":`<div class="empty">Никого не найдено</div>`}</div>`;
}
async function exportCsv(b){b.textContent="⏳";const r=await api("export",{});b.textContent=r?"✓ Файл в Telegram":"Ошибка"}

/* ------------------------------ ПОДПИСКИ ------------------------------ */
const subPill=s=>s.state=="overdue"?`<span class="pill p-bad">просрочка ${s.overdue_days} дн.</span>`:s.state=="soon"?`<span class="pill p-warn">через ${s.due_in} дн.</span>`:
 s.state=="ok"?`<span class="pill p-ok">в срок</span>`:`<span class="pill">${S.d.sub_statuses[s.status]}</span>`;
function subs(d){
 return `<div class="grid g4">${kpi(money(d.mrr),"MRR (в месяц)",d.subs_active+" активных подписок")}${kpi(money(d.received_subs),"Получено за период","по подпискам")}
  ${kpi(d.subs_overdue,"Просрочено",money(d.subs_overdue_sum),d.subs_overdue?"bad":"")}${kpi(money(d.mrr*12),"Годовой доход","если все продлят")}</div>
 <div class="card" style="margin-top:14px"><h3>💳 Подписки AI-агентов <span class="sp"></span><button class="btn sm pri" onclick="openSub()">＋ Подписка</button></h3>
 <div style="overflow-x:auto"><table><tr><th>Клиент</th><th class="hide-m">Продукт</th><th class="num">Цена</th><th>Следующая оплата</th><th class="num hide-m">Всего оплачено</th><th>Статус</th><th></th></tr>
 ${d.subs.map(s=>`<tr><td><b>${esc(s.name)}</b><div class="sm mut">${esc(s.phone||"")}${s.tenant?" · Instagram подключён":""}</div></td><td class="hide-m">${esc(s.product)}</td>
  <td class="num">${money(s.price)}<div class="sm mut">${s.months==1?"в месяц":"за "+s.months+" мес."}</div></td><td>${dday(s.next_due)}<div>${s.status=="active"?subPill(s):""}</div></td>
  <td class="num hide-m">${money(s.paid_total)}<div class="sm mut">${s.payments.length} плат.</div></td><td>${s.status=="active"?`<span class="pill p-ac">активна</span>`:subPill(s)}</td>
  <td style="white-space:nowrap">${s.status=="active"?`<button class="btn sm ok" onclick="openSubPay('${s.id}')">✅ Оплатил</button>`:""} <button class="btn sm ghost" onclick="openSubEdit('${s.id}')">✎</button></td></tr>`).join("")}</table></div>
 ${d.subs.length?"":`<div class="empty">Пока нет подписок. Добавьте клиента на AI-агента — бот будет напоминать о датах оплаты.</div>`}</div>`;
}
const tenantSel=(id,v)=>`<select class="inp" id="${id}"><option value="">— не привязан —</option>${S.d.tenants.map(t=>`<option value="${t.ig_id}" ${v==t.ig_id?"selected":""}>@${esc(t.username)}${t.company?" · "+esc(t.company):""}</option>`).join("")}</select>`;
const methodSel=(id,v)=>`<select class="inp" id="${id}">${Object.entries(S.d.pay_methods).map(([k,n])=>`<option value="${k}" ${v==k?"selected":""}>${n}</option>`).join("")}</select>`;
function openSub(){closeMenu();modal(`<h2>＋ Подписка на AI-агента</h2>
 <div class="two"><div><label class="f">Клиент (компания)</label><input class="inp" id="s-name" list="cl-list"></div><div><label class="f">Телефон</label><input class="inp" id="s-phone"></div></div>
 <datalist id="cl-list">${S.d.crm.slice(0,300).map(x=>`<option value="${esc(x.name)}">`).join("")}</datalist>
 <div class="two"><div><label class="f">Продукт</label><input class="inp" id="s-prod" value="AI-агент"></div><div><label class="f">Instagram клиента</label>${tenantSel("s-ten","")}</div></div>
 <div class="two"><div><label class="f">Цена, $</label><input class="inp" id="s-price" type="number" value="99"></div><div><label class="f">Период оплаты</label><select class="inp" id="s-mon"><option value="1">Каждый месяц</option><option value="3">Раз в 3 месяца</option><option value="6">Раз в полгода</option><option value="12">Раз в год</option></select></div></div>
 <div class="two"><div><label class="f">Дата первой оплаты</label><input class="inp" id="s-start" type="date" value="${today()}"></div><div><label class="f">Способ оплаты</label>${methodSel("s-m")}</div></div>
 <label class="row" style="margin-top:12px"><input type="checkbox" id="s-paid" checked> Первая оплата уже получена</label>
 <label class="f">Заметка</label><input class="inp" id="s-note">
 <div class="row" style="margin-top:16px"><button class="btn pri" onclick="saveSub()">Добавить</button><button class="btn" onclick="closeModal()">Отмена</button></div>`)}
async function saveSub(){const name=$("#s-name").value.trim();if(!name){$("#s-name").focus();return}
 if(await api("sub",{action:"add",name,phone:$("#s-phone").value,product:$("#s-prod").value,tenant:$("#s-ten").value,price:$("#s-price").value,months:$("#s-mon").value,
  start:$("#s-start").value,next_due:$("#s-start").value,paid_now:$("#s-paid").checked,method:$("#s-m").value,note:$("#s-note").value})){closeModal();toast("Подписка добавлена");load()}}
function openSubPay(id){const s=S.d.subs.find(x=>x.id==id);modal(`<h2>✅ Оплата подписки</h2><div class="mut">${esc(s.name)} · период с ${dday(s.next_due)}</div>
 <div class="two"><div><label class="f">Сумма, $</label><input class="inp" id="sp-a" type="number" value="${s.price}"></div><div><label class="f">Способ</label>${methodSel("sp-m")}</div></div>
 <div class="mut sm" style="margin-top:10px">Следующая оплата сдвинется на ${dday(addM(s.next_due,s.months))}</div>
 <div class="row" style="margin-top:16px"><button class="btn ok" onclick="act('sub',{action:'pay',id:'${id}',amount:$('#sp-a').value,method:$('#sp-m').value},'Оплата записана');closeModal()">Записать оплату</button><button class="btn" onclick="closeModal()">Отмена</button></div>`)}
function addM(day,n){const d=new Date(day+"T12:00");d.setMonth(d.getMonth()+n);return d.toISOString().slice(0,10)}
function openSubEdit(id){const s=S.d.subs.find(x=>x.id==id);modal(`<h2>✎ Подписка: ${esc(s.name)}</h2>
 <div class="two"><div><label class="f">Клиент</label><input class="inp" id="se-name" value="${esc(s.name)}"></div><div><label class="f">Телефон</label><input class="inp" id="se-phone" value="${esc(s.phone)}"></div></div>
 <div class="two"><div><label class="f">Продукт</label><input class="inp" id="se-prod" value="${esc(s.product)}"></div><div><label class="f">Instagram</label>${tenantSel("se-ten",s.tenant)}</div></div>
 <div class="two"><div><label class="f">Цена, $</label><input class="inp" id="se-price" type="number" value="${s.price}"></div><div><label class="f">Следующая оплата</label><input class="inp" id="se-due" type="date" value="${s.next_due}"></div></div>
 <label class="f">Статус</label><select class="inp" id="se-st">${Object.entries(S.d.sub_statuses).map(([k,n])=>`<option value="${k}" ${s.status==k?"selected":""}>${n}</option>`).join("")}</select>
 <label class="f">Заметка</label><input class="inp" id="se-note" value="${esc(s.note)}">
 ${s.payments.length?`<label class="f">История оплат</label>${s.payments.slice().reverse().map(p=>`<div class="row sb sm" style="padding:4px 0"><span>${dt(p.ts)} · ${S.d.pay_methods[p.method]||""}</span><b>${money(p.amount)}</b></div>`).join("")}
  <button class="btn sm ghost" style="margin-top:6px" onclick="act('sub',{action:'unpay',id:'${id}'},'Последняя оплата отменена');closeModal()">↩︎ Отменить последнюю оплату</button>`:""}
 <div class="row" style="margin-top:16px"><button class="btn pri" onclick="saveSubEdit('${id}')">Сохранить</button><button class="btn danger" onclick="if(confirm('Удалить подписку?')){act('sub',{action:'delete',id:'${id}'},'Удалено');closeModal()}">Удалить</button><button class="btn" onclick="closeModal()">Отмена</button></div>`)}
async function saveSubEdit(id){if(await api("sub",{action:"update",id,name:$("#se-name").value,phone:$("#se-phone").value,product:$("#se-prod").value,tenant:$("#se-ten").value,
 price:$("#se-price").value,next_due:$("#se-due").value,status:$("#se-st").value,note:$("#se-note").value})){closeModal();toast("Сохранено");load()}}

/* ------------------------------ ПЛАТЕЖИ ------------------------------ */
function pay(d){
 return `<div class="grid g4">${kpi(money(d.received),"Получено за период",d.payments.length+" платежей")}${kpi(money(d.received-d.received_subs),"За проекты","сайты, CRM, приложения")}
  ${kpi(money(d.received_subs),"За подписки","AI-агенты")}${kpi(money(d.debt_total),"Должны клиенты",d.debts.length+" клиентов",d.debt_total?"warn":"")}</div>
 <div class="grid g2" style="margin-top:14px">
 <div class="card"><h3>💵 Поступления <span class="sp"></span><button class="btn sm pri" onclick="openPay()">＋ Платёж</button></h3>
  <table><tr><th>Дата</th><th>От кого</th><th>За что</th><th class="num">Сумма</th><th></th></tr>
  ${d.payments.map(p=>`<tr><td class="sm">${dt(p.ts)}</td><td>${p.kind=="deal"?`<a href="#" onclick="drawer('${p.key}');return false">${esc(p.who)}</a>`:esc(p.who)}</td>
   <td class="sm mut">${p.kind=="sub"?"Подписка · "+esc(p.product||""):"Проект"}${p.note?" · "+esc(p.note):""} · ${d.pay_methods[p.method]||""}</td><td class="num"><b>${money(p.amount,0)}</b></td>
   <td>${p.kind=="deal"?`<button class="btn sm ghost" onclick="if(confirm('Удалить платёж?'))act('pay',{key:'${p.key}',delete:'${p.id}'},'Удалено')">✕</button>`:""}</td></tr>`).join("")}</table>
  ${d.payments.length?"":`<div class="empty">За период платежей нет</div>`}</div>
 <div class="card"><h3>💸 Должники</h3>
  ${d.debts.map(x=>`<div class="task">${av(x.who)}<div class="who"><b onclick="drawer('${x.key}')">${esc(x.who)}</b><div class="sm">Договор ${money(x.price)} · оплачено ${money(x.paid)}</div>
   <div class="prog"><i style="width:${100*x.paid/x.price}%"></i></div></div><div class="acts"><b class="warn">${money(x.left)}</b><button class="btn sm" onclick="openPay('${x.key}')">Принять</button></div></div>`).join("")||`<div class="empty">Должников нет 👍</div>`}</div></div>`;
}
function openPay(key){closeMenu();const x=key?cl(key):null;modal(`<h2>＋ Платёж за проект</h2><div class="mut sm">Оплата подписок — во вкладке «Подписки», кнопка «Оплатил».</div>
 <label class="f">Клиент</label>${x?`<div><b>${esc(x.name)}</b> ${x.deal.amount?`<span class="mut sm">· договор ${money(x.deal.amount)}, оплачено ${money(x.paid)}</span>`:""}</div><input type="hidden" id="p-k" value="${esc(key)}">`:
  `<select class="inp" id="p-k"><option value="">— выберите клиента —</option>${S.d.crm.filter(c=>c.stage!="dialog").map(c=>`<option value="${esc(c.key)}">${esc(c.name||"Клиент")} ${esc(c.phone||"")}</option>`).join("")}</select>`}
 <div class="two"><div><label class="f">Сумма, $</label><input class="inp" id="p-a" type="number" value="${x&&x.deal.amount?Math.max(0,x.deal.amount-x.paid):""}"></div><div><label class="f">Способ</label>${methodSel("p-m")}</div></div>
 <div class="two"><div><label class="f">Дата</label><input class="inp" id="p-d" type="date" value="${today()}"></div><div><label class="f">Сумма договора, $ (если ещё не указана)</label><input class="inp" id="p-price" type="number" value="${x&&x.deal.amount||""}"></div></div>
 <label class="f">Комментарий</label><input class="inp" id="p-n" placeholder="Предоплата 50%, остаток и т.п.">
 <div class="row" style="margin-top:16px"><button class="btn ok" onclick="savePay()">Записать</button><button class="btn" onclick="closeModal()">Отмена</button></div>`)}
async function savePay(){const k=$("#p-k").value,a=Number($("#p-a").value);if(!k){$("#p-k").focus();return}if(!(a>0)){$("#p-a").focus();return}
 const price=Number($("#p-price").value);if(price>0)await api("price",{key:k,price});
 if(await api("pay",{key:k,amount:a,method:$("#p-m").value,ts:new Date($("#p-d").value+"T12:00").getTime()/1000,note:$("#p-n").value,price})){closeModal();toast("Платёж записан");load()}}

/* ------------------------------ РАСХОДЫ ------------------------------ */
function exp(d){
 const cn=Object.fromEntries(d.exp_cats.map(c=>[c[0],c[1]])), auto=d.spend_auto, rec=d.recurring;
 const cats=[["auto","ИИ-агент (Claude API, голос, сервер — авто)",auto],...d.exp_cats.map(c=>[c[0],c[1],d.by_cat[c[0]]||0])].filter(x=>x[2]>0);
 const e=d.econ;
 return `<div class="grid g4">${kpi(money(d.spend,0),"Все расходы за период")}${kpi(money((d.by_cat.ads_ig||0)+(d.by_cat.ads_tg||0)+(d.by_cat.ads_other||0)),"Реклама и таргет")}
  ${kpi(money((d.by_cat.ai||0)+(d.by_cat.server||0)+(d.by_cat.voice||0)+(d.by_cat.services||0)),"Сервисы и подписки")}${kpi(money(auto,2),"Работа ИИ-агента","Claude API + голос")}</div>
 <div class="grid g2" style="margin-top:14px">
 <div class="card"><h3>📉 Куда уходят деньги <span class="sp"></span><button class="btn sm pri" onclick="openExp()">＋ Расход</button></h3>
  ${cats.map(([k,n,v])=>`<div class="fn" style="grid-template-columns:1fr 120px 80px"><div>${n}</div><div class="fbar"><i style="width:${100*v/(d.spend||1)}%"></i></div><div class="num"><b>${money(v,0)}</b> <span class="mut sm">${pct(v,d.spend)}</span></div></div>`).join("")||`<div class="empty">Нет расходов за период</div>`}</div>
 <div class="card"><h3>🔁 Регулярные расходы <span class="sp"></span><button class="btn sm" onclick="openExp(true)">＋ Регулярный</button></h3>
  <table>${rec.map(r=>`<tr><td><b>${esc(r.note||cn[r.cat])}</b><div class="sm mut">${cn[r.cat]} · с ${dday(r.since)}</div></td>
   <td class="num"><b>${money(r.amount,0)}</b><div class="sm mut">${r.freq=="monthly"?"в месяц":"в день"}</div></td>
   <td style="white-space:nowrap"><button class="btn sm ghost" onclick="editRec('${r.id}')">✎</button> <button class="btn sm ghost danger" onclick="if(confirm('Остановить этот расход?'))act('expense',{stop:'${r.id}'},'Остановлено')">Стоп</button></td></tr>`).join("")}</table>
  ${rec.length?`<div class="mut sm" style="margin-top:8px">В месяц: <b>${money(rec.reduce((s,r)=>s+(r.freq=="monthly"?r.amount:r.amount*30),0))}</b>. Добавляются в расходы автоматически.</div>`:`<div class="empty">Добавьте подписки (Claude, Railway…) и дневной бюджет таргета</div>`}</div></div>
 <div class="card" style="margin-top:14px"><h3>📊 Окупаемость рекламы по каналам</h3><div style="overflow-x:auto"><table><tr><th>Канал</th><th class="num">Реклама</th><th class="num">ИИ-агент</th><th class="num">Диалогов</th><th class="num">Лидов</th><th class="num">Продаж</th><th class="num">Выручка</th><th class="num">Цена лида</th><th class="num">Цена продажи</th><th class="num">ROMI</th></tr>
  ${["tg","ig"].map(c=>`<tr><td><span class="dot" style="background:${COL[c]}"></span>${CHN[c]}</td><td class="num">${money(e[c].ads)}</td><td class="num">${money(e[c].bot,2)}</td><td class="num">${e[c].dialogs}</td><td class="num">${e[c].leads}</td><td class="num">${e[c].won}</td><td class="num">${money(e[c].revenue)}</td>
   <td class="num">${e[c].leads?money(e[c].per_lead,2):"—"}</td><td class="num">${e[c].won?money(e[c].per_sale):"—"}</td><td class="num ${e[c].romi>0?"ok":e[c].romi<0?"bad":""}">${e[c].romi===null?"—":e[c].romi+"%"}</td></tr>`).join("")}</table></div></div>
 <div class="card" style="margin-top:14px"><h3>🧾 Все расходы за период</h3><table><tr><th>Дата</th><th>Категория</th><th>Комментарий</th><th class="num">Сумма</th><th></th></tr>
  ${d.expenses.slice(0,200).map(x=>`<tr><td class="sm">${dt(x.ts)}</td><td>${esc(cn[x.cat]||"")}</td><td class="sm mut">${esc(x.note)}</td><td class="num"><b>${money(x.amount,2)}</b></td>
   <td><button class="btn sm ghost" onclick="if(confirm('Удалить?'))act('expense',{delete:'${x.id}'},'Удалено')">✕</button></td></tr>`).join("")}</table>${d.expenses.length?"":`<div class="empty">Пусто</div>`}</div>`;
}
function openExp(rec){closeMenu();modal(`<h2>${rec?"🔁 Регулярный расход":"＋ Расход"}</h2>
 <div class="two"><div><label class="f">Категория</label><select class="inp" id="e-c">${S.d.exp_cats.map(c=>`<option value="${c[0]}">${c[1]}</option>`).join("")}</select></div>
 <div><label class="f">Сумма, $</label><input class="inp" id="e-a" type="number" placeholder="0"></div></div>
 <div class="two"><div><label class="f">${rec?"Начиная с":"Дата"}</label><input class="inp" id="e-d" type="date" value="${today()}"></div>
 <div><label class="f">Повторять</label><select class="inp" id="e-f"><option value="">Нет, разово</option><option value="daily" ${rec?"":""}>Каждый день</option><option value="monthly" ${rec?"selected":""}>Каждый месяц</option></select></div></div>
 <label class="f">Комментарий</label><input class="inp" id="e-n" placeholder="Например: Claude, таргет на сайт, кампания №2">
 <div class="mut sm" style="margin-top:8px">Таргет: удобно задать «каждый день» с дневным бюджетом. Подписки сервисов — «каждый месяц».</div>
 <div class="row" style="margin-top:16px"><button class="btn pri" onclick="saveExp()">Добавить</button><button class="btn" onclick="closeModal()">Отмена</button></div>`)}
async function saveExp(){const a=Number($("#e-a").value);if(!(a>0)){$("#e-a").focus();return}const f=$("#e-f").value,dv=$("#e-d").value;
 if(await api("expense",{cat:$("#e-c").value,amount:a,note:$("#e-n").value,ts:new Date(dv+"T12:00").getTime()/1000,since:dv,freq:f||undefined,daily:f=="daily"})){closeModal();toast("Расход добавлен");load()}}
function editRec(id){const r=S.d.recurring.find(x=>x.id==id);modal(`<h2>✎ Регулярный расход</h2><label class="f">Название</label><input class="inp" id="r-n" value="${esc(r.note)}">
 <label class="f">Сумма, $ (${r.freq=="monthly"?"в месяц":"в день"})</label><input class="inp" id="r-a" type="number" value="${r.amount}">
 <div class="mut sm" style="margin-top:8px">Новая сумма применится к следующим списаниям.</div>
 <div class="row" style="margin-top:16px"><button class="btn pri" onclick="act('expense',{update_rec:'${id}',amount:$('#r-a').value,note:$('#r-n').value},'Сохранено');closeModal()">Сохранить</button><button class="btn" onclick="closeModal()">Отмена</button></div>`)}

/* ------------------------------ БОТ ------------------------------ */
function bot(d){
 const a=d.agent, recent=d.crm.filter(x=>x.ch!="manual").slice(0,40);
 return `<div class="grid g4">${kpi(a.dialogs,"Диалогов за период",a.msgs_in+" сообщений от клиентов")}${kpi(a.leads,"Лидов",pct(a.leads,a.dialogs)+" конверсия")}
  ${kpi(money(a.cost,2),"Расход агента","ИИ "+money(a.ai_usd,2)+" · голос "+money(a.voice_usd,2))}${kpi(a.leads?money(a.cost/a.leads,3):"—","Цена лида (агент)")}</div>
 <div class="grid g2" style="margin-top:14px">
 <div class="card"><h3>📋 Указания боту</h3><div class="mut sm" style="margin-bottom:8px">Бот выполняет их во всех диалогах. Можно писать и прямо боту в Telegram.</div>
  ${d.rules.map((r,i)=>`<div class="note row sb"><span>${i+1}. ${esc(r.t)}</span><button class="btn sm ghost" onclick="act('rule',{delete:${i+1}},'Удалено')">✕</button></div>`).join("")||`<div class="empty">Указаний пока нет</div>`}
  <div class="row" style="margin-top:8px"><input class="inp" id="rule" style="flex:1" placeholder="Например: не обещай скидки, предлагай звонок"><button class="btn pri" onclick="if($('#rule').value.trim())act('rule',{text:$('#rule').value},'Указание добавлено')">Добавить</button></div></div>
 <div class="card"><h3>🎙 Голос и подключения</h3>
  <label class="f">Стиль голосовых ответов</label><div class="seg" style="width:max-content">${[["calm","🧘 Спокойный"],["lively","🙂 Живой"]].map(([k,n])=>`<button class="${d.voice_mode==k?"on":""}" onclick="act('voice',{mode:'${k}'},'Голос: '+'${n}')">${n}</button>`).join("")}</div>
  <label class="f" style="margin-top:16px">Instagram-аккаунты (боты клиентов)</label>
  ${d.tenants.map(t=>`<div class="row sb" style="padding:6px 0;border-bottom:1px solid var(--line)"><span>@${esc(t.username)} ${t.company?`<span class="mut sm">· ${esc(t.company)}</span>`:""}</span>
   <span>${t.enabled?`<span class="pill p-ok">работает</span>`:`<span class="pill">выкл</span>`} ${t.kb?"":`<span class="pill p-warn">нет базы</span>`}</span></div>`).join("")||`<div class="mut">Нет</div>`}
  <div class="row" style="margin-top:10px"><button class="btn sm" onclick="navigator.clipboard.writeText('${esc(d.connect_url)}');toast('Ссылка скопирована')">📋 Ссылка подключения Instagram для клиента</button></div></div></div>
 <div class="card" style="margin-top:14px"><h3>💬 Последние диалоги</h3><table><tr><th>Клиент</th><th class="hide-m">Последнее сообщение</th><th>Этап</th><th>Бот</th></tr>
  ${recent.map(x=>{const m=x.tail[x.tail.length-1]||{};return `<tr class="click" onclick="drawer('${x.key}')"><td><b>${esc(x.name||"Клиент")}</b><div class="sm mut"><span class="dot" style="background:${COL[x.ch]}"></span>${dtt(x.last)}</div></td>
   <td class="hide-m sm">${m.r=="u"?"👤 ":"🤖 "}${esc((m.t||"").slice(0,90))}</td><td>${stPill(x.stage)}</td>
   <td onclick="event.stopPropagation()"><button class="btn sm ${x.bot_off?"ok":"ghost"}" onclick="act('bot',{key:'${x.key}',on:${x.bot_off?"true":"false"}},'${x.bot_off?"Бот включён":"Бот остановлен"}')">${x.bot_off?"▶️ Включить":"⏸ Стоп"}</button></td></tr>`}).join("")}</table></div>`;
}

/* ------------------------------ КАРТОЧКА КЛИЕНТА ------------------------------ */
function drawer(k){S.ckey=k;const x=cl(k);if(!x.key)return;const f=x.facts,price=Number(x.deal.amount||0);
 $("#drawer").classList.add("on");
 $("#pn").innerHTML=`<div class="ph"><div class="row" style="flex-wrap:nowrap">${av(x.name)}<div style="flex:1;min-width:0"><b style="font-size:18px">${esc(x.name||"Клиент")}</b>
   <div class="sm mut"><span class="dot" style="background:${COL[x.ch]}"></span>${CHN[x.ch]}${x.username?" · @"+esc(x.username):""} · с ${dt(x.first)} · готовность ${x.readiness}%</div></div>
   <button class="btn ghost" onclick="closeDrawer()">✕</button></div>
  <div class="row" style="margin-top:12px">${x.tel?`<a class="btn ok" href="tel:${esc(x.tel)}">📞 ${esc(x.phone)}</a>`:""}
   <button class="btn" onclick="openRemind('${k}')">⏰ ${x.remind_ts?dtt(x.remind_ts):"Напомнить"}</button>
   ${x.link?`<a class="btn" href="${esc(x.link)}" target="_blank">💬 Чат</a>`:""}
   <select class="inp" style="width:auto" onchange="this.value=='won'?openWon('${k}'):act('client',{key:'${k}',stage:this.value},'Этап изменён')">${S.d.pipe.map(p=>`<option value="${p[0]}" ${x.stage==p[0]?"selected":""}>${p[1]}</option>`).join("")}</select></div>
  ${x.ch!="manual"?`<div class="botbar ${x.bot_off?"off":""}"><span>${x.bot_off?"⏸ Бот не отвечает этому клиенту":"🤖 Бот отвечает этому клиенту"}</span>
   <button class="btn sm" onclick="act('bot',{key:'${k}',on:${x.bot_off?"true":"false"}},'${x.bot_off?"Бот включён":"Бот остановлен"}')">${x.bot_off?"▶️ Включить":"⏸ Стоп бот"}</button></div>`:""}
  <div class="tabs">${[["profile","Профиль"],["money","Оплаты"],["chat","Переписка"],["notes","Заметки "+(x.notes.length||"")]].map(([t,n])=>`<button class="${S.ctab==t?"on":""}" onclick="S.ctab='${t}';drawer('${k}')">${n}</button>`).join("")}</div></div>
  <div class="pb" id="pb">${{profile:cProfile,money:cMoney,chat:cChat,notes:cNotes}[S.ctab](x,k)}</div>`;
 if(S.ctab=="chat")loadHist(k);
}
function closeDrawer(){$("#drawer").classList.remove("on");S.ckey=null}
function cProfile(x,k){const f=x.facts,F=(id,l,v,ph)=>`<div><label class="f">${l}</label><input class="inp" id="cf-${id}" value="${esc(v||"")}" placeholder="${ph||""}"></div>`;
 return `<div class="card"><div class="two">${F("name","Имя",x.name)}${F("phone","Телефон",x.phone,"+998 …")}${F("business","Бизнес",f.business)}${F("budget","Бюджет",f.budget)}</div>
  ${F("need","Что хочет",f.need)}${F("offer","Что предложили",f.offer)}${F("call_time","Удобное время для звонка",f.call_time)}
  ${f.objection?`<div class="note sm">⚠️ Возражение: ${esc(f.objection)}</div>`:""}${f.note?`<div class="note sm">📝 Итог бота: ${esc(f.note)}</div>`:""}
  <div class="row" style="margin-top:14px"><button class="btn pri" onclick="saveProfile('${k}')">💾 Сохранить</button><span class="mut sm">Расход на клиента: ${money(x.cost,3)}</span></div></div>`}
async function saveProfile(k){const fields={};["name","phone","business","budget","need","offer","call_time"].forEach(i=>fields[i]=$("#cf-"+i).value);
 if(await api("client",{key:k,fields})){toast("Сохранено");load()}}
function cMoney(x,k){const price=Number(x.deal.amount||0),left=Math.max(0,price-x.paid);
 return `<div class="card"><div class="grid g3">${kpi(price?money(price):"—","Договор")}${kpi(money(x.paid),"Оплачено","","ok")}${kpi(money(left),"Остаток","",left?"warn":"")}</div>
  ${price?`<div class="prog" style="height:8px;margin-top:12px"><i style="width:${Math.min(100,100*x.paid/price)}%"></i></div>`:""}
  <div class="row" style="margin-top:14px"><input class="inp" id="cm-price" type="number" style="width:160px" placeholder="Сумма договора $" value="${price||""}"><button class="btn" onclick="act('price',{key:'${k}',price:$('#cm-price').value},'Сумма договора сохранена')">Сохранить сумму</button>
   <button class="btn ok" onclick="openPay('${k}')">＋ Принять оплату</button></div></div>
  <div class="card" style="margin-top:12px"><h3>История оплат</h3>${x.payments.slice().reverse().map(p=>`<div class="row sb" style="padding:8px 0;border-bottom:1px solid var(--line)"><span>${dt(p.ts)} · ${S.d.pay_methods[p.method]||""}${p.note?` · <span class="mut">${esc(p.note)}</span>`:""}</span>
   <span><b>${money(p.amount)}</b> <button class="btn sm ghost" onclick="if(confirm('Удалить платёж?'))act('pay',{key:'${k}',delete:'${p.id}'},'Удалено')">✕</button></span></div>`).join("")||`<div class="empty">Оплат пока нет</div>`}</div>`}
function cChat(x,k){return `<div id="hist"><div class="empty">Загрузка переписки…</div></div>`}
async function loadHist(k){const r=await api("history",{key:k});if(!r||S.ckey!=k)return;
 $("#hist").innerHTML=r.items.map(m=>`<div class="msg ${m.r=="a"?"a":""}"><div class="t">${m.r=="u"?"Клиент":m.h?"Менеджер":m.v?"Бот · голосовое":m.f?"Бот · дожим":"Бот"} · ${dtt(m.ts)}</div>${esc(m.t)}</div>`).join("")||`<div class="empty">Переписки нет</div>`}
function cNotes(x,k){return `<div class="card"><textarea class="inp" id="cn" rows="3" placeholder="Что обсудили, договорённости, следующий шаг…"></textarea>
 <div class="row" style="margin-top:8px"><button class="btn pri" onclick="if($('#cn').value.trim())act('client',{key:'${k}',note:$('#cn').value},'Заметка добавлена')">Добавить заметку</button></div></div>
 ${x.notes.slice().reverse().map(n=>`<div class="note"><div class="sm mut">${dtt(n.ts)}</div>${esc(n.t)}</div>`).join("")}`}
function openRemind(k){const x=cl(k),def=new Date(x.remind_ts?x.remind_ts*1000:Date.now()+3600e3);modal(`<h2>⏰ Напоминание</h2><div class="mut">${esc(x.name||"")} ${esc(x.phone||"")}</div>
 <label class="f">Когда</label><input class="inp" id="rm-d" type="datetime-local" value="${localDT(def)}">
 <div class="row" style="margin-top:8px">${[["+1 час",60],["+3 часа",180],["Завтра 10:00","tm"],["Через неделю",10080]].map(([n,v])=>`<button class="btn sm ghost" onclick="quick('${v}')">${n}</button>`).join("")}</div>
 <label class="f">Комментарий</label><textarea class="inp" id="rm-t" rows="2" placeholder="Например: перезвонить после совещания, отправить КП">${esc(x.remind_text||"")}</textarea>
 <div class="mut sm" style="margin-top:8px">В это время бот пришлёт вам в Telegram номер и комментарий.</div>
 <div class="row" style="margin-top:16px"><button class="btn pri" onclick="saveRemind('${k}')">Сохранить</button>${x.remind_ts?`<button class="btn danger" onclick="act('remind',{key:'${k}',ts:0},'Напоминание удалено');closeModal()">Удалить</button>`:""}<button class="btn" onclick="closeModal()">Отмена</button></div>`)}
function quick(v){const d=v=="tm"?(()=>{const t=new Date(Date.now()+864e5);t.setHours(10,0,0,0);return t})():new Date(Date.now()+Number(v)*6e4);$("#rm-d").value=localDT(d)}
async function saveRemind(k){const ts=new Date($("#rm-d").value).getTime()/1000;if(!(ts>Date.now()/1000)){$("#rm-d").focus();return}
 if(await api("remind",{key:k,ts,text:$("#rm-t").value})){closeModal();toast("Напомню "+dtt(ts));load()}}
function openNewClient(){closeMenu();modal(`<h2>＋ Новый клиент</h2><div class="mut sm">Например, позвонил сам или пришёл по рекомендации.</div>
 <div class="two"><div><label class="f">Имя</label><input class="inp" id="nc-name"></div><div><label class="f">Телефон</label><input class="inp" id="nc-phone" placeholder="+998 …"></div></div>
 <div class="two"><div><label class="f">Бизнес</label><input class="inp" id="nc-business"></div><div><label class="f">Бюджет</label><input class="inp" id="nc-budget"></div></div>
 <label class="f">Что хочет</label><input class="inp" id="nc-need"><label class="f">Заметка</label><textarea class="inp" id="nc-note" rows="2"></textarea>
 <div class="row" style="margin-top:16px"><button class="btn pri" onclick="saveNew()">Добавить</button><button class="btn" onclick="closeModal()">Отмена</button></div>`)}
async function saveNew(){const b={};["name","phone","business","budget","need","note"].forEach(i=>b[i]=$("#nc-"+i).value);if(!b.name&&!b.phone){$("#nc-name").focus();return}
 const r=await api("new",b);if(r){closeModal();toast("Клиент добавлен");await load();if(r.key){S.ctab="profile";drawer(r.key)}}}
function modal(h){$("#mb").innerHTML=h;$("#modal").classList.add("on");const i=$("#mb input:not([type=hidden]),#mb select");if(i&&innerWidth>860)i.focus()}
function closeModal(){$("#modal").classList.remove("on")}
function closeMenu(){$("#addm").classList.remove("on")}
document.addEventListener("keydown",e=>{if(e.key=="Escape"){closeModal();closeDrawer()}});
chrome();load();setInterval(()=>{if(!document.hidden&&!$("#modal").classList.contains("on"))load()},60000);
</script></body></html>"""

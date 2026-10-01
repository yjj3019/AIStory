// 실제 Chrome(헤드리스)으로 두 페이지를 띄워 audio18 연동을 시뮬레이션한다.
//   1) python -m http.server 8793  (프로젝트 루트에서)
//   2) node .agent/sim_page.mjs http://localhost:8793
// 검사: 페이지가 계산한 클립 id 20개 == manifest id, 각 클립(mp3/wav) 메타데이터 로딩·길이,
//       타이머 목표 == manifest 총합, 시작 클릭 후 실제 재생(고품질 음성), 콘솔/네트워크 오류
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const base = process.argv[2] || 'http://localhost:8793';
const chromePaths = ['C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe'];
const chrome = chromePaths.find(p => fs.existsSync(p));
if (!chrome) { console.log('chrome 없음'); process.exit(2); }
const port = 9333;
const udd = fs.mkdtempSync(path.join(os.tmpdir(), 'sim-'));
const proc = spawn(chrome, ['--headless=new', '--disable-gpu', '--no-sandbox', '--autoplay-policy=no-user-gesture-required',
  `--remote-debugging-port=${port}`, `--user-data-dir=${udd}`, '--window-size=1366,768', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function target() {
  for (let i = 0; i < 40; i++) {
    try {
      const l = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      const p = l.find(t => t.type === 'page');
      if (p) return p.webSocketDebuggerUrl;
    } catch {}
    await sleep(500);
  }
  throw new Error('chrome devtools 연결 실패');
}

const ws = new WebSocket(await target());
await new Promise(r => ws.addEventListener('open', r));
let id = 0; const pending = new Map(); const events = [];
ws.addEventListener('message', e => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } else events.push(m);
});
const send = (method, params = {}) => new Promise(r => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const evalJS = async (expr) => {
  const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true, timeout: 120000 });
  if (r.result?.exceptionDetails) return { __error: r.result.exceptionDetails.exception?.description || r.result.exceptionDetails.text };
  return r.result?.result?.value;
};
await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable'); await send('Log.enable');
await send('Page.addScriptToEvaluateOnNewDocument', { source:
  `window.__auds=[];const A=window.Audio;window.Audio=function(...a){const x=new A(...a);window.__auds.push(x);return x};window.Audio.prototype=A.prototype;` });

const PROBE = `(async()=>{
  const o={};
  const g=n=>{try{return eval(n)}catch(e){return undefined}};
  o.audioDir=g('AUDIO_DIR');
  const scenes=g('SCENES');
  o.scenes=scenes?scenes.length:null;
  const cn=g('clipName'), en=g('endingId');
  o.ids=(cn&&scenes)?['00-opening',...scenes.map((_,i)=>cn(i)),en?en():'?']:null;
  let m=null; try{ m=await (await fetch(o.audioDir+'manifest.json')).json(); }catch(e){ o.manifestErr=String(e); }
  o.manifestIds=m?m.items.map(x=>x.id):null;
  o.manifestTotal=m?m.items.reduce((a,x)=>a+x.seconds,0):null;
  o.clips=[];
  for(const id of (o.ids||[])){
    const row={id};
    for(const ext of ['mp3','wav']){
      row[ext]=await new Promise(res=>{const a=new Audio();a.preload='metadata';const t=setTimeout(()=>res('timeout'),20000);
        a.onloadedmetadata=()=>{clearTimeout(t);res(+a.duration.toFixed(2))};a.onerror=()=>{clearTimeout(t);res('error')};a.src=o.audioDir+id+'.'+ext;});
    }
    row.man=m?(m.items.find(x=>x.id===id)||{}).seconds:null;
    o.clips.push(row);
  }
  return o;
})()`;

const results = {};
for (const pageName of ['AIStory.html', 'AIStory-slide.html']) {
  events.length = 0;
  await send('Page.navigate', { url: `${base}/${pageName}` });
  await sleep(3500);
  const r = { page: pageName };
  r.probe = await evalJS(PROBE);
  r.timerBefore = await evalJS(`(document.querySelector('#timer')||{}).textContent`);
  // 자막 보정 앵커(sync.json) 로딩 + 보간 함수 동작 확인
  r.sync = await evalJS(`(()=>{try{return {n:SYNC?Object.keys(SYNC).length:null,
     at30:(SYNC&&SYNC['17-scene'])?+fracAt('17-scene',30,162.9).toFixed(3):null, plain30:+(30/162.9).toFixed(3)}}catch(e){return {err:String(e)}}})()`);
  // 시작 버튼 클릭 → 실제 재생 확인
  r.clicked = await evalJS(`(()=>{const b=[...document.querySelectorAll('button')].find(x=>/이야기 듣기|들으며 시작/.test(x.textContent));if(!b)return null;b.click();return b.textContent.trim()})()`);
  await sleep(6000);
  r.playing = await evalJS(`(()=>{const a=(window.__auds||[]).filter(x=>!x.paused&&x.currentTime>0.3);return a.map(x=>({src:x.src.split('/').slice(-2).join('/'),t:+x.currentTime.toFixed(1)}))})()`);
  r.engine = await evalJS(`(document.querySelector('#engine')||{}).textContent`);
  r.pos = await evalJS(`(document.querySelector('#pos')||{}).textContent`);
  r.timerAfter = await evalJS(`(document.querySelector('#timer')||{}).textContent`);
  r.errors = events.filter(e => e.method === 'Runtime.exceptionThrown' || (e.method === 'Log.entryAdded' && e.params.entry.level === 'error'))
    .map(e => (e.params.exceptionDetails?.exception?.description || e.params.entry?.text || '').slice(0, 160));
  r.http4xx = events.filter(e => e.method === 'Network.responseReceived' && e.params.response.status >= 400)
    .map(e => `${e.params.response.status} ${e.params.response.url.replace(base, '')}`);
  results[pageName] = r;
}

// 판정
let bad = 0; const out = [];
const fmt = s => { const n = Math.round(s); return `${Math.floor(n / 60)}:${String(n % 60).padStart(2, '0')}`; };
for (const [name, r] of Object.entries(results)) {
  const p = r.probe || {}; const probs = [];
  if (p.__error) probs.push('probe 오류: ' + p.__error);
  else {
    if (!p.ids) probs.push('페이지에서 클립 id 를 얻지 못함');
    if (p.audioDir !== 'audio18/') probs.push(`AUDIO_DIR=${p.audioDir}`);
    if (p.ids && p.manifestIds && JSON.stringify(p.ids) !== JSON.stringify(p.manifestIds)) probs.push(`페이지 id ${p.ids.length}개 ≠ manifest id ${p.manifestIds.length}개`);
    for (const c of p.clips || []) {
      for (const ext of ['mp3', 'wav']) if (typeof c[ext] !== 'number') probs.push(`${c.id}.${ext} 로딩 실패(${c[ext]})`);
      if (typeof c.mp3 === 'number' && c.man && Math.abs(c.mp3 - c.man) > 0.5) probs.push(`${c.id}: mp3 ${c.mp3}s ≠ manifest ${c.man}s`);
    }
    if (p.manifestTotal && r.timerAfter && !r.timerAfter.includes(fmt(p.manifestTotal))) probs.push(`타이머 ${r.timerAfter} ≠ manifest 총합 ${fmt(p.manifestTotal)}`);
  }
  if (!r.sync || r.sync.err || r.sync.n !== 20) probs.push('sync.json 앵커 로딩 실패: ' + JSON.stringify(r.sync));
  if (r.clicked === null) probs.push('시작 버튼을 찾지 못함');
  if (!r.playing || r.playing.length === 0) probs.push('시작 후 재생 중인 오디오 없음');
  if (r.engine && !/고품질/.test(r.engine)) probs.push(`엔진 표시 "${r.engine}" (고품질 음성 아님)`);
  if (r.errors.length) probs.push('콘솔 오류: ' + r.errors.join(' | '));
  if (r.http4xx.length) probs.push('HTTP 오류: ' + [...new Set(r.http4xx)].join(', '));
  bad += probs.length;
  out.push(`## ${name}\n- 자막 앵커: ${JSON.stringify(r.sync)}\n- 클립 ${p.ids ? p.ids.length : '?'}개 / 장 ${p.scenes} / 타이머 ${r.timerBefore} → ${r.timerAfter} / 엔진 "${r.engine}" / 위치 ${r.pos}\n- 재생 중: ${JSON.stringify(r.playing)}\n- 문제: ${probs.length ? '\n  - ' + probs.join('\n  - ') : '없음'}`);
}
console.log(out.join('\n\n'));
ws.close(); proc.kill();
try { fs.rmSync(udd, { recursive: true, force: true }); } catch {}
process.exit(bad ? 1 : 0);

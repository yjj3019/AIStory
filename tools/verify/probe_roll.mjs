// 엔딩 크레딧 자동 스크롤 동작 측정. node probe_roll.mjs <baseUrl> [reduced]
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
const base = process.argv[2]; const reduced = process.argv[3] === 'reduced';
const chrome = ['C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe'].find(p => fs.existsSync(p));
const port = 9300 + Math.floor(Math.random() * 90);
const udd = fs.mkdtempSync(path.join(os.tmpdir(), 'roll-'));
const proc = spawn(chrome, ['--headless=new', '--disable-gpu', '--no-sandbox', '--autoplay-policy=no-user-gesture-required', `--remote-debugging-port=${port}`, `--user-data-dir=${udd}`, 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let wsUrl; for (let i = 0; i < 40 && !wsUrl; i++) { try { const l = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json(); wsUrl = l.find(t => t.type === 'page')?.webSocketDebuggerUrl; } catch {} if (!wsUrl) await sleep(500); }
const ws = new WebSocket(wsUrl); await new Promise(r => ws.addEventListener('open', r));
let id = 0; const pend = new Map();
ws.addEventListener('message', e => { const m = JSON.parse(e.data); if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); } });
const send = (method, params = {}) => new Promise(r => { const i = ++id; pend.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async (x) => { const r = await send('Runtime.evaluate', { expression: x, awaitPromise: true, returnByValue: true }); return r.result?.result?.value ?? r.result?.exceptionDetails?.exception?.description; };
await send('Page.enable'); await send('Runtime.enable');
await send('Emulation.setDeviceMetricsOverride', { width: 1366, height: 768, deviceScaleFactor: 1, mobile: false });
// 모드: reduced = 동작 줄이기 켬, nopref = 해제 강제, 그 외 = 이 PC 기본값
if (process.argv[3] === 'reduced') await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
if (process.argv[3] === 'nopref') await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'no-preference' }] });
const state = (sel) => ev(`(()=>{const t=document.querySelector('${sel}');if(!t)return 'no-track';const cs=getComputedStyle(t);const m=new DOMMatrix(cs.transform);
  const view=t.parentElement; const btn=document.querySelector('#rollPause,.roll-ctl');
  return {anim:cs.animationName,play:cs.animationPlayState,ty:Math.round(m.m42)-Math.round(view.scrollTop),st:Math.round(view.scrollTop),btn:btn?(btn.hidden?'숨김':btn.textContent):'없음',h:t.offsetHeight,reduced:matchMedia('(prefers-reduced-motion: reduce)').matches,
          parentCls:t.closest('section,div.page')?.className.slice(0,40)}})()`);
const out = {};
for (const [name, file] of [['슬라이드', 'AIStory-slide.html'], ['원본형', 'AIStory.html']]) {
  await send('Page.navigate', { url: `${base}/${file}` }); await sleep(2500);
  await ev(`(()=>{const b=[...document.querySelectorAll('button')].find(x=>/직접 넘기기/.test(x.textContent))||[...document.querySelectorAll('button')].find(x=>/이야기 듣기|시작/.test(x.textContent));if(b)b.click();})()`);
  await sleep(1500);
  let sel;
  if (name === '슬라이드') {
    sel = '#credits .roll-track';
    const n = await ev(`typeof N!=='undefined'?N:SCENES.length`);
    await ev(`go(${'${n}'}+1)`.replace('${n}', n));      // 엔딩(N) 다음 = 크레딧
  } else {
    sel = '#roll .roll-track';
    await ev(`document.getElementById('roll').scrollIntoView({block:'start'})`);
  }
  await sleep(1200); const a = await state(sel);
  await sleep(4000); const b = await state(sel);
  let pauseTest = null;
  if (typeof b === 'object' && b.btn === '일시정지') {
    await ev(`document.querySelector('#rollPause,.roll-ctl').click()`);
    const p0 = await state(sel); await sleep(2500); const p1 = await state(sel);       // 멈춰 있어야 한다
    await ev(`document.querySelector('#rollPause,.roll-ctl').click()`);
    await sleep(2500); const p2 = await state(sel);                                    // 다시 움직여야 한다
    pauseTest = { 정지중_이동: p1.st - p0.st, 버튼: p1.btn, 재개후_이동: p2.st - p1.st };
  }
  out[name] = { t0: a, t4s: b, moved: typeof a === 'object' && typeof b === 'object' ? (b.ty - a.ty) : null, pauseTest };
}
console.log(JSON.stringify(out, null, 1));
ws.close(); proc.kill(); try { fs.rmSync(udd, { recursive: true, force: true }); } catch {}

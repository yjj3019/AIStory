// 헤드리스 Chrome 으로 페이지를 띄워 시작 버튼을 누른 뒤 스크린샷과 레이아웃 수치를 낸다.
//   node .agent/shot.mjs http://localhost:8831/AIStory-slide.html out.png [width] [height] [slideIndex]
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const url = process.argv[2], out = process.argv[3];
const W = +(process.argv[4] || 1366), H = +(process.argv[5] || 768), IDX = process.argv[6];
const chrome = ['C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe'].find(p => fs.existsSync(p));
const port = 9400 + Math.floor(Math.random() * 400);
const udd = fs.mkdtempSync(path.join(os.tmpdir(), 'shot-'));
const proc = spawn(chrome, ['--headless=new', '--disable-gpu', '--no-sandbox', '--autoplay-policy=no-user-gesture-required', `--remote-debugging-port=${port}`, `--user-data-dir=${udd}`, `--window-size=${W},${H}`, 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let wsUrl;
for (let i = 0; i < 40 && !wsUrl; i++) { try { const l = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json(); wsUrl = l.find(t => t.type === 'page')?.webSocketDebuggerUrl; } catch {} if (!wsUrl) await sleep(500); }
const ws = new WebSocket(wsUrl); await new Promise(r => ws.addEventListener('open', r));
let id = 0; const pend = new Map();
ws.addEventListener('message', e => { const m = JSON.parse(e.data); if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); } });
const send = (method, params = {}) => new Promise(r => { const i = ++id; pend.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async (expr) => (await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true })).result?.result?.value;
await send('Page.enable'); await send('Runtime.enable');
await send('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url }); await sleep(3000);
// 시작: 재생이 장을 넘기지 않도록 "직접 넘기기" 계열을 우선, 없으면 일반 시작 버튼
await ev(`(()=>{const bs=[...document.querySelectorAll('button')];const b=bs.find(x=>/직접 넘기기/.test(x.textContent))||bs.find(x=>/이야기 듣기|들으며 시작|시작/.test(x.textContent));if(b)b.click();})()`);
await sleep(2500);
if (IDX) { await ev(`(()=>{try{go(${+IDX})}catch(e){}})()`); await sleep(1500); }
const metrics = await ev(`(()=>{
  const q=s=>[...document.querySelectorAll(s)];
  const vis=q('.vis, .chapter-visual').filter(e=>e.offsetParent!==null||getComputedStyle(e).display!=='none');
  const over=e=>({cls:e.className.toString().slice(0,40),w:e.clientWidth,h:e.clientHeight,sw:e.scrollWidth,sh:e.scrollHeight});
  const lanes=q('[class*=lane], .pcard, .person, .hero-por').filter(e=>e.getBoundingClientRect().width>0);
  const bad=lanes.map(over).filter(o=>o.sh>o.h+1||o.sw>o.w+1);
  return {vw:innerWidth,vh:innerHeight,docScrollH:document.documentElement.scrollHeight,bodyScrollH:document.body.scrollHeight,
          visOverflow:vis.map(over).filter(o=>o.sh>o.h+1||o.sw>o.w+1).slice(0,6), nLanes:lanes.length, overflowing:bad.slice(0,12)}})()`);
console.log(JSON.stringify(metrics, null, 1));
const shot = await send('Page.captureScreenshot', { format: 'png' });
fs.writeFileSync(out, Buffer.from(shot.result.data, 'base64'));
console.log('저장', out);
ws.close(); proc.kill();
try { fs.rmSync(udd, { recursive: true, force: true }); } catch {}

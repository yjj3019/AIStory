// 슬라이드 전수 레이아웃 검사: 슬라이드 x 인물 칸(강조/펼침 상태) x 해상도 에서 넘침을 측정한다.
//   node .agent/scan_slides.mjs http://localhost:8841/AIStory-slide.html
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const url = process.argv[2];
const SIZES = [[1366, 768], [1920, 1080], [1280, 720]];
const chrome = ['C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe'].find(p => fs.existsSync(p));
const port = 9800 + Math.floor(Math.random() * 150);
const udd = fs.mkdtempSync(path.join(os.tmpdir(), 'scan-'));
const proc = spawn(chrome, ['--headless=new', '--disable-gpu', '--no-sandbox', `--remote-debugging-port=${port}`, `--user-data-dir=${udd}`, 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let wsUrl;
for (let i = 0; i < 40 && !wsUrl; i++) { try { const l = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json(); wsUrl = l.find(t => t.type === 'page')?.webSocketDebuggerUrl; } catch {} if (!wsUrl) await sleep(500); }
const ws = new WebSocket(wsUrl); await new Promise(r => ws.addEventListener('open', r));
let id = 0; const pend = new Map();
ws.addEventListener('message', e => { const m = JSON.parse(e.data); if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); } });
const send = (method, params = {}) => new Promise(r => { const i = ++id; pend.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async (expr) => { const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true }); return r.result?.result?.value ?? r.result?.exceptionDetails?.text; };
await send('Page.enable'); await send('Runtime.enable');

const CHECK = `(async (si, mode) => {
  go(si); await new Promise(r=>setTimeout(r,350));
  const p = pages[si] || document.querySelectorAll('.page')[si];
  const lanes = [...p.querySelectorAll('.lane')];
  const res = { slide: si, lanes: lanes.length, bad: [] };
  const measure = (tag) => {
    // 칸 안 내용이 칸 경계를 실제로 넘어 흐르는가: 칸의 scrollHeight(자손의 넘침 포함) > clientHeight
    lanes.forEach((ln, k) => {
      const r = ln.getBoundingClientRect(); if (!r.height) return;
      if (ln.scrollHeight > ln.clientHeight + 1) res.bad.push({ k, tag, over: ln.scrollHeight - ln.clientHeight, laneH: Math.round(r.height) });
    });
    // 화면 영역 자체가 스크롤되는가
    const vis = p.querySelector('.vis') || p;
    if (vis.scrollHeight > vis.clientHeight + 2) res.bad.push({ tag, visScroll: vis.scrollHeight - vis.clientHeight });
    const pr = p.getBoundingClientRect(), last = lanes[lanes.length-1]?.getBoundingClientRect();
    if (last && last.bottom > innerHeight + 1) res.bad.push({ tag, offscreen: Math.round(last.bottom - innerHeight) });
  };
  measure('기본');
  for (let k = 0; k < lanes.length; k++) {
    lanes.forEach(l => { l.classList.remove('speaking'); l.setAttribute('aria-pressed','false'); });
    p.classList.add('has-speaker');
    if (mode === 'speak') lanes[k].classList.add('speaking'); else lanes[k].setAttribute('aria-pressed','true');
    await new Promise(r=>setTimeout(r,120));
    measure(mode + '#' + k);
  }
  lanes.forEach(l => { l.classList.remove('speaking'); l.setAttribute('aria-pressed','false'); });
  return res;
})`;

const summary = [];
for (const [w, h] of SIZES) {
  await send('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: 1, mobile: false });
  await send('Page.navigate', { url }); await sleep(2800);
  await ev(`(()=>{const b=[...document.querySelectorAll('button')].find(x=>/직접 넘기기/.test(x.textContent))||[...document.querySelectorAll('button')].find(x=>/시작/.test(x.textContent));if(b)b.click();})()`);
  await sleep(1200);
  const n = await ev(`SCENES.length`);
  let badTotal = 0; const rows = [];
  const ONLY=(process.argv[3]||'').split(',').filter(Boolean).map(Number);
  for (let s = 0; s < n; s++) {
    if (ONLY.length && !ONLY.includes(s)) continue;
    for (const mode of ['speak', 'press']) {
      const r = await ev(`${CHECK}(${s}, '${mode}')`);
      if (r && r.bad && r.bad.length) { badTotal += r.bad.length; rows.push(`  슬라이드 ${s + 1} (칸 ${r.lanes}): ${r.bad.slice(0, 4).map(b => JSON.stringify(b)).join(' ')}`); }
    }
  }
  summary.push(`${w}x${h}: 넘침 ${badTotal}건${rows.length ? '\n' + [...new Set(rows)].slice(0, 14).join('\n') : ''}`);
}
console.log(summary.join('\n'));
ws.close(); proc.kill();
try { fs.rmSync(udd, { recursive: true, force: true }); } catch {}

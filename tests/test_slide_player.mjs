// Runs the exact production controller without browser APIs or audio files.
// Usage: node --test tests/test_slide_player.mjs
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const template=fs.readFileSync(new URL('../slide.template.html',import.meta.url),'utf8');
const script=template.match(/<script>([\s\S]*?)<\/script>/)[1];
const core=script.match(/\/\* AUDIO_SESSION_START[\s\S]*?\*\/([\s\S]*?)\/\* AUDIO_SESSION_END \*\//)[1];
const createAudioSession=vm.runInNewContext(`${core};createAudioSession`,{setTimeout,clearTimeout});
class MockAudio extends EventTarget {
  constructor(){super();this.readyState=0;this.currentTime=0;this.duration=12;this.plays=0;this.pauses=0;}
  play(){this.plays++;return this.result||Promise.resolve();}
  pause(){this.pauses++;}
  fire(type){this.dispatchEvent(new Event(type));}
}
function setup(verified=true){
  const audio=[],events=[],progress=[],timers=new Map();let next=0;
  const session=createAudioSession({
    isVerified:()=>verified,
    makeAudio:()=>{const a=new MockAudio();audio.push(a);return a;},
    onState:(...args)=>events.push(args),onProgress:(...args)=>progress.push(args),
    schedule:fn=>{timers.set(++next,fn);return next;},cancel:id=>timers.delete(id)
  });
  return {session,audio,events,progress,timers};
}

test('template JavaScript parses',()=>{new vm.Script(script);});
test('pending audio never creates or starts an Audio object',()=>{
  const s=setup(false);assert.equal(s.session.play('old-scene'),false);
  assert.equal(s.audio.length,0);assert.equal(s.events[0][0],'pending');assert.equal(s.timers.size,0);
});
test('Stop invalidates delayed readiness and completion callbacks',()=>{
  const s=setup();let ended=0;s.session.play('opening',()=>ended++);const a=s.audio[0];
  s.session.stop();a.fire('canplay');a.fire('ended');a.fire('timeupdate');
  assert.equal(a.plays,0);assert.equal(ended,0);assert.equal(s.progress.length,0);assert.equal(s.timers.size,0);
});
test('new navigation excludes old readiness/ended/error events',()=>{
  const s=setup();let oldEnd=0,newEnd=0;
  s.session.play('old',()=>oldEnd++);const old=s.audio[0];
  s.session.play('new',()=>newEnd++);const fresh=s.audio[1];
  old.fire('canplay');old.fire('ended');old.fire('error');fresh.fire('canplay');fresh.fire('ended');
  assert.equal(old.plays,0);assert.equal(fresh.plays,1);assert.equal(oldEnd,0);assert.equal(newEnd,1);
  assert.ok(!s.events.some(([state])=>state==='error'));
});
test('canplay fires repeatedly but starts only once',()=>{
  const s=setup();s.session.play('scene');const a=s.audio[0];a.fire('canplay');a.fire('canplay');
  assert.equal(a.plays,1);assert.equal(s.timers.size,0);
});
test('current play failure stops safely without automatic fallback',async()=>{
  const s=setup();s.session.play('scene');const a=s.audio[0];a.result=Promise.reject(new Error('NotAllowed'));
  a.fire('canplay');await Promise.resolve();
  assert.equal(s.events.at(-1)[0],'error');assert.equal(s.audio.length,1);assert.ok(a.pauses>0);
});
test('a late play rejection cannot cancel a newer clip',async()=>{
  const s=setup();let reject;s.session.play('old');const old=s.audio[0];old.result=new Promise((_,r)=>{reject=r;});old.fire('canplay');
  s.session.play('new');s.audio[1].fire('canplay');reject(new Error('old rejected'));await Promise.resolve();
  assert.equal(s.events.at(-1)[0],'playing');assert.equal(s.events.at(-1)[1],'new');
});
test('late successful play completion is paused after Stop',async()=>{
  const s=setup();let resolve;s.session.play('old');const a=s.audio[0];a.result=new Promise(r=>{resolve=r;});a.fire('canplay');
  s.session.stop();const paused=a.pauses;resolve();await Promise.resolve();assert.ok(a.pauses>paused);
});
test('readiness timeout stops instead of synthesizing speech or advancing',()=>{
  const s=setup();let ended=0;s.session.play('scene',()=>ended++);[...s.timers.values()][0]();
  assert.equal(s.events.at(-1)[0],'error');assert.equal(ended,0);assert.equal(s.timers.size,0);
  s.audio[0].fire('canplay');assert.equal(s.audio[0].plays,0);
});
test('elapsed display comes only from real media timeupdate',()=>{
  const s=setup();s.session.play('scene');const a=s.audio[0];a.fire('canplay');assert.equal(s.progress.length,0);
  a.currentTime=2.4;a.fire('timeupdate');assert.deepEqual(s.progress[0],['scene',2.4,12]);
});
test('template contains no TTS fallback, fake duration, or reduced-motion JS scroll',()=>{
  assert.doesNotMatch(script,/speechSynthesis|SpeechSynthesisUtterance|40\s*\*\s*60|browserSay/);
  assert.doesNotMatch(template,/0:00\s*\/\s*40:00|requestAnimationFrame\(frame\)/);
  assert.match(template,/\.page\.roll\s+\.roll-track\.is-paused\{animation-play-state:paused\}/);
});

test('already-ready verified media starts without waiting for another event',()=>{
  let a;const session=createAudioSession({isVerified:()=>true,makeAudio:()=>{a=new MockAudio();a.readyState=4;return a;}});
  session.play('scene');assert.equal(a.plays,1);session.stop();
});
test('an ended callback can safely begin the next clip exactly once',()=>{
  const s=setup();s.session.play('first',()=>s.session.play('second'));s.audio[0].fire('canplay');s.audio[0].fire('ended');s.audio[0].fire('ended');
  assert.equal(s.audio.length,2);s.audio[1].fire('canplay');assert.equal(s.events.at(-1)[1],'second');
});

// Actual page audio coordinator with DOM stubs: tests state, not layout or focus rendering.
function pageAudio({pending=false}={}){
  const nodes=new Map(),audio=[],timers=new Map();let tid=0;
  const status=Object.fromEntries(['00-opening','part1','01-scene','02-scene','03-ending'].map(id=>[id,{status:pending?'pending':'verified',rendered_seconds:pending?null:12}]));
  const sandbox={
    AUDIO_STATUS:status,NARRATION:{items:[{id:'00-opening',display_text:'opening'}]},
    SCENES:[{part:1,lines:['first']},{part:1,lines:['second']}],SENTS:[[{t:'first'}],[{t:'second'}]],cur:[0,0],
    PART_TEXT:{1:'part'},N:2,
    pageKind:[{t:'part',part:1},{t:'scene',i:0},{t:'scene',i:1},{t:'end'},{t:'credits'}],
    endPage:{querySelector:()=>({textContent:'ending'})},
    $:id=>{if(!nodes.has(id))nodes.set(id,{disabled:false,textContent:''});return nodes.get(id);},
    Audio:class extends MockAudio{constructor(){super();audio.push(this);}},
    setTimeout:fn=>{timers.set(++tid,fn);return tid;},clearTimeout:id=>timers.delete(id),
    setSent:()=>{},pageOfScene:i=>i+1,pageOfPart:()=>0
  };
  const context=vm.createContext(sandbox);
  const production=script.slice(script.indexOf("const AUDIO_DIR='audio/';"),script.indexOf("$('play').onclick="));
  vm.runInContext(`let current=0;function go(i,preserve=false){if(!preserve)stop();current=i;markEngine();}\n${production}`,context);
  const run=code=>vm.runInContext(code,context);
  return {run,audio,nodes,timers};
}

test('pending page disables audio while showing reading status without an Audio object',()=>{
  const p=pageAudio({pending:true});p.run('markEngine();start()');
  assert.equal(p.audio.length,0);assert.equal(p.nodes.get('play').disabled,true);assert.equal(p.nodes.get('introStart').disabled,true);
  assert.equal(p.nodes.get('engine').textContent,'음성 재렌더링 대기');assert.equal(p.nodes.get('timer').textContent,'길이 확인 대기');
});
test('stopping during opening prevents delayed clip and next-page playback',()=>{
  const p=pageAudio();p.run('start();stop()');p.audio[0].fire('canplay');p.audio[0].fire('ended');
  assert.equal(p.audio[0].plays,0);assert.equal(p.audio.length,1);assert.equal(p.run('playing'),false);
});
test('navigation cancels scene advance timer even if the callback already queued',()=>{
  const p=pageAudio();p.run('go(1);start()');p.audio[0].fire('canplay');p.audio[0].fire('ended');
  const callback=[...p.timers.values()].at(-1);assert.equal(typeof callback,'function');
  p.run('go(3)');callback();assert.equal(p.run('current'),3);assert.equal(p.run('playing'),false);
});
test('a stopped opening restarts without skipping its narration',()=>{
  const p=pageAudio();p.run('start();stop();start()');
  assert.equal(p.audio.length,2);assert.ok(p.audio.every(a=>a.src.endsWith('/00-opening.mp3')));
  p.audio[0].fire('canplay');p.audio[1].fire('canplay');assert.equal(p.audio[0].plays,0);assert.equal(p.audio[1].plays,1);
});

class MockNode {
  constructor(){this.attributes={};this.inert=false;this.hidden=false;this.listeners={};this.classes=new Set();this.style={};
    this.classList={contains:x=>this.classes.has(x),add:x=>this.classes.add(x),remove:x=>this.classes.delete(x),toggle:(x,on)=>{if(on??!this.classes.has(x))this.classes.add(x);else this.classes.delete(x);}};
  }
  setAttribute(k,v){this.attributes[k]=v;}
  focus(){this.focused=true;}
  addEventListener(type,fn){this.listeners[type]=fn;}
}
test('script drawer manages background inert state and returns focus on close',()=>{
  const drawer=new MockNode(),trigger=new MockNode(),view=new MockNode(),cap=new MockNode(),sources=new MockNode(),player=new MockNode(),close=new MockNode();
  drawer.querySelector=()=>close;const elements={'.script':drawer,'.btn-script':trigger,'.vis':view,'.cap':cap,'.src-list':sources};
  const page={querySelector:selector=>elements[selector]};let stopped=0;
  const code=script.slice(script.indexOf('function setScriptOpen('),script.indexOf('/* ---------- 내비게이션 ---------- */'));
  const fn=vm.runInNewContext(code+';setScriptOpen',{$:()=>player,stop:()=>stopped++});
  fn(page,true);assert.equal(stopped,1);assert.equal(drawer.inert,false);assert.equal(close.focused,true);
  assert.ok([view,cap,sources,player].every(el=>el.inert));assert.equal(trigger.attributes['aria-expanded'],'true');
  fn(page,false);assert.equal(drawer.inert,true);assert.equal(trigger.focused,true);assert.equal(drawer.attributes['aria-hidden'],'true');
  assert.ok([view,cap,sources,player].every(el=>!el.inert));
});
function credits(reduced){
  const rp=new MockNode(),view=new MockNode(),track=new MockNode(),button=new MockNode(),mq={matches:reduced,addEventListener:()=>{}};
  rp.classList.add('active');rp.querySelector=sel=>({'.roll-view':view,'.roll-track':track,'.roll-ctl':button})[sel];
  const start=script.indexOf('  /* 동작 줄이기는 수동 스크롤.');const end=script.indexOf('\n}\nconst N=',start);
  const code=script.slice(start,end);
  vm.runInNewContext(code,{rp,matchMedia:()=>mq,MutationObserver:class{observe(){}},requestAnimationFrame:()=>{throw new Error('Unexpected automatic JS motion');}});
  return {view,track,button};
}
test('reduced-motion credits remain manual, with no JS auto-scroll fallback',()=>{
  const c=credits(true);assert.equal(c.button.hidden,true);assert.equal(c.view.tabIndex,0);assert.equal(c.view.scrollTop,undefined);
  c.view.listeners.wheel();assert.equal(c.view.scrollTop,undefined);
});
test('normal-motion credits expose a working pause/resume control',()=>{
  const c=credits(false);assert.equal(c.button.hidden,false);assert.equal(c.button.textContent,'일시정지');
  c.button.onclick();assert.equal(c.button.textContent,'계속');assert.equal(c.track.classList.contains('is-paused'),true);
  c.button.onclick();assert.equal(c.button.textContent,'일시정지');assert.equal(c.track.classList.contains('is-paused'),false);
});
function keyboard(){
  let handler;const intro={hidden:true},page={querySelector:()=>null},player={clicks:0,click(){this.clicks++;}},moves=[];
  const start=script.indexOf("document.addEventListener('keydown',e=>{");const end=script.indexOf('\n\ngo(0);',start);
  vm.runInNewContext(script.slice(start,end),{document:{addEventListener:(_,fn)=>handler=fn},$:id=>id==='intro'?intro:player,pages:[page],current:0,go:n=>moves.push(n)});
  const event=(key,match=()=>false)=>({key,target:{closest:match},prevented:false,preventDefault(){this.prevented=true;}});
  return {handler,event,moves,player};
}
test('global navigation leaves input/contenteditable and scroll regions alone',()=>{
  const k=keyboard();const input=k.event('PageDown',selector=>selector.includes('input'));
  k.handler(input);assert.equal(input.prevented,false);assert.equal(k.moves.length,0);
  const scroll=k.event('ArrowRight',selector=>selector.includes('.vis'));k.handler(scroll);assert.equal(k.moves.length,0);
});
test('global PageDown navigation prevents native page scrolling',()=>{
  const k=keyboard(),e=k.event('PageDown');k.handler(e);assert.equal(e.prevented,true);assert.deepEqual(k.moves,[1]);
});
test('space on a focused button does not also invoke global playback',()=>{
  const k=keyboard(),e=k.event(' ',selector=>selector.includes('button'));k.handler(e);assert.equal(k.player.clicks,0);assert.equal(e.prevented,false);
});


test('layout guard keeps dense cards intrinsic and mobile columns in normal flow',()=>{
  const rules=template.match(/\/\* LAYOUT_GUARDS_START \*\/([\s\S]*?)\/\* LAYOUT_GUARDS_END \*\//)[1];
  assert.match(rules,/\.page \.dg \.lane\.speaking\{flex:0 0 auto;min-height:max-content;max-height:none\}/);
  assert.match(rules,/\.page \.dg\.two \.dg-col\{height:auto;min-height:0;justify-content:flex-start\}/);
  assert.match(rules,/\.page \.dg\.two\{display:flex;flex-direction:column;align-items:stretch\}/);
  assert.match(rules,/\.page \.vis\{display:block;overflow:auto;overscroll-behavior:contain;overflow-anchor:none\}/);
});
test('speaker emphasis never dims non-speaking text',()=>{
  assert.doesNotMatch(template,/\.page\.has-speaker[^}]*opacity:\s*\.62/);
  assert.match(template,/\.page\.has-speaker[^}]*opacity:1/);
});
test('transcript scrolling adjusts only its own container',()=>{
  const code=script.match(/\/\* SCROLL_WITHIN_START \*\/([\s\S]*?)\/\* SCROLL_WITHIN_END \*\//)[1];
  const scrollWithin=vm.runInNewContext(`${code};scrollWithin`);
  const container={scrollTop:100,getBoundingClientRect:()=>({top:10,bottom:110})};
  scrollWithin(container,{getBoundingClientRect:()=>({top:-10,bottom:25})});assert.equal(container.scrollTop,80);
  scrollWithin(container,{getBoundingClientRect:()=>({top:95,bottom:145})});assert.equal(container.scrollTop,115);
  scrollWithin(container,{getBoundingClientRect:()=>({top:25,bottom:95})});assert.equal(container.scrollTop,115);
  assert.doesNotMatch(script,/\.scrollIntoView\(/);
});

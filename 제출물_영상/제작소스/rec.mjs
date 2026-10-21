import {chromium} from '/Users/junny_macbook/node_modules/playwright/index.mjs';
import fs from 'fs';
const MODE=process.env.MODE;
const API='http://127.0.0.1:8010/api', APP='http://localhost:3010';
const batch=await (await fetch(API+'/predict/batch-unmatched',{method:'POST',headers:{'content-type':'application/json'},body:'{}'})).json();
const baseX={electrolyte_temp:'25.1',tank_temp:'25',soaking_time_sec:'1804',aging_days:'3',formation_dv:'0.048',cell_weight_mean:'211',cell_weight_std:'2.6',charge_ratio:'112',charge_program_deviation_pct:'-81'};
const seed={tab:MODE==='C'?'batch':'manual',modelName:'AGM70_B1',xValues:baseX,manualResult:null,batchResult:batch,batchScope:'all',batchScopeDate:'',batchScopeModel:'',batchScopeBuyer:'',batchMetric:'y'};
const br=await chromium.launch({executablePath:'/Users/junny_macbook/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
const RD='rec'+MODE;fs.rmSync(RD,{recursive:true,force:true});
const ctx=await br.newContext({viewport:{width:1920,height:1080},recordVideo:{dir:RD,size:{width:1920,height:1080}}});
await ctx.addInitScript(({seed})=>{
  try{ if(!sessionStorage.getItem('__seeded')){sessionStorage.setItem('ax_prediction_session_v1',JSON.stringify(seed));sessionStorage.setItem('__seeded','1');} }catch(e){}
  const css=document.createElement('style');
  css.textContent='nextjs-portal,[data-nextjs-toast],#__next-build-watcher{display:none!important}body{zoom:1.25}';
  const boot=()=>{document.head.appendChild(css);
    const c=document.createElement('div');
    c.style.cssText='position:fixed;left:0;top:0;width:36px;height:36px;z-index:99999;pointer-events:none;transform:translate(-100px,-100px)';
    c.innerHTML='<svg width="36" height="36" viewBox="0 0 24 24"><path d="M3 2l7 18 2.5-7.5L20 10z" fill="#1F3742" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    document.documentElement.appendChild(c);
    window.addEventListener('mousemove',e=>{c.style.transform=`translate(${e.clientX}px,${e.clientY}px)`;},true);
    window.addEventListener('mousedown',e=>{const r=document.createElement('div');r.style.cssText=`position:fixed;left:${e.clientX-30}px;top:${e.clientY-30}px;width:60px;height:60px;border-radius:50%;border:4px solid #0097A9;z-index:99998;pointer-events:none;opacity:.9;transition:transform .5s ease-out,opacity .5s ease-out`;document.documentElement.appendChild(r);requestAnimationFrame(()=>{r.style.transform='scale(1.8)';r.style.opacity='0';});setTimeout(()=>r.remove(),600);},true);
  };
  document.addEventListener('DOMContentLoaded',boot);
},{seed});
const t00=Date.now();
const pg=await ctx.newPage();
const now=()=>(Date.now()-t00)/1000;
const marks=[];const mark=()=>marks.push(+now().toFixed(2));
const sleep=ms=>pg.waitForTimeout(ms);
const move=async(x,y,dur=0.7)=>{await pg.mouse.move(x,y,{steps:Math.max(10,Math.round(dur*45))});};
const sscroll=async(y,ms=900)=>{await pg.evaluate(y=>window.scrollTo({top:y,behavior:'smooth'}),y);await sleep(ms);};
const clickEl=async(loc,dur=0.6)=>{const bb=await loc.boundingBox();await move(bb.x+bb.width/2,bb.y+bb.height/2,dur);await sleep(120);await loc.click();};
const typeInto=async(label,val)=>{const loc=pg.locator('.field',{has:pg.locator(`label:has-text("${label}")`)}).locator('input');await loc.scrollIntoViewIfNeeded();const bb=await loc.boundingBox();await move(bb.x+bb.width/2,bb.y+bb.height/2,0.5);await pg.mouse.down();await pg.mouse.up();await loc.fill('');await loc.pressSequentially(val,{delay:80});};
const nav=async(t)=>{await sscroll(0,500);await clickEl(pg.locator(`a:text-is("${t}")`).first(),0.55);};
const RUN='button:has-text("1단→2단 순차 예측 실행")';
await pg.goto(APP+(MODE==='C'?'/prediction':'/upload'));
await pg.waitForSelector(MODE==='C'?'text=조건 입력 (X)':'text=매칭 성공');await sleep(500);
await pg.mouse.move(960,560);
if(MODE==='A'){
  mark();await sleep(1100);                       // 0 화면으로 보겠습니다
  mark();await sscroll(560,1100);await move(700,640,0.9);await sleep(1300);  // 1 자동 매칭
  mark();await nav('분석 대시보드');await pg.waitForSelector('text=종합 결론',{timeout:20000});await sleep(300);await move(1000,560,0.9);await sleep(1500); // 2 대시보드
  mark();await nav('예측');await pg.waitForSelector('text=조건 입력 (X)',{timeout:10000});await sleep(300);
  await typeInto('전해액온도','30');await sleep(300);await clickEl(pg.locator(RUN),0.6);await pg.waitForSelector('text=예측 판정',{timeout:15000});await sleep(500);await sscroll(420,900);await sleep(1200); // 3
  mark();await sscroll(0,700);await typeInto('셀중량 표준편차','9');await typeInto('충전율','98');await clickEl(pg.locator(RUN),0.5);
  await pg.waitForSelector('text=부적합',{timeout:15000}).catch(()=>{});await sleep(1200);
  const cz=pg.locator('text=원인 인자 (SPEC 미달 시)').first();await cz.scrollIntoViewIfNeeded();
  const cy=await pg.evaluate(()=>window.scrollY);await sscroll(cy+380,1000);await move(1280,560,0.8);await sleep(2600); // 4 원인 인자 목록
  mark();await sleep(300);mark();
}
if(MODE==='B'){
  mark();await sleep(1000);                       // 0 추가로 소개
  mark();await move(600,760,0.8);await pg.locator('input[type=file]').first().setInputFiles('/Users/junny_macbook/무제 폴더/더미 데이터/충전바이어_더미_process.csv');
  await pg.waitForSelector('text=아직 저장되지 않았습니다',{timeout:15000});await sleep(300);await sscroll(330,900);await move(760,640,0.7);await sleep(1000); // 1 미리보기
  mark();await nav('분석 대시보드');await pg.waitForSelector('text=종합 결론',{timeout:20000});await sleep(250);
  await clickEl(pg.locator('button:has-text("1단·2단 분석 실행")').first(),0.6);await sleep(1600);await sscroll(900,900);await sleep(300);await move(1330,640,0.8);await sleep(1500); // 2 분석 한 번+신뢰도 카드
  mark();await nav('상세 분석');await pg.waitForSelector('text=EN CCA 합격률',{timeout:20000});await sleep(600);await move(960,600,0.7);await sscroll(430,1300);await sleep(700); // 3 게이지
  mark();await sscroll(1500,1100);await clickEl(pg.locator('text=원인 보기').first(),0.7);await sleep(500);await sscroll(1760,800);await move(900,760,0.6);await sleep(1700); // 4 원인 3가지
  mark();await sscroll(0,800);await clickEl(pg.locator('button:has-text("형명별")').first(),0.6);await sleep(1200);await clickEl(pg.locator('button:has-text("바이어별")').first(),0.5);await sleep(1000); // 5 형명·바이어
  mark();await sleep(300);mark();
}
if(MODE==='C'){
  mark();await clickEl(pg.locator('button.tab:has-text("시험 전 로트")'),0.6);await sleep(1800);   // 0 탭 열기
  mark();await sscroll(300,1100);await sleep(1300);                                                // 1 결과 보기
  mark();await clickEl(pg.locator('button.period-tab:has-text("형명별")').first(),0.6);await sleep(1500);await clickEl(pg.locator('button.period-tab:has-text("바이어별")').first(),0.5);await sleep(1200); // 2
  mark();await sleep(300);mark();
}
await ctx.close();await br.close();
fs.writeFileSync(`marks${MODE}.json`,JSON.stringify(marks));console.log(MODE,marks);

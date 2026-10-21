import {chromium} from '/Users/junny_macbook/node_modules/playwright/index.mjs';
import fs from 'fs';
const timing=JSON.parse(fs.readFileSync('timing_v8.json','utf8'));
let html=fs.readFileSync('scene.html','utf8').replace('__TIMING__',JSON.stringify(timing));
fs.writeFileSync('scene_built.html',html);
const fps=30, only=process.env.ONLY?process.env.ONLY.split(',').map(Number):null;
const b=await chromium.launch({executablePath:'/Users/junny_macbook/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
const pg=await b.newPage({viewport:{width:1920,height:1080}});
await pg.goto('file://'+process.cwd()+'/scene_built.html');await pg.evaluate(()=>document.fonts.ready);
fs.mkdirSync('frames',{recursive:true});
if(only){for(const t of only){await pg.evaluate(T=>window.setT(T),t);await pg.screenshot({path:`frames/p_${t}.png`});}}
else{const N=Math.ceil(timing.TOT*fps);for(let i=Math.floor((timing.END-1)*fps);i<N;i++){await pg.evaluate(T=>window.setT(T),i/fps);await pg.screenshot({path:`frames/f${String(i).padStart(5,'0')}.jpg`,type:'jpeg',quality:92});}}
await b.close();console.log('done');

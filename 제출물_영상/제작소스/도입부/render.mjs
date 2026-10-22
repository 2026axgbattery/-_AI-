import {chromium} from '/Users/junny_macbook/node_modules/playwright/index.mjs';
import fs from 'fs';
const timing=JSON.parse(fs.readFileSync('timing.json','utf8'));
fs.writeFileSync('scene_built.html',fs.readFileSync('scene.html','utf8').replace('__TIMING__',JSON.stringify(timing)));
const fps=30, only=process.env.ONLY?process.env.ONLY.split(',').map(Number):null;
const b=await chromium.launch({executablePath:'/Users/junny_macbook/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist']});
const pg=await b.newPage({viewport:{width:1920,height:1080}});
pg.on('console',m=>console.log('console:',m.text()));pg.on('pageerror',e=>console.log('ERR',e.message));
await pg.goto('http://127.0.0.1:8765/scene_built.html');await pg.waitForFunction(()=>window.READY===true,null,{timeout:20000});await pg.evaluate(()=>document.fonts.ready);
fs.mkdirSync('frames',{recursive:true});
if(only){for(const t of only){await pg.evaluate(T=>window.setT(T),t);await pg.screenshot({path:`frames/p_${t}.png`});}}
else{const N=Math.ceil(timing.end*fps);for(let i=0;i<N;i++){await pg.evaluate(T=>window.setT(T),i/fps);await pg.screenshot({path:`frames/f${String(i).padStart(5,'0')}.jpg`,type:'jpeg',quality:92});if(i%90==0)console.log(i,'/',N);}}
await b.close();console.log('done');

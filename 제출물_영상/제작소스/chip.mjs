import {chromium} from '/Users/junny_macbook/node_modules/playwright/index.mjs';
const b=await chromium.launch({executablePath:'/Users/junny_macbook/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
const p=await b.newPage();await p.goto('file://'+process.cwd()+'/chip.html');
await p.locator('#c').screenshot({path:'chip.png',omitBackground:true});await b.close();

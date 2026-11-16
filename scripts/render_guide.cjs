// Render the versioned offline manual; all screenshots use synthetic demo data.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'../frontend/node_modules/playwright');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
(async()=>{
  const browser=await chromium.launch({headless:true});
  try {
    const page=await browser.newPage();
    await page.goto(pathToFileURL(path.resolve(__dirname,'../docs/release/使用指南.html')).href);
    await page.evaluate(()=>document.fonts.ready);
    await page.pdf({path:path.resolve(__dirname,'../docs/release/使用指南.pdf'),printBackground:true,preferCSSPageSize:true});
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});

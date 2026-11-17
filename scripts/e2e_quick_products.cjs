// Synthetic, disposable sandbox only. Runs last because it adds product D.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'../frontend/node_modules/playwright');
const path=require('node:path');
const assert=require('node:assert/strict');
const base=process.env.PLANNER_TEST_URL;
let browser,page,sandbox=false;
async function main(){
  browser=await chromium.launch({headless:true});page=await browser.newPage({viewport:{width:1440,height:1150}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base);await page.getByRole('heading',{name:'我的排柜',exact:true}).waitFor();
  const initial=await(await page.request.get(base+'/api/bootstrap')).json();
  assert.equal(initial.products.length,3);assert.ok(initial.products.every(p=>['A','B','C'].includes(p.code)&&p.description.startsWith('TEST ')));sandbox=true;
  async function importOrder(name){
    await page.getByRole('button',{name:'新增订单',exact:true}).click();
    await page.getByLabel('选择Excel文件').setInputFiles(path.join(__dirname,'../.local-data/browser-fixtures/quick-order.xlsx'));
    await page.getByLabel('订单名称',{exact:true}).fill(name);
    await page.getByRole('button',{name:'确认字段并导入',exact:true}).click();
    await page.getByRole('heading',{name:'订单审核',exact:true}).waitFor();
    if(name==='TEST QUICK PRODUCT'){
      const board=page.getByRole('region',{name:'问题分类'});
      await page.getByRole('button',{name:'处理补产品 / 绑定产品',exact:true}).waitFor();
      assert.equal(await page.getByRole('button',{name:'处理确认工厂',exact:true}).count(),0);
      await page.locator('.review-category-board').screenshot({path:path.join(__dirname,'../.local-data/manual-review-tasks.png')});
      await page.getByRole('button',{name:'处理补产品 / 绑定产品',exact:true}).click();
      assert.equal(await page.getByRole('button',{name:'处理这款产品',exact:true}).count(),1,'Two warehouses must produce one product task');
      await page.getByRole('button',{name:'处理这款产品',exact:true}).click();
      await page.getByRole('dialog',{name:'审核订单行'}).getByRole('button',{name:'取消',exact:true}).click();
    }
    await page.getByRole('button',{name:'全部明细',exact:true}).click();
  }
  await importOrder('TEST QUICK PRODUCT');
  // Opening and cancelling the direct quick action must not create an orphan product.
  await page.getByRole('button',{name:'快速补新品',exact:true}).first().click();
  const modal=page.getByRole('dialog',{name:'审核订单行'});
  assert.equal(await modal.getByLabel('新品编码',{exact:true}).inputValue(),'D');
  assert.equal(await modal.getByLabel('新品名称',{exact:true}).inputValue(),'TEST NEW DESK D');
  await modal.getByRole('button',{name:'取消',exact:true}).click();
  assert.equal((await(await page.request.get(base+'/api/bootstrap')).json()).products.length,3);
  await page.getByRole('button',{name:'审核第2行 DCSYD',exact:true}).click();
  await modal.getByLabel('调整后排柜数量',{exact:true}).fill('110');
  await modal.getByLabel('本批次数量',{exact:true}).fill('110');
  await modal.getByRole('button',{name:'快速新增新品',exact:true}).click();
  assert.equal(await modal.getByLabel('调整后排柜数量',{exact:true}).inputValue(),'110');
  await modal.getByLabel('新品编码',{exact:true}).fill('A');
  await modal.getByText('资料库已有相同编码，请核对后选择已有产品。',{exact:true}).waitFor();
  await modal.getByLabel('新品编码',{exact:true}).fill('D');
  await modal.getByLabel('新品工厂',{exact:true}).fill('利泰');
  await modal.getByLabel('新品单件体积',{exact:true}).fill('0.2');
  await modal.getByLabel('新品单件毛重',{exact:true}).fill('20');
  await modal.locator('.quick-product').screenshot({path:path.join(__dirname,'../.local-data/manual-quick-product.png')});
  await modal.getByRole('button',{name:'保存新品及审核结果',exact:true}).click();
  await modal.waitFor({state:'hidden'});
  await page.getByText('全部审核就绪',{exact:true}).waitFor();
  let state=await(await page.request.get(base+'/api/bootstrap')).json();
  assert.equal(state.products.length,4);
  const product=state.products.find(p=>p.code==='D');assert.ok(product);
  const project=state.projects.find(p=>p.name==='TEST QUICK PRODUCT');assert.ok(project);
  let detail=await(await page.request.get(base+'/api/projects/'+project.id)).json();
  assert.equal(detail.issue_count,0);assert.ok(detail.lines.every(l=>l.product_id===product.id));
  assert.equal(detail.lines[0].updated_qty,110);assert.equal(detail.lines[0].batches[0].quantity,110);
  await page.getByRole('button',{name:'进入排柜',exact:true}).click();
  await page.getByRole('button',{name:'生成推荐方案',exact:true}).click();
  await page.waitForFunction(()=>document.querySelectorAll('.container-option').length===2);
  state=await(await page.request.get(base+'/api/bootstrap')).json();
  const plan=state.plans.filter(p=>p.project_id===project.id).at(-1);assert.ok(plan);
  const download=page.waitForEvent('download');await page.getByRole('button',{name:'导出 Excel',exact:true}).click();await download;
  await page.getByRole('button',{name:'我的排柜',exact:true}).click();
  await importOrder('TEST QUICK REUSE');
  await page.getByText('全部审核就绪',{exact:true}).waitFor();
  assert.equal((await(await page.request.get(base+'/api/bootstrap')).json()).products.length,4);
  await page.getByRole('button',{name:'审核第2行 DCSYD',exact:true}).click();
  await modal.getByRole('button',{name:'就地补齐此产品',exact:true}).click();
  await modal.getByLabel('新品单件毛重',{exact:true}).fill('21');
  await modal.getByRole('checkbox',{name:/确认更新资料库/}).check();
  await modal.getByRole('button',{name:'保存资料及审核结果',exact:true}).click();
  await modal.waitFor({state:'hidden'});
  await page.getByText('全部审核就绪',{exact:true}).waitFor();
  state=await(await page.request.get(base+'/api/bootstrap')).json();
  assert.equal(state.products.find(p=>p.id===product.id).weight,'21');
  const old=await(await page.request.get(base+'/api/plans/'+plan.id)).json();
  assert.ok(old.snapshot.atoms.every(a=>a.weight==='20'),'Saved plan snapshots must not change');
  assert.deepEqual(errors,[]);
  await browser.close();console.log('PASS quick products: inline create/cancel → preserve quantity and batches → duplicate warning → atomically create and bind warehouses → solve/export → next import reuses product → inline shared edit preserves saved plan');
}
main().catch(async error=>{console.error(error);if(page&&sandbox){try{await page.screenshot({path:path.join(__dirname,'../.local-data/e2e-failure.png'),fullPage:true});console.error(await page.locator('body').innerText());}catch{}}await browser?.close();process.exitCode=1;});

from copy import deepcopy
from io import BytesIO
import json
import time
from zipfile import ZipFile, ZIP_DEFLATED

import pytest
import xlsxwriter

from container_planner.excel import parse_dates, read_book
from container_planner.service import commit_import, line_issues, snapshot_inputs
from container_planner.store import Conflict, Store


def workbook(sheets):
    out=BytesIO()
    wb=xlsxwriter.Workbook(out)
    for name,rows in sheets.items():
        sh=wb.add_worksheet(name)
        for i,row in enumerate(rows):
            sh.write_row(i,0,row)
    wb.close()
    return out.getvalue()


def upload(client,data,name="example.xlsx"):
    res=client.post('/api/imports/preview',files={"file":(name,data)})
    assert res.status_code==200,res.text
    return res.json()


def commit(client,imp,kind,**kwargs):
    sheet=next(iter(imp['sheets']))
    config={"kind":kind,"sheet":sheet,"mapping":imp['sheets'][sheet]['mapping'],"header_row":1,**kwargs}
    res=client.post('/api/imports/'+imp['id']+'/commit',json=config)
    assert res.status_code==200,res.text
    return res.json()


def setup_order(client):
    cat=workbook({'产品':[['PRODUCT CODE','OEM CODE','Product Description','Barcode NO.','CBM','G.W'],['TEST','OEM1','测试书桌','00123456789',.1,10]]})
    commit(client,upload(client,cat),'catalog')
    factory=workbook({'利泰':[['Product code','OEM Code','Product Description','G.W'],['TEST','OEM1','测试书桌',99]]})
    commit(client,upload(client,factory),'factory')
    order=workbook({'订单':[['Item ID','Item Name','ABC Class','DCSYD','DCBRI','DCVIC','DCFRE','Total','LSD'],['TEST','测试书桌','A',700,0,0,0,None,'2026/12/21']]})
    result=commit(client,upload(client,order),'order')
    return result['project_id']


def wait_job(client,id):
    for _ in range(100):
        job=client.get('/api/jobs/'+id).json()
        if job['status'] in {'completed','failed'}:
            assert job['status']=='completed',job
            return job
        time.sleep(.1)
    pytest.fail('排柜进程未在10秒内完成')


def test_complete_flow_export_snapshots_backup_restore(client,tmp_path):
    project_id=setup_order(client)
    bootstrap=client.get('/api/bootstrap').json()
    assert bootstrap['products'][0]['weight']=='10'
    assert bootstrap['products'][0]['warnings']
    project=client.get('/api/projects/'+project_id).json()
    assert project['issue_count']==0
    job=client.post('/api/projects/'+project_id+'/solve',json={"revision":project['revision'],"seconds":1}).json()
    completed=wait_job(client,job['id'])
    plan=client.get('/api/plans/'+completed['plan_id']).json()
    assert len(plan['containers'])==2
    exported=client.post('/api/plans/'+plan['id']+'/export')
    assert exported.status_code==200,exported.text
    content=client.get('/api/exports/'+exported.json()['id']).content
    path=tmp_path/'output.xlsx'
    path.write_bytes(content)
    book=read_book(path)
    assert set(book)=={'排柜明细','Summary'}
    with ZipFile(BytesIO(content)) as archive:
        xml=archive.read('xl/worksheets/sheet1.xml').decode()
        assert '<f>H' in xml and '<f>SUM(K' in xml
        assert '#REF!' not in xml
    product=bootstrap['products'][0]
    res=client.patch('/api/products/'+product['id'],json={"revision":product['revision'],"weight":"20"})
    assert res.status_code==200
    old=client.get('/api/plans/'+plan['id']).json()
    assert old['snapshot']['atoms'][0]['weight']=='10'
    # A saved manual adjustment creates a new version and keeps the original untouched.
    plan['containers'][0]['locked']=True
    version=client.post('/api/plans/'+plan['id']+'/versions',json={"containers":plan['containers']})
    assert version.status_code==200,version.text
    assert version.json()['parent_id']==plan['id']
    assert not client.get('/api/plans/'+plan['id']).json()['containers'][0]['locked']
    backup=client.get('/api/backup')
    assert backup.status_code==200
    res=client.post('/api/restore',files={'file':('backup.zip',backup.content)})
    assert res.status_code==200,res.text
    assert client.get('/api/plans/'+plan['id']).status_code==200
    # Restore original files along with database references.
    imp=client.get('/api/bootstrap').json()['imports'][0]
    assert client.get('/api/imports/'+imp['id']+'/original').status_code==200


def test_review_blocks_ambiguous_dates_and_catches_stale_write(client):
    project_id=setup_order(client)
    p=client.get('/api/projects/'+project_id).json()
    line=p['lines'][0]
    url=f"/api/projects/{project_id}/lines/{line['id']}"
    change={"revision":p['revision'],"updated_qty":701,"batches":[{"date":"2026-12-21","quantity":700}]}
    updated=client.patch(url,json=change)
    assert updated.status_code==200
    assert updated.json()['issue_count']==1
    assert client.patch(url,json=change).status_code==409
    blocked=client.post(f'/api/projects/{project_id}/solve',json={"revision":updated.json()['revision']})
    assert blocked.status_code==422
    fixed=client.patch(url,json={"revision":updated.json()['revision'],"batches":[{"date":"2026-12-21","quantity":351},{"date":"2026-12-28","quantity":350}]}).json()
    assert fixed['issue_count']==0
    assert fixed['lines'][0]['original_qty']==700


def test_factory_conflicts_not_last_row_wins(client):
    project_id=setup_order(client)
    factory=workbook({'好事达':[['Product code','Product Description'],['TEST','测试书桌']]})
    commit(client,upload(client,factory),'factory')
    p=client.get('/api/bootstrap').json()['products'][0]
    assert not p['factory']
    assert set(p['factory_candidates'])=={'利泰','好事达'}
    assert client.get('/api/projects/'+project_id).json()['issue_count']==1


def test_placeholder_identifiers_never_link_different_products(client):
    order=workbook({'订单':[['Item ID','Item Name','DCSYD','LSD'],['NO SKUS YET','新产品一',10,'2026/12/21'],['NO SKUS YET','新产品二',20,'2026/12/21']]})
    result=commit(client,upload(client,order),'order')
    p=client.get('/api/projects/'+result['project_id']).json()
    assert len(p['lines'])==2
    assert all(l['product_id'] is None for l in p['lines'])


def test_invalid_inputs_and_cross_site_requests(client):
    assert client.post('/api/imports/preview',files={'file':('old.xls',b'bad')}).status_code==422
    assert client.post('/api/imports/preview',files={'file':('bad.xlsx',b'bad')}).status_code==422
    assert client.post('/api/products',json={'description':'x'},headers={'Origin':'https://evil.example'}).status_code==403
    data=BytesIO()
    with ZipFile(data,'w',ZIP_DEFLATED) as z:
        z.writestr('../escape','bad')
    assert client.post('/api/restore',files={'file':('bad.zip',data.getvalue())}).status_code==422


def test_store_transaction_and_restart(store):
    p=store.put('product',{'description':'x'})
    with pytest.raises(Conflict):
        store.put_many([('product',{'description':'y'},p['id'],p['revision'],'change'),
                        ('product',{'description':'z'},p['id'],p['revision'],'stale')])
    assert store.get('product',p['id'])['description']=='x'
    again=Store(store.root)
    assert again.get('product',p['id'])['description']=='x'


def test_dates_keep_year_and_do_not_evenly_split():
    assert parse_dates('2026/12/21、2026/12/28',2027)==['2026-12-21','2026-12-28']
    assert parse_dates('3.8',2027)==['2027-03-08']
    assert parse_dates('2026/13/99',2026)==[]
    assert parse_dates('12/21/2026',2027)==['2026-12-21']
    assert parse_dates('21/12/2026',2027)==['2026-12-21']
    assert parse_dates('03/08/2026',2026)==[]


def test_distinct_skus_with_same_oem_are_not_collapsed(client):
    cat=workbook({'产品':[['PRODUCT CODE','OEM CODE','Product Description','CBM','G.W'],['A','SAME','A产品',.1,10],['B','SAME','B产品',.2,20]]})
    commit(client,upload(client,cat),'catalog')
    products=client.get('/api/bootstrap').json()['products']
    assert len(products)==2
    assert {p['code']:p['cbm'] for p in products}=={'A':'0.1','B':'0.2'}


def test_bulk_binding_uses_both_name_and_code(client):
    setup_order(client)
    product=client.get('/api/bootstrap').json()['products'][0]
    order=workbook({'订单':[['Item ID','Item Name','DCSYD','DCVIC','LSD'],
                           ['NO SKUS YET','新产品一',10,20,'2026/12/21'],
                           ['NO SKUS YET','新产品二',30,0,'2026/12/21']]})
    result=commit(client,upload(client,order),'order')
    p=client.get('/api/projects/'+result['project_id']).json()
    line=p['lines'][0]
    res=client.patch(f"/api/projects/{p['id']}/lines/{line['id']}",json={'revision':p['revision'],'product_id':product['id'],'bind_matching':True})
    assert res.status_code==200
    lines=res.json()['lines']
    assert lines[0]['product_id']==lines[1]['product_id']==product['id']
    assert lines[2]['product_id'] is None


def test_decimal_comma_is_not_silently_a_thousands_separator():
    from container_planner.excel import number
    assert number('1,000.25')=='1000.25'
    assert number('1,5') is None
    assert number('NaN') is None


def test_demo_is_synthetic_reviewable_and_never_overwrites_business_records(client):
    first=client.post('/api/demo')
    assert first.status_code==200,first.text
    p=client.get('/api/projects/'+first.json()['project_id']).json()
    assert p['name'].startswith('【练习】')
    assert len(p['lines'])==3 and p['issue_count']==1
    assert p['lines'][0]['batches']==[]
    assert p['lines'][0]['issues']==['发货批次待分配']
    assert client.post('/api/demo').status_code==422
    assert len(client.get('/api/bootstrap').json()['products'])==3


def test_standard_warehouse_qty_headers_and_blank_confirmation(client):
    data=workbook({'Sheet1':[['Item ID','Item Name','Supplier Code','Supplier Name','Category','Sub Category','Status','ABC Class','DCSYD QTY','DCBRI QTY','DCVIC QTY','DCFRE QTY'],
                           ['A','测试产品','V001','供应商甲','BEDROOM','BEDSIDE','NEW','A',10,None,0,5],
                           ['B','另一产品','V001','供应商甲','BEDROOM','BEDSIDE','CURRENT','B',None,4,0,'待定']]})
    imp=upload(client,data)
    mapping=imp['sheets']['Sheet1']['mapping']
    assert {w:mapping[w] for w in ['DCSYD','DCBRI','DCVIC','DCFRE']}==dict(DCSYD='I',DCBRI='J',DCVIC='K',DCFRE='L')
    assert 'factory' not in mapping and mapping['supplier_name']=='D'
    assert imp['sheets']['Sheet1']['blank_warehouse_quantities']==2
    result=commit(client,imp,'order',blank_quantity_as_zero=True,default_batch_date='2026-11-30')
    p=client.get('/api/projects/'+result['project_id']).json()
    assert len(p['lines'])==4
    assert sorted(l['updated_qty'] for l in p['lines'] if l['updated_qty'] is not None)==[4,5,10]
    assert sum(l['updated_qty'] is None for l in p['lines'])==1 # text must not become zero
    assert all(l['supplier_name']=='供应商甲' and l['date_source']=='导入时人工指定' for l in p['lines'])
    assert p['lines'][0]['batches']==[{'date':'2026-11-30','quantity':10}]
    assert all(l.get('product') is None for l in p['lines']) # supplier does not create a factory/product
    second=commit(client,upload(client,data),'order')
    raw=client.get('/api/projects/'+second['project_id']).json()
    assert len(raw['lines'])==6 # blanks remain audit records without explicit confirmation
    assert all(not l['batches'] for l in raw['lines'])


def test_default_date_does_not_override_existing_or_ambiguous_lsd(client):
    data=workbook({'订单':[['Item ID','Item Name','DCSYD QTY','LSD'],
                         ['A','有日期',10,'2027/1/11'],['B','多日期',20,'2027/1/11、2027/1/18'],['C','无日期',30,None]]})
    result=commit(client,upload(client,data),'order',default_batch_date='2026-11-30')
    lines=client.get('/api/projects/'+result['project_id']).json()['lines']
    assert lines[0]['batches'][0]['date']=='2027-01-11'
    assert lines[1]['batches']==[]
    assert lines[2]['batches'][0]['date']=='2026-11-30'


def test_warehouse_header_variations_keep_original_format_supported():
    from container_planner.excel import suggest
    rows=[{'row':1,'cells':{'A':'Item ID','B':'Item Name','C':'DCSYD\nQTY','D':'DCBRI_QTY','E':'DCVIC','F':'DCFRE QTY.'}}]
    assert suggest(rows)['mapping']=={'code':'A','description':'B','DCSYD':'C','DCBRI':'D','DCVIC':'E','DCFRE':'F'}


def test_confirmed_rules_pending_lsd_adjustments_and_dated_export(client,tmp_path):
    setup_order(client)
    data=workbook({'订单':[['Item ID','Item Name','Status','ABC Class','DCSYD QTY','DCBRI QTY','DCVIC QTY','DCFRE QTY'],
                         ['TEST','测试书桌','NEW','A',49,None,0,0]]})
    result=commit(client,upload(client,data),'order',blank_quantity_as_zero=True,allow_undated=True,auto_adjust=True)
    p=client.get('/api/projects/'+result['project_id']).json()
    assert p['issue_count']==0 and len(p['lines'])==1
    assert p['lines'][0]['updated_qty']==75 and p['lines'][0]['original_qty']==49
    assert p['quantity_warnings'] and p['lines'][0]['quantity_group_updated']==75
    again=client.post(f"/api/projects/{p['id']}/rules",json={'revision':p['revision'],'auto_adjust':True}).json()
    assert again['lines'][0]['updated_qty']==75
    assert client.post(f"/api/projects/{p['id']}/rules",json={'revision':p['revision'],'auto_adjust':True}).status_code==409
    job=client.post(f"/api/projects/{p['id']}/solve",json={'revision':again['revision'],'seconds':1}).json()
    completed=wait_job(client,job['id'])
    plan=client.get('/api/plans/'+completed['plan_id']).json()
    assert plan['containers'][0]['load_class']=='NEW' and plan['containers'][0]['date']==''
    plan['containers'][0]['date']='2026-11-30'
    dated=client.post('/api/plans/'+plan['id']+'/versions',json={'containers':plan['containers']})
    assert dated.status_code==200,dated.text
    exported=client.post('/api/plans/'+dated.json()['id']+'/export')
    assert exported.status_code==200,exported.text
    path=tmp_path/'adjusted.xlsx'
    path.write_bytes(client.get('/api/exports/'+exported.json()['id']).content)
    book=read_book(path)
    assert '数量调整' in book
    assert '2026-11-30' in str(book['Summary'])
    assert '75' in str(book['数量调整']) and '49' in str(book['数量调整'])


def test_pending_lsd_never_hides_explicit_ambiguous_dates():
    line={'updated_qty':100,'original_qty':100,'batches':[],'warehouse':'DCSYD','lsd':'2026/11/20、2026/11/27'}
    assert '发货批次待分配' in line_issues(line,{},True,True)

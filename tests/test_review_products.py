import pytest

from test_import_and_api import setup_order, workbook, upload, commit, wait_job


def new_order(client, rows=None):
    setup_order(client)
    content=workbook({'订单':[['Item ID','Item Name','DCSYD','DCVIC','LSD'],*(rows or [
        ['NEW-D','TEST NEW DESK',100,50,'2026/12/21']])]})
    result=commit(client,upload(client,content),'order')
    return client.get('/api/projects/'+result['project_id']).json()


def product(**extra):
    return {'code':'NEW-D','oem':'','barcode':'','description':'TEST NEW DESK','factory':'利泰','cbm':'.2','weight':'20',**extra}


def save(client,p,**values):
    line=p['lines'][0]
    return client.patch(f"/api/projects/{p['id']}/lines/{line['id']}",json={'revision':p['revision'],'quick_product':product(),**values})


def test_new_product_and_draft_line_saved_atomically_and_reused(client):
    p=new_order(client)
    result=save(client,p,bind_matching=True,updated_qty=110,batches=[{'date':'2026-12-21','quantity':110}])
    assert result.status_code==200,result.text
    saved=result.json()
    a,b=saved['lines']
    assert a['product_id']==b['product_id'] and a['updated_qty']==110 and b['updated_qty']==50
    assert saved['issue_count']==0
    products=client.get('/api/bootstrap').json()['products']
    new=next(v for v in products if v['code']=='NEW-D')
    assert new['cbm']=='0.2' and new['weight']=='20'
    assert len(products)==2
    assert new['sources'][0]['row']==2
    # The next import resolves by the newly saved code without another library edit.
    content=workbook({'订单':[['Item ID','Item Name','DCSYD','LSD'],['NEW-D','TEST NEW DESK',100,'2026/12/21']]})
    imported=commit(client,upload(client,content),'order')
    again=client.get('/api/projects/'+imported['project_id']).json()
    assert again['lines'][0]['product_id']==new['id'] and again['issue_count']==0
    job=client.post(f"/api/projects/{saved['id']}/solve",json={'revision':saved['revision'],'seconds':1}).json()
    plan_id=wait_job(client,job['id'])['plan_id']
    plan=client.get('/api/plans/'+plan_id).json()
    previous_weight=plan['snapshot']['atoms'][0]['weight']
    edit=product(id=new['id'],revision=new['revision'],weight='21',confirm_shared=True)
    response=save(client,saved,product_id=new['id'],quick_product=edit)
    assert response.status_code==200,response.text
    assert response.json()['lines'][0]['product']['weight']=='21'
    assert client.get('/api/plans/'+plan_id).json()['snapshot']['atoms'][0]['weight']==previous_weight=='20'


@pytest.mark.parametrize('field,value',[('factory',''),('cbm',''),('cbm','-1'),('weight','NaN'),('weight','0'),('description',''),('code','NO SKUS YET')])
def test_invalid_quick_product_creates_no_partial_records(client,field,value):
    p=new_order(client)
    count=len(client.get('/api/bootstrap').json()['products'])
    response=save(client,p,quick_product=product(**{field:value}),updated_qty=120)
    assert response.status_code==422,response.text
    assert len(client.get('/api/bootstrap').json()['products'])==count
    assert client.get('/api/projects/'+p['id']).json()==p


def test_stale_order_rolls_back_new_product_and_audit(client):
    p=new_order(client)
    client.patch('/api/projects/'+p['id'],json={'revision':p['revision'],'name':'TEST updated'})
    before=len(client.get('/api/history').json())
    assert save(client,p).status_code==409
    assert len(client.get('/api/bootstrap').json()['products'])==1
    assert len(client.get('/api/history').json())==before


@pytest.mark.parametrize('identity,value',[('code',' test '),('oem',' OEM1 '),('barcode','00123456789')])
def test_duplicate_identity_requires_existing_product(client,identity,value):
    p=new_order(client)
    response=save(client,p,quick_product=product(**{identity:value}))
    assert response.status_code==422 and '已存在' in response.text
    assert len(client.get('/api/bootstrap').json()['products'])==1


def test_shared_edit_requires_confirmation_and_revisions(client):
    identifier=setup_order(client)
    p=client.get('/api/projects/'+identifier).json()
    existing=client.get('/api/bootstrap').json()['products'][0]
    values={**existing,'weight':'30'}
    assert save(client,p,quick_product=values,product_id=existing['id']).status_code==422
    values['confirm_shared']=True
    client.patch('/api/products/'+existing['id'],json={'revision':existing['revision'],'weight':'11'})
    before=client.get('/api/projects/'+identifier).json()
    assert save(client,p,quick_product=values,product_id=existing['id'],updated_qty=710).status_code==409
    assert client.get('/api/projects/'+identifier).json()==before
    assert client.get('/api/bootstrap').json()['products'][0]['weight']=='11'


def test_no_sku_only_binds_warehouses_from_same_original_row(client):
    p=new_order(client,[['NO SKUS YET','TEST SAME NAME',100,50,'2026/12/21'],['NO SKUS YET','TEST SAME NAME',100,50,'2026/12/21']])
    response=save(client,p,quick_product=product(code='',description='TEST SAME NAME'),bind_matching=True)
    assert response.status_code==200,response.text
    lines=response.json()['lines']
    assert lines[0]['product_id']==lines[1]['product_id']
    assert lines[2]['product_id'] is None and lines[3]['product_id'] is None


def test_matching_does_not_replace_existing_binding(client):
    p=new_order(client)
    original=client.get('/api/bootstrap').json()['products'][0]
    # Another warehouse was already explicitly reviewed to use a different product.
    store=client.app.state.store
    raw=store.get('project',p['id']);raw['lines'][1]['product_id']=original['id']
    current=store.put('project',raw,raw['id'],raw['revision'])
    response=save(client,current,bind_matching=True)
    assert response.status_code==200,response.text
    assert response.json()['lines'][1]['product_id']==original['id']


def test_existing_identifier_ambiguity_does_not_block_measurement_completion(client):
    identifier=setup_order(client)
    p=client.get('/api/projects/'+identifier).json()
    existing=client.get('/api/bootstrap').json()['products'][0]
    client.app.state.store.put('product',existing,action='TEST duplicate legacy record')
    values={**existing,'weight':'21','confirm_shared':True}
    response=save(client,p,product_id=existing['id'],quick_product=values)
    assert response.status_code==200,response.text
    assert response.json()['lines'][0]['product']['weight']=='21'
    assert len(client.get('/api/bootstrap').json()['products'])==2

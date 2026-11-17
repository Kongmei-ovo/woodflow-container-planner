from io import BytesIO

import pytest
import xlsxwriter

from container_planner.excel import WAREHOUSES, suggest
from test_import_and_api import upload, commit, workbook


def grouped_order(reverse=False, catalog_first=False):
    buffer = BytesIO()
    with xlsxwriter.Workbook(buffer) as book:
        if catalog_first:
            catalog = book.add_worksheet('产品资料')
            catalog.write_row(0, 0, ['Product code', 'Product Description', 'CBM', 'G.W'])
            catalog.write_row(1, 0, ['SYNTH-A', '练习产品A', .13, 10])
        sheet = book.add_worksheet('订单')
        sheet.merge_range('E1:H1', 'CBM' if reverse else 'Shipment')
        sheet.write('I1', 'TOTAL UNITS')
        sheet.merge_range('J1:M1', 'Order QTY' if reverse else 'CBM')
        sheet.write_row(1, 0, ['Item ID', 'Item Name', 'Sub Category', 'Status', *WAREHOUSES, 'TOTAL UNITS', *WAREHOUSES])
        for row, code, status, quantities, volumes in [
            (2, 'SYNTH-A', 'CURRENT', [65, 115, 50, 20], [9, 15, 7, 3]),
            (3, 'SYNTH-B', 'NEW', [105, 80, 95, 40], [14, 11, 13, 6]),
        ]:
            left, right = (volumes, quantities) if reverse else (quantities, volumes)
            sheet.write_row(row, 0, [code, '练习产品'+code, 'TABLE', status, *left, sum(quantities), *right])
        # Unlabelled totals must not create extra products/order lines.
        sheet.write_row(4, 4, [170, 195, 145, 60, 570, 23.5, 26.2, 20.1, 9.6])
    return buffer.getvalue()


@pytest.mark.parametrize('reverse', [False, True])
def test_group_heading_selects_pieces_and_never_cbm(client, reverse):
    preview = upload(client, grouped_order(reverse))
    data = preview['sheets']['订单']
    columns = ['J','K','L','M'] if reverse else ['E','F','G','H']
    assert {w:data['mapping'][w] for w in WAREHOUSES} == dict(zip(WAREHOUSES, columns))
    assert data['header_row'] == 2 and data['order_ready']
    result = commit(client, preview, 'order', header_row=2, allow_undated=True, auto_adjust=True)
    project = client.get('/api/projects/'+result['project_id']).json()
    assert len(project['lines']) == 8
    assert sum(line['original_qty'] for line in project['lines']) == 570
    assert sum(line['updated_qty'] for line in project['lines']) == 570
    assert {w:sum(l['original_qty'] for l in project['lines'] if l['warehouse']==w) for w in WAREHOUSES} == dict(zip(WAREHOUSES,[170,195,145,60]))


def test_stale_saved_volume_mapping_is_rejected_without_creating_project(client):
    preview = upload(client, grouped_order())
    mapping = {**preview['sheets']['订单']['mapping'], **dict(zip(WAREHOUSES,['J','K','L','M']))}
    result = client.post('/api/imports/'+preview['id']+'/commit', json={
        'kind':'order','sheet':'订单','header_row':2,'mapping':mapping})
    assert result.status_code == 422 and 'CBM体积' in result.text
    assert not client.get('/api/bootstrap').json()['projects']
    assert client.get('/api/imports/'+preview['id']).json()['status'] == 'staged'


def test_product_sheet_error_points_to_order_and_header_preview_recalculates(client):
    preview = upload(client, grouped_order(catalog_first=True))
    assert preview['sheets']['产品资料']['sheet_kind'] == 'catalog'
    assert preview['sheets']['订单']['order_ready']
    result = client.post('/api/imports/'+preview['id']+'/commit', json={
        'kind':'order','sheet':'产品资料','header_row':1,'mapping':preview['sheets']['产品资料']['mapping']})
    assert result.status_code == 422 and '产品资料表' in result.text and '请切换到订单工作表：订单' in result.text
    refreshed = client.get('/api/imports/'+preview['id']+'/sheet',params={'sheet':'订单','header_row':2}).json()
    assert refreshed['mapping']['DCSYD'] == 'E'
    assert refreshed['column_units']['J'] == 'volume' and refreshed['preview'][0]['row'] == 2


def test_unknown_duplicate_warehouse_needs_manual_choice_instead_of_last_wins(client):
    data = workbook({'订单':[['Item ID','Item Name','DCSYD','DCSYD','DCBRI'],['SYNTH-A','练习产品A',125,20,50]]})
    preview = upload(client, data)
    suggested = preview['sheets']['订单']
    assert 'DCSYD' not in suggested['mapping']
    assert suggested['ambiguous_warehouses']['DCSYD'] == ['C','D']
    blocked = client.post('/api/imports/'+preview['id']+'/commit',json={
        'kind':'order','sheet':'订单','mapping':suggested['mapping']})
    assert blocked.status_code == 422 and '重复仓库列' in blocked.text
    result = commit(client, preview, 'order', mapping={**suggested['mapping'],'DCSYD':'C'})
    project = client.get('/api/projects/'+result['project_id']).json()
    assert sum(l['original_qty'] for l in project['lines']) == 175


def test_unmerged_csv_style_group_labels_also_exclude_volumes():
    rows = [{'row':1,'cells':{'C':'Order QTY','E':'CBM'}},
            {'row':2,'cells':{'A':'Item ID','B':'Item Name','C':'DCSYD','D':'DCBRI','E':'DCSYD','F':'DCBRI'}}]
    assert suggest(rows)['mapping']['DCSYD'] == 'C'
    assert suggest(rows)['mapping']['DCBRI'] == 'D'


@pytest.mark.parametrize('invalid', [0, -1, True, '2'])
def test_invalid_header_row_cannot_bypass_column_unit_detection(invalid):
    with pytest.raises(ValueError, match='表头行必须为正整数'):
        suggest([], header_row=invalid)

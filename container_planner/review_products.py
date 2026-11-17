"""Prepare auditable product changes for the same transaction as an order review."""
from .excel import codekey, normalized, number, text
from .service import product_issues, valid_code
from .store import uid


def prepare_product(store, values, line, selected_id):
    if not isinstance(values, dict):
        raise ValueError('新品资料格式无效。')
    identifier = text(values.get('id'))
    previous = store.get('product', identifier) if identifier else None
    if previous:
        if identifier != selected_id:
            raise ValueError('请先选择要补充的产品，再保存。')
        if values.get('revision') is None:
            raise ValueError('缺少产品版本，请重新打开审核窗口。')
        if values.get('confirm_shared') is not True:
            raise ValueError('请确认本次修改会更新资料库，并影响其他使用该产品的订单。')
    product = dict(previous or {'factory_candidates': [], 'conflicts': [], 'sources': [line.get('source', {})]})
    for field in ('code', 'oem', 'barcode', 'description', 'factory'):
        product[field] = text(values.get(field))
        if len(product[field]) > 500:
            raise ValueError('产品字段过长，请控制在500字以内。')
    if not product['description']:
        raise ValueError('请填写新品名称。')
    for field in ('code', 'oem', 'barcode'):
        if product[field] and not valid_code(product[field]):
            raise ValueError('编码未确定时请留空，不要把待定或占位文字作为正式编码。')
    for field in ('cbm', 'weight'):
        product[field] = number(values.get(field))
    problems = product_issues({**product, 'conflicts': []})
    if problems:
        raise ValueError('请补齐产品资料：' + '；'.join(problems))
    # Identical identifiers can refer to an existing product; names alone do not.
    for other in store.list('product'):
        if other['id'] == identifier:
            continue
        for field, title in (('code', '产品编码'), ('oem', 'OEM编码'), ('barcode', '条码')):
            if valid_code(product[field]) and codekey(product[field]) == codekey(other.get(field)):
                raise ValueError(f'{title}已存在：{other.get("code") or other.get("oem") or "无码产品"} · {other.get("description", "")}。请选择已有产品，避免重复新增。')
    product['factory_candidates'] = [product['factory']]
    product['conflicts'] = []
    identifier = identifier or uid()
    action = '订单审核中补齐产品资料' if previous else '订单审核中快速新增产品'
    return ('product', product, identifier, values.get('revision') if previous else None, action)


def same_source_product(left, right):
    if normalized(left.get('description')) != normalized(right.get('description')):
        return False
    if valid_code(left.get('source_code')):
        return codekey(left['source_code']) == codekey(right.get('source_code'))
    # Without a real SKU, only bind warehouses split from the very same source row.
    a, b = left.get('source', {}), right.get('source', {})
    return bool(a.get('import_id') and a.get('sheet') and a.get('row')) and all(a.get(k) == b.get(k) for k in ('import_id', 'sheet', 'row'))

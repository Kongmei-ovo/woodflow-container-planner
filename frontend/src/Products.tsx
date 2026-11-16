import {useMemo,useState} from 'react';
import {Plus, Pencil, Check} from 'lucide-react';
import {api,patch,post,fmt} from './api';
import {Badge,Empty,Modal,Pager,SearchBox} from './shared';
import type {Notice,Product} from './types';

export default function Products({products,refresh,notify,initialSearch=''}:{products:Product[];refresh:()=>Promise<void>;notify:Notice;initialSearch?:string}){
  const [search,setSearch]=useState(initialSearch),[onlyIssues,setOnlyIssues]=useState(false),[factory,setFactory]=useState(''),[page,setPage]=useState(1);
  const [editing,setEditing]=useState<Product|null|undefined>(undefined),[selected,setSelected]=useState<Set<string>>(new Set()),[assign,setAssign]=useState('利泰');
  const [busy,setBusy]=useState(false);
  const filtered=useMemo(()=>products.filter(p=>(!onlyIssues||p.issues?.length)&&(!factory||p.factory===factory)&&[p.code,p.oem,p.description,p.barcode].join(' ').toLowerCase().includes(search.toLowerCase())),[products,search,onlyIssues,factory]);
  const slice=filtered.slice((page-1)*30,page*30);
  const factories=Array.from(new Set(['利泰','续泰','好事达',...products.map(p=>p.factory).filter(Boolean)]));
  function toggle(id:string){setSelected(prev=>{const next=new Set(prev);next.has(id)?next.delete(id):next.add(id);return next;});}
  async function bulk(){setBusy(true);try{await post('/products/assign-factory',{factory:assign,products:products.filter(p=>selected.has(p.id)).map(p=>({id:p.id,revision:p.revision}))});await refresh();setSelected(new Set());notify('已确认所选产品的工厂归属');}catch(e){notify((e as Error).message,true);}finally{setBusy(false);}}
  return <>
    <div className="page-title"><div><span className="eyebrow">PRODUCT LIBRARY</span><h1>产品资料</h1><p>维护每件完整产品的工厂、体积与毛重，作为排柜的统一依据。</p></div><button className="primary" onClick={()=>setEditing(null)}><Plus size={17}/>新增产品</button></div>
    <div className="panel"><div className="toolbar"><SearchBox value={search} onChange={v=>{setSearch(v);setPage(1);}}/><select aria-label="筛选工厂" value={factory} onChange={e=>{setFactory(e.target.value);setPage(1);}}><option value="">全部工厂</option>{factories.map(f=><option key={f}>{f}</option>)}</select><label className="check"><input type="checkbox" checked={onlyIssues} onChange={e=>{setOnlyIssues(e.target.checked);setPage(1);}}/>仅看待完善</label><span className="muted push">{products.length} 款产品</span></div>
    {selected.size>0?<div className="bulk-bar"><strong>已选 {selected.size} 款</strong><select aria-label="批量指定工厂" value={assign} onChange={e=>setAssign(e.target.value)}>{factories.map(f=><option key={f}>{f}</option>)}</select><button disabled={busy} onClick={bulk}><Check size={15}/>确认工厂归属</button><button className="text-button" onClick={()=>setSelected(new Set())}>取消选择</button></div>:null}
    {filtered.length?<><div className="table-scroll"><table><thead><tr><th><input aria-label="选择当前页全部产品" type="checkbox" checked={slice.length>0&&slice.every(p=>selected.has(p.id))} onChange={e=>setSelected(prev=>{const next=new Set(prev);slice.forEach(p=>e.target.checked?next.add(p.id):next.delete(p.id));return next;})}/></th><th>产品编码 / 产品名称</th><th>工厂</th><th>单件体积 m³</th><th>单件毛重 kg</th><th>资料状态</th><th/></tr></thead><tbody>{slice.map(p=><tr key={p.id}><td><input type="checkbox" aria-label={'选择'+p.code} checked={selected.has(p.id)} onChange={()=>toggle(p.id)}/></td><td><span className="code">{p.code||'待建编码'}</span><span className="description">{p.description}</span></td><td>{p.factory||<span className="warn-text">待确认</span>}</td><td className="numeric">{fmt(p.cbm,8)}</td><td className="numeric">{fmt(p.weight,3)}</td><td>{p.issues?.length?<Badge tone="warning">{p.issues.length} 项待完善</Badge>:<Badge tone="success">已就绪</Badge>}</td><td><button className="icon-button" aria-label={'编辑'+p.code} onClick={()=>setEditing(p)}><Pencil size={16}/></button></td></tr>)}</tbody></table></div><Pager page={page} total={filtered.length} onChange={setPage}/></>:<Empty title="没有匹配的产品">导入产品资料，或调整筛选条件。</Empty>}
    </div>{editing!==undefined?<ProductEditor key={editing?.id||'new'} product={editing} factories={factories} close={()=>setEditing(undefined)} saved={async()=>{await refresh();setEditing(undefined);notify('产品资料已保存，历史方案保持原快照');}} notify={notify}/>:null}
  </>;
}

function ProductEditor({product,factories,close,saved,notify}:{product:Product|null;factories:string[];close:()=>void;saved:()=>Promise<void>;notify:Notice}){
  const [form,setForm]=useState({code:product?.code||'',oem:product?.oem||'',barcode:product?.barcode||'',description:product?.description||'',factory:product?.factory||'',cbm:product?.cbm||'',weight:product?.weight||''});
  const [busy,setBusy]=useState(false);
  async function save(e:React.FormEvent){e.preventDefault();setBusy(true);try{if(product)await patch('/products/'+product.id,{...form,revision:product.revision,confirm_conflicts:true});else await post('/products',form);await saved();}catch(e){notify((e as Error).message,true);}finally{setBusy(false);}}
  return <Modal title={product?'审核产品资料':'新增产品'} onClose={close}><form onSubmit={save}><div className="form-grid">{(['code','oem','barcode','description'] as const).map((field,i)=><label key={field} className={field==='description'?'span-2':''}>{['产品编码','OEM编码','条码','产品名称'][i]}<input value={form[field]} required={field==='description'} onChange={e=>setForm({...form,[field]:e.target.value})}/></label>)}<label>工厂<input list="factory-list" value={form.factory} placeholder="选择或填写工厂" onChange={e=>setForm({...form,factory:e.target.value})}/><datalist id="factory-list">{factories.map(f=><option key={f} value={f}/>)}</datalist></label><div/><label>单件体积（m³）<input type="number" min="0.000000000001" step="any" value={form.cbm} onChange={e=>setForm({...form,cbm:e.target.value})}/></label><label>单件毛重（kg）<input type="number" min="0.000000000001" step="any" value={form.weight} onChange={e=>setForm({...form,weight:e.target.value})}/></label></div>
    {product?.factory_candidates?.length?<p className="hint">工厂候选：{product.factory_candidates.join('、')}。保存后以你选择的工厂为准。</p>:null}
    {product?.conflicts?.length?<div className="alert warning">{product.conflicts.join('；')}。请核实后保存，本次保存视为确认。</div>:null}
    {product?.warnings?.length?<details><summary>资料差异说明（{product.warnings.length}）</summary>{product.warnings.map((w,i)=><p className="hint" key={i}>{w}</p>)}</details>:null}
    {product?.sources?.length?<details><summary>查看资料来源</summary>{product.sources.map((s,i)=><p className="hint" key={i}><a href={'/api/imports/'+(s as {import_id?:string}).import_id+'/original'}>{s.file}</a> · {s.sheet} · 第{s.row}行</p>)}</details>:null}
    <div className="modal-actions"><button type="button" onClick={close}>取消</button><button className="primary" disabled={busy}>{busy?'保存中…':'确认并保存'}</button></div></form></Modal>;
}

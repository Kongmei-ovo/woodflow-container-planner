import type {Product} from './types';

export type QuickProduct={id?:string;revision?:number;code:string;oem:string;barcode:string;description:string;factory:string;cbm:string;weight:string;confirm_shared:boolean};
const placeholders=new Set(['NOSKUSYET','SKUNOTCREATED','NONE','N/A','TBC','待定']);
export const codeKey=(value:string)=> (value||'').normalize('NFKC').toUpperCase().replace(/\s/g,'');
export const realCode=(value:string)=>!!codeKey(value)&&!placeholders.has(codeKey(value));
export function quickDefaults(product:Product|undefined,sourceCode:string,description:string):QuickProduct{return {id:product?.id,revision:product?.revision,code:product?product.code:(realCode(sourceCode)?sourceCode:''),oem:product?.oem||'',barcode:product?.barcode||'',description:product?.description||description,factory:product?.factory||'',cbm:product?.cbm||'',weight:product?.weight||'',confirm_shared:false};}

export default function QuickProductFields({form,onChange,products,onUseExisting,onCancel,busy}:{form:QuickProduct;onChange:(next:QuickProduct)=>void;products:Product[];onUseExisting:(id:string)=>void;onCancel:()=>void;busy:boolean}){
  const original=products.find(p=>p.id===form.id);
  const duplicates=products.filter(p=>p.id!==form.id&&(['code','oem','barcode'] as const).some(field=>(!original||codeKey(original[field])!==codeKey(form[field]))&&realCode(form[field])&&codeKey(p[field])===codeKey(form[field])));
  const factories=[...new Set(['利泰','续泰','好事达',...products.map(p=>p.factory).filter(Boolean)])];
  function change(field:keyof QuickProduct,value:string){onChange({...form,[field]:value});}
  return <fieldset className="quick-product" disabled={busy}><legend>{form.id?'就地补齐产品资料':'快速新增新品'}</legend><p className="hint">名称和原编码已带入。只需核实工厂、完整一件产品的总体积与毛重，保存审核时一起存入资料库并绑定订单。</p>
  <div className="quick-product-grid">{(['description','code','factory','cbm','weight'] as const).map(field=><label key={field}>{({description:'新品名称',code:'新品编码（未定可留空）',factory:'新品工厂',cbm:'新品单件体积（m³）',weight:'新品单件毛重（kg）'})[field]}<input aria-label={({description:'新品名称',code:'新品编码',factory:'新品工厂',cbm:'新品单件体积',weight:'新品单件毛重'})[field]} value={form[field]} required={field!=='code'} type={field==='cbm'||field==='weight'?'number':'text'} min={field==='cbm'||field==='weight'?'0.000000000001':undefined} step={field==='cbm'||field==='weight'?'any':undefined} list={field==='factory'?'quick-factories':undefined} onChange={e=>change(field,e.target.value)}/></label>)}<datalist id="quick-factories">{factories.map(f=><option key={f} value={f}/>)}</datalist></div>
  <details><summary>OEM编码 / 条码（可选）</summary><div className="quick-product-grid"><label>新品OEM编码<input value={form.oem} onChange={e=>change('oem',e.target.value)}/></label><label>新品条码<input value={form.barcode} onChange={e=>change('barcode',e.target.value)}/></label></div></details>
  {duplicates.length?<div className="alert warning" role="alert"><strong>资料库已有相同编码，请核对后选择已有产品。</strong>{duplicates.slice(0,5).map(p=><div key={p.id}><span>{p.code||p.oem} · {p.description} · {p.factory||'工厂待确认'}</span><button type="button" onClick={()=>onUseExisting(p.id)}>使用此产品</button></div>)}</div>:null}
  {form.id?<label className="check"><input type="checkbox" required checked={form.confirm_shared} onChange={e=>onChange({...form,confirm_shared:e.target.checked})}/>确认更新资料库：其他使用此产品的订单会重新检查，已保存方案保持原快照。</label>:null}
  <p className="hint">这里填写全部包装合计的毛重，不是净重；暂时不知道体积或毛重时，先取消补充，保留待审核状态。</p><button type="button" className="text-button" onClick={onCancel}>取消补充，选择已有产品</button>
  </fieldset>;
}

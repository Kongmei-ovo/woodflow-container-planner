import {useEffect, useRef, type ReactNode} from 'react';
import {ChevronLeft, ChevronRight, Search, X} from 'lucide-react';

export function Modal({title,children,onClose,wide=false}:{title:string;children:ReactNode;onClose:()=>void;wide?:boolean}) {
  const ref=useRef<HTMLDivElement>(null);
  useEffect(()=>{
    const before=document.activeElement as HTMLElement|null;
    const root=ref.current;
    root?.focus();
    function key(e:KeyboardEvent) {
      if(e.key==='Escape')onClose();
      if(e.key==='Tab' && root) {
        const nodes=Array.from(root.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]),select:not([disabled]),textarea:not([disabled]),a[href]'));
        const first=nodes[0],last=nodes.at(-1);
        if(e.shiftKey && (document.activeElement===first||document.activeElement===root)){e.preventDefault();last?.focus();}
        else if(!e.shiftKey && document.activeElement===last){e.preventDefault();first?.focus();}
      }
    }
    document.addEventListener('keydown',key);return()=>{document.removeEventListener('keydown',key);before?.focus();};
  },[onClose]);
  return <div className="modal-backdrop"><div ref={ref} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title} className={'modal '+(wide?'wide':'')}>
    <div className="modal-heading"><h2>{title}</h2><button className="icon-button" aria-label="关闭" onClick={onClose}><X size={20}/></button></div>{children}
  </div></div>;
}
export function SearchBox({value,onChange,placeholder='搜索产品编码或名称'}:{value:string;onChange:(v:string)=>void;placeholder?:string}){
  return <label className="search"><Search size={16}/><input aria-label={placeholder} placeholder={placeholder} value={value} onChange={e=>onChange(e.target.value)}/></label>;
}
export function Pager({page,total,size=30,onChange}:{page:number;total:number;size?:number;onChange:(p:number)=>void}){
  const max=Math.max(1,Math.ceil(total/size));
  return <div className="pager"><span>共 {total} 条 · 第 {Math.min(page,max)} / {max} 页</span><div><button className="icon-button" disabled={page<=1} aria-label="上一页" onClick={()=>onChange(page-1)}><ChevronLeft size={17}/></button><button className="icon-button" disabled={page>=max} aria-label="下一页" onClick={()=>onChange(page+1)}><ChevronRight size={17}/></button></div></div>;
}
export function Empty({title,children}:{title:string;children?:ReactNode}){return <div className="empty"><div className="empty-symbol">▦</div><h3>{title}</h3><p>{children}</p></div>;}
export function Badge({children,tone='neutral'}:{children:ReactNode;tone?:string}){return <span className={'badge '+tone}>{children}</span>;}

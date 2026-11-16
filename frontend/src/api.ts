export async function api<T>(path:string, init:RequestInit={}):Promise<T> {
  const res = await fetch('/api'+path, {...init, headers:init.body instanceof FormData ? init.headers : {'Content-Type':'application/json', ...init.headers}});
  if (!res.ok) {
    const error = await res.json().catch(()=>({detail:`请求失败（${res.status}）` }));
    throw new Error(typeof error.detail === 'string' ? error.detail : '输入格式无效，请检查后重试。');
  }
  return res.json();
}
export const post = <T>(path:string,body:unknown={})=>api<T>(path,{method:'POST',body:JSON.stringify(body)});
export const patch = <T>(path:string,body:unknown)=>api<T>(path,{method:'PATCH',body:JSON.stringify(body)});
export function fmt(value:number|string|undefined|null, digits=0) {
  return value == null ? '—' : Number(value).toLocaleString('zh-CN',{maximumFractionDigits:digits});
}
export function dateTime(value:string) {return new Date(value).toLocaleString('zh-CN',{hour12:false});}

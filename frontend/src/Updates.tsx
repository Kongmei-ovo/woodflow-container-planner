import {useCallback,useEffect,useRef,useState} from 'react';
import {Download,ExternalLink,RefreshCw} from 'lucide-react';
import {api,post,fmt} from './api';
import {Modal} from './shared';

type UpdateState={status:string;message:string;current_version:string;latest_version?:string;release_url:string;notes?:string;platform?:string;downloaded:number;total:number};
type Props={open:boolean;onClose:()=>void;version:string;autoCheck:boolean;hasDraft:boolean;onAvailable:(version:string)=>void;onRestarting:(value:boolean)=>void};
export default function Updates({open,onClose,version,autoCheck,hasDraft,onAvailable,onRestarting}:Props){
  const [state,setState]=useState<UpdateState|null>(null),[error,setError]=useState(''),[requesting,setRequesting]=useState(false),[restarting,setRestarting]=useState(false);
  const alive=useRef(true),sequence=useRef(0),started=useRef(false);
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
  const receive=useCallback((value:UpdateState)=>{if(!alive.current)return;setState(value);onAvailable(value.latest_version||'');},[onAvailable]);
  const check=useCallback(async()=>{const id=++sequence.current;setError('');setRequesting(true);try{const next=await post<UpdateState>('/updates/check');if(id===sequence.current)receive(next);}catch(e){if(alive.current)setError((e as Error).message);}finally{if(alive.current&&id===sequence.current)setRequesting(false);}},[receive]);
  useEffect(()=>{if(autoCheck&&!started.current){started.current=true;void check();}},[autoCheck,check]);
  useEffect(()=>{if(open)void check();},[open,check]);
  useEffect(()=>{
    if(!state||!['checking','downloading','verifying'].includes(state.status))return;
    let cancelled=false;
    const timer=setInterval(()=>{void api<UpdateState>('/updates').then(next=>{if(!cancelled)receive(next);}).catch(()=>{});},1000);
    return()=>{cancelled=true;clearInterval(timer);};
  },[state?.status,receive]);
  useEffect(()=>{
    if(!restarting)return;
    let cancelled=false;const deadline=Date.now()+120000;
    const timer=setInterval(()=>{void api<{version:string}>('/health',{signal:AbortSignal.timeout(2000)}).then(health=>{if(!cancelled&&health.version===state?.latest_version)window.location.reload();}).catch(()=>{});if(Date.now()>deadline&&!cancelled)setError('新版切换时间较长。请查看新打开的工作台窗口；若没有打开，可重新双击启动程序。');},1500);
    return()=>{cancelled=true;clearInterval(timer);};
  },[restarting,state?.latest_version]);
  const close=useCallback(()=>{if(!restarting)onClose();},[restarting,onClose]);
  async function download(){if(!state?.latest_version)return;sequence.current++;setRequesting(true);setError('');try{receive(await post<UpdateState>('/updates/install',{version:state.latest_version}));}catch(e){setError((e as Error).message);}finally{if(alive.current)setRequesting(false);}}
  async function restart(){if(hasDraft)return;setRestarting(true);onRestarting(true);setError('');try{await post('/updates/restart');}catch(e){setRestarting(false);onRestarting(false);setError((e as Error).message);}}
  if(!open)return null;
  const working=requesting||!!state&&['checking','downloading','verifying','restarting'].includes(state.status);
  return <Modal title="版本与更新" onClose={close}><div className="update-content"><div className="update-versions"><span>当前版本<strong>{version}</strong></span>{state?.latest_version?<span>可更新版本<strong>{state.latest_version}</strong></span>:null}</div>
    <p role="status">{restarting?'正在自动备份本机资料并切换新版，请稍候…':state?.message||'正在检查更新…'}</p>
    {state?.status==='downloading'?<><progress aria-label="更新包下载进度" max={state.total||1} value={state.downloaded}/><p className="hint">{fmt(state.downloaded/1048576,1)} / {fmt(state.total/1048576,1)} MB</p></>:null}
    {state?.notes?<details className="update-notes"><summary>查看本次更新内容</summary><pre>{state.notes}</pre></details>:null}
    {error?<p className="alert error" role="alert">{error}</p>:null}
    {hasDraft?<p className="alert warning">尚有未保存的排柜调整，请先“另存新版本”，再重启更新。</p>:null}
    <p className="hint">下载期间可关闭此窗口继续工作。新版先在空目录验证启动，重启前自动备份订单与资料。更新成功后，原启动入口会转到已安装的新版。</p>
    <div className="update-actions">{state?.status==='ready'?<button className="primary" disabled={hasDraft||restarting} onClick={()=>void restart()}><RefreshCw size={16}/>{restarting?'正在切换…':'已保存，重启更新'}</button>:state?.latest_version&&state?.platform?<button className="primary" disabled={working||restarting} onClick={()=>void download()}><Download size={16}/>{working?'正在准备…':'下载并准备更新'}</button>:null}<button disabled={working||restarting} onClick={()=>void check()}><RefreshCw size={15}/>重新检查</button><a href={state?.release_url||'https://github.com/Kongmei-ovo/woodflow-container-planner/releases'} target="_blank" rel="noreferrer">前往下载页<ExternalLink size={13}/></a></div>
  </div></Modal>;
}

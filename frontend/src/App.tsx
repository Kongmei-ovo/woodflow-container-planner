import {useCallback,useEffect,useRef,useState} from 'react';
import {Box,Boxes,CheckCircle2,ChevronRight,Database,History as HistoryIcon,Menu,Power,ShieldCheck,X} from 'lucide-react';
import {api,post} from './api';
import type {Bootstrap} from './types';
import {Empty} from './shared';
import Products from './Products';
import Importer from './Importer';
import Review from './Review';
import Workspace from './Workspace';
import History from './History';
import Orders from './Orders';
import Updates from './Updates';

const clientVersion='1.1.0-beta.12';
const pages=[{id:'overview',label:'我的排柜',icon:Boxes},{id:'products',label:'资料设置',icon:Database},{id:'history',label:'历史与备份',icon:HistoryIcon}];
export default function App(){
  const [page,setPage]=useState('overview'),[data,setData]=useState<Bootstrap|null>(null),[error,setError]=useState(''),[message,setMessage]=useState<{text:string;error:boolean}|null>(null),[projectId,setProjectId]=useState(()=>localStorage.getItem('woodflow.project.v1')||''),[planId,setPlanId]=useState(()=>localStorage.getItem('woodflow.plan.v1')||''),[nav,setNav]=useState(false);
  const [stopped,setStopped]=useState(false);
  const [updateOpen,setUpdateOpen]=useState(false),[availableUpdate,setAvailableUpdate]=useState(''),[updating,setUpdating]=useState(false);
  const closeUpdates=useCallback(()=>setUpdateOpen(false),[]);
  const [refreshing,setRefreshing]=useState(false),[retired,setRetired]=useState(false);
  const notify=useCallback((text:string,error=false)=>setMessage({text,error}),[]);
  const currentProject=useRef(projectId),currentPlan=useRef(planId),currentData=useRef<Bootstrap|null>(null),newOrder=useRef(false),refreshSequence=useRef(0);
  const choosePlan=useCallback((id:string)=>{
    const saved=currentData.current?.plans.find(p=>p.id===id);
    if(saved&&saved.project_id!==currentProject.current)return;
    currentPlan.current=id;setPlanId(id);localStorage.setItem('woodflow.plan.v1',id);
  },[]);
  const chooseProject=useCallback((id:string)=>{
    if(id)newOrder.current=false;
    if(currentProject.current!==id){currentPlan.current='';setPlanId('');localStorage.setItem('woodflow.plan.v1','');}
    currentProject.current=id;setProjectId(id);localStorage.setItem('woodflow.project.v1',id);
  },[]);
  const refresh=useCallback(async(preferredProject?:string)=>{
    const sequence=++refreshSequence.current;setRefreshing(true);
    if(preferredProject)chooseProject(preferredProject);
    try{
      const result=await api<Bootstrap>('/bootstrap');
      if(sequence!==refreshSequence.current)return;
      currentData.current=result;setData(result);
      if(!newOrder.current&&!result.projects.some(p=>p.id===currentProject.current))chooseProject(result.projects.at(-1)?.id||'');
      const saved=result.plans.find(p=>p.id===currentPlan.current);
      if(!saved||saved.project_id!==currentProject.current)choosePlan('');
      setError('');
    }catch(e){if(sequence===refreshSequence.current)setError((e as Error).message);throw e;}finally{if(sequence===refreshSequence.current)setRefreshing(false);}
  },[chooseProject,choosePlan]);
  useEffect(()=>{void refresh().catch(()=>{});},[refresh]);
  useEffect(()=>{
    if(stopped||updating||!data)return;
    let cancelled=false,failures=0;
    async function check(){
      try{const health=await api<{version:string}>('/health',{signal:AbortSignal.timeout(3000)});if(cancelled)return;failures=0;setRetired(false);if(health.version!==clientVersion)window.location.reload();}
      catch{if(!cancelled&&++failures>=2)setRetired(true);}
    }
    const timer=setInterval(()=>void check(),5000);
    return()=>{cancelled=true;clearInterval(timer);};
  },[data?.version,stopped,updating]);

  useEffect(()=>{if(!message||message.error)return;const timer=setTimeout(()=>setMessage(null),5000);return()=>clearTimeout(timer);},[message]);
  function openUpdates(){if(document.querySelector('[role=dialog]')){notify('请先保存或关闭当前编辑窗口，再检查更新。',true);return;}setUpdateOpen(true);}
  function go(next:string){
    if(page==='workspace'&&next!==page&&hasDraft&&!window.confirm('尚有未保存的排柜调整，是否放弃这些调整并离开？'))return false;
    if(next==='import'&&page!=='import'){newOrder.current=true;chooseProject('');choosePlan('');}
    if(next==='workspace'&&page==='review')choosePlan('');
    setPage(next);setNav(false);return true;
  }
  function openProject(id:string){chooseProject(id);go('review');}
  function openPlan(id:string){const p=currentData.current?.plans.find(p=>p.id===id);if(!p)return;chooseProject(p.project_id);choosePlan(id);go('workspace');}
  const [hasDraft,setHasDraft]=useState(false);
  const [demoBusy,setDemoBusy]=useState(false);
  async function loadDemo(){setDemoBusy(true);try{const result=await post<{project_id:string}>('/demo');await refresh();openProject(result.project_id);}catch(e){notify((e as Error).message,true);}finally{setDemoBusy(false);}}
  async function exitTool(){if(!window.confirm(hasDraft?'尚有未保存的调整。确定放弃调整并退出本地工具？':'退出后可再次双击启动程序打开工作台。确定退出？'))return;try{await post('/shutdown');setStopped(true);setData(null);}catch(e){notify((e as Error).message,true);}}
  const title=pages.find(p=>p.id===page)?.label||'我的排柜';
  const [settingsImport,setSettingsImport]=useState(false);
  const [productSearch,setProductSearch]=useState('');
  const [returnToOrder,setReturnToOrder]=useState(false);
  const activeProject=data?.projects.find(p=>p.id===projectId);
  const taskPage=['import','review','workspace'].includes(page);
  return <div className="app-shell"><aside className={'sidebar '+(nav?'mobile-open':'')}><a className="brand" href="#" onClick={e=>{e.preventDefault();go('overview');}}><span className="brand-mark"><Box size={25}/></span><span>木序<strong>CONTAINER PLANNER</strong></span></a><div className="sidebar-caption">你的排柜工作空间</div><nav>{pages.map(p=><button key={p.id} className={(page===p.id||(p.id==='overview'&&taskPage))?'active':''} onClick={()=>go(p.id)}><p.icon size={19}/>{p.label}{p.id==='review'&&data?.projects.some(p=>p.issue_count)?<span className="nav-dot"/>:null}</button>)}</nav><div className="sidebar-bottom"><div className="local-indicator"><span/>本地工作模式</div><p>资料保存在本机<br/>Windows / macOS</p><button className="sidebar-version" aria-label="版本与更新" onClick={openUpdates} disabled={stopped}>WOODFLOW · {data?.version||clientVersion}{availableUpdate?' · 有更新':''}</button><button className="quit-button" onClick={exitTool} disabled={stopped}><Power size={13}/>退出工具</button></div></aside>
    <div className="main-shell"><header className="topbar"><button className="icon-button mobile-toggle" aria-label="打开导航" onClick={()=>setNav(!nav)}><Menu size={21}/></button><span>工作空间</span><ChevronRight size={14}/><strong>{title}</strong><div className="topbar-right"><ShieldCheck size={15}/><span>本地存储</span><button className="running-version" aria-label="检查更新" title="点击版本号检查更新" onClick={openUpdates} disabled={stopped}>运行版本 {data?.version||clientVersion}{availableUpdate?' · 可更新':''}</button><span className="topbar-divider"/><span>{new Date().toLocaleDateString('zh-CN',{year:'numeric',month:'long',day:'numeric'})}</span></div></header>
    <main>{error?<div className="alert error">连接失败：{error}<button onClick={()=>void refresh().catch(()=>{})}>重新连接</button></div>:null}
    {stopped?<Empty title="本地工具已退出">再次双击启动程序，即可回到工作台。</Empty>:!data?<Empty title="正在打开你的工作空间…">请确认本地服务已启动。</Empty>:<>
      {taskPage?<section className="task-flow panel"><div className="task-context"><button className="text-button" onClick={()=>go('overview')}>← 返回我的排柜</button><strong>{page==='import'?'新增订单':activeProject?.name||'当前排柜任务'}</strong></div><nav aria-label="当前订单处理步骤">{[{id:'import',label:'导入订单',hint:'上传客户文件'},{id:'review',label:'处理问题',hint:activeProject?.issue_count?`${activeProject.issue_count} 行待确认`:'确认产品、工厂和交期'},{id:'workspace',label:'排柜并导出',hint:'调整后下载Excel'}].map((step,i)=><button key={step.id} aria-current={page===step.id?'step':undefined} className={page===step.id?'current':''} disabled={refreshing|| (step.id==='import'?page!=='import':!activeProject||(step.id==='workspace'&&activeProject.issue_count>0))} onClick={()=>go(step.id)}><span>{i+1}</span><div><strong>{step.label}</strong><small>{step.hint}</small></div></button>)}</nav></section>:null}
      {page==='overview'?<Orders data={data} refresh={refresh} notify={notify} onAdd={()=>go('import')} onReview={openProject} onPlan={openPlan} onSolve={id=>{chooseProject(id);choosePlan('');go('workspace');}} onDemo={loadDemo} demoBusy={demoBusy} onSettings={()=>{setSettingsImport(true);go('products');}}/>:null}
      {page==='import'?<Importer data={data} refresh={refresh} notify={notify} openProject={openProject} orderOnly/>:null}
      {page==='products'?<>{returnToOrder?<div className="alert"><span>正在为当前订单完善基础资料。保存后返回，订单会自动重新检查。</span><button onClick={()=>{setReturnToOrder(false);go('review');}}>返回当前订单 →</button></div>:null}<div className="settings-tabs"><button className={!settingsImport?'primary':''} onClick={()=>setSettingsImport(false)}>查看与修改产品</button><button className={settingsImport?'primary':''} onClick={()=>setSettingsImport(true)}>导入或更新基础资料</button></div>{settingsImport?<Importer data={data} refresh={refresh} notify={notify} openProject={openProject} initialKind="catalog"/>:<Products key={productSearch} initialSearch={productSearch} products={data.products} refresh={refresh} notify={notify}/>}</>:null}
      {page==='review'?<Review onProducts={(code='')=>{setProductSearch(code);setReturnToOrder(true);setSettingsImport(false);go('products');}} projectId={projectId} choose={chooseProject} projects={data.projects} products={data.products} refresh={refresh} notify={notify} onSolve={id=>{chooseProject(id);choosePlan('');go('workspace');}}/>:null}
      {page==='workspace'?<Workspace key={projectId} refreshing={refreshing} data={data} projectId={projectId} planId={planId} choosePlan={choosePlan} chooseProject={chooseProject} refresh={refresh} notify={notify} onDirtyChange={setHasDraft}/>:null}
      {page==='history'?<History data={data} refresh={refresh} notify={notify}/>:null}
    </>}
    <footer className="page-footer"><Box size={13}/>木序 · 智能排柜工作台<span>把数据理清，让装柜有据。</span></footer></main></div>
    {retired&&!stopped?<div className="retired-session" role="alert"><h1>此工作台已停止运行</h1><p>如果刚打开新版，请使用新打开的工作台窗口。重新连接会加载当前运行版本；请勿继续在旧页面编辑。</p><button className="primary" onClick={()=>window.location.reload()}>重新连接当前工作台</button></div>:null}
    {!stopped&&data?<Updates open={updateOpen} onClose={closeUpdates} version={data.version} autoCheck={!!data.update_auto_check} hasDraft={hasDraft} onAvailable={setAvailableUpdate} onRestarting={setUpdating}/>:null}
    {message?<div className={'toast '+(message.error?'error':'')} role={message.error?'alert':'status'}>{message.error?<span>!</span>:<CheckCircle2 size={18}/>}<p>{message.text}</p><button className="icon-button" aria-label="关闭提示" onClick={()=>setMessage(null)}><X size={17}/></button></div>:null}
  </div>;
}

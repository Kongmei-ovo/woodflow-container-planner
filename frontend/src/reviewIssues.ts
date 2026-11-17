import type {Line} from './types';

export type ReviewIssue = {title:string;reason:string;action:string;product:boolean};

// Translate validation messages into the business decision the operator must make.
export function explainIssues(line:Line):ReviewIssue[] {
  const result:ReviewIssue[]=[];
  const missingBatch=line.issues.includes('发货批次待分配');
  const allocated=line.batches.reduce((sum,b)=>sum+(Number(b.quantity)||0),0);
  for(const issue of line.issues){
    if(missingBatch&&issue==='各批次数量之和与排柜数量不符')continue;
    if(issue==='发货批次待分配'){
      const count=line.suggested_dates.length;
      result.push({title:count>1?'多个交期，数量未拆分':'发货日期未确认',reason:count>1?`原订单列出 ${count} 个日期，但没有说明各日期分别发多少件，系统无法确定本行 ${line.updated_qty??'待确认'} 件货应排在哪个批次。`:`本行尚未分配到明确的发货日期，无法确定与哪些订单合柜。`,action:count>1?'填写各日期的发货数量，合计须等于本行排柜数量。':'确认发货日期，并填写本批次数量。',product:false});
    }else if(issue==='产品未绑定'){
      result.push({title:'订单产品尚未对应到产品资料',reason:`客户原编码“${line.source_code||'空白'}”尚未对应到已确认的产品，无法取用其工厂、体积和毛重。`,action:'按产品名称、编码或OEM查找并选择对应产品；没有对应产品时，点击本行“快速补新品”就地创建并绑定。',product:false});
    }else if(issue.includes('工厂')){
      const choices=line.product?.factory_candidates||[];
      result.push({title:choices.length>1?'工厂归属有多个候选':'产品所属工厂未确认',reason:choices.length>1?`资料中有多个工厂候选：${choices.join('、')}。不同工厂不能合柜，必须先确定本款由谁供货。`:'产品资料没有确认的工厂。排柜需要先按工厂隔离，系统不能自行指定。',action:'点击本行“就地补资料”确认工厂，保存后所有使用该产品的订单会重新检查。',product:true});
    }else if(issue==='各批次数量之和与排柜数量不符'){
      result.push({title:'批次数量与排柜数量不一致',reason:`本行排柜数量为 ${line.updated_qty} 件，各批次合计为 ${allocated} 件，相差 ${Math.abs((line.updated_qty??0)-allocated)} 件。`,action:'核对调整后的数量，并修改各批次分配，使两者合计一致。',product:false});
    }else if(issue.includes('单件')||issue.includes('资料冲突')){
      result.push({title:issue,reason:'无法据此可靠计算整柜体积或毛重，可能导致超容或超重。',action:'核实整件完整产品的CBM（m³）和毛重（kg），点击本行“就地补资料”保存确认值。',product:true});
    }else{
      result.push({title:issue,reason:'这一项尚未满足排柜的数据要求，系统暂不能使用该行计算。',action:issue.includes('5或0')?'点击自动凑整，或将本行数量改为5的整数倍，例如50、55。':issue.includes('原始数量')?'对照原文件核实并补录原始数量。':issue.includes('目的仓')?'确认并填写该行目的仓。':issue.includes('日期')?'核实并选择有效的发货日期。':issue.includes('重复批次')?'将相同发货日期的数量合并。':issue.includes('数量')?'核实数量，件数应填写整数；批次数量必须大于零。':'核实并修正对应字段后保存。',product:false});
    }
  }
  return result;
}

import type {Line} from './types';
import {codeKey,realCode} from './QuickProductFields';
export const categories=[
 {key:'产品未绑定',title:'补产品 / 绑定产品',action:'为每款产品选择已有资料，或补齐新品。相同产品的多个仓只处理一次。'},
 {key:'工厂',title:'确认工厂',action:'确认每款产品的供货工厂，避免不同工厂混柜。'},
 {key:'单件',title:'补体积 / 毛重',action:'核实完整一件产品的总体积和毛重，再保存到资料库。'},
 {key:'数量',title:'核对数量',action:'核对原数量、排柜数量和凑整要求，不改动其他仓的数量。'},
 {key:'批次',title:'分配交期',action:'按仓填写各批次发货日期和数量，合计应等于该仓排柜数量。'},
 {key:'其他',title:'其他待确认项',action:'逐项查看原因并补齐目的仓、日期等信息。'}
];
export function categoryFor(issue:string){if(issue==='产品未绑定')return '产品未绑定';if(issue.includes('工厂'))return '工厂';if(issue.includes('单件')||issue.includes('资料冲突'))return '单件';if(issue.includes('批次')||issue.includes('日期'))return '批次';if(issue.includes('数量')||issue.includes('5或0'))return '数量';return '其他';}
export function productKey(line:Line){if(line.product_id)return line.product_id;const name=line.description.normalize('NFKC').trim().toUpperCase().replace(/\s+/g,' ');if(realCode(line.source_code))return codeKey(line.source_code)+'|'+name;if(!line.source.import_id)return line.id;return JSON.stringify([line.source.import_id,line.source.sheet,line.source.row,name]);}
export function taskGroups(lines:Line[],category:string){const groups=new Map<string,Line[]>();for(const line of lines){if(line.excluded||!line.issues.some(i=>categoryFor(i)===category))continue;const key=['产品未绑定','工厂','单件'].includes(category)?productKey(line):line.id;const group=groups.get(key)||[];group.push(line);groups.set(key,group);}return [...groups.values()];}

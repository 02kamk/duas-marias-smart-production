export type Environment='demo'|'real';
export interface Entry{id:string;reference:string;type:'income'|'expense';nature:'operating'|'equipment'|'financing';category:string;description:string;amountCents:number;documentDate:string;dueDate:string;settledDate:string|null;status:'open'|'settled'|'cancelled'}
export interface Policy{openingDate:string;openingBalanceCents:number;historyStartMonth:string|null;historyThroughMonth:string|null;reserveMonths:number;equipmentPercent:number;contingencyPercent:number;scenarioPercent:number}
export interface Ledger{environment:Environment;settings:Policy;entries:Entry[];audit:{id:string;at:string;action:string;reason?:string}[]}
export interface ForecastRow{month:string;invoicedCents:number|null;receiptsCents:number|null;paymentsCents:number|null;scheduledReceiptsCents:number;scheduledPaymentsCents:number;cashCents:number|null;stressCashCents:number|null}
export interface ModelEvaluation{algorithm:string;validationMAECents:Record<string,number>;testMAECents:Record<string,number>;protocol:string;notice:string}
export interface FinanceReport{environment:Environment;asOf:string;health:'green'|'yellow'|'red';healthScope:string;cashCents:number;payable30Cents:number;receivable30Cents:number;overduePayableCents:number;dataOrigin:string;forecastAvailable:boolean;forecast:ForecastRow[];forecastModels:Record<string,ModelEvaluation>;scenarioPercent:number;notice:string;explanations:string[];currentMonthBridge:{scheduledReceiptsCents:number;scheduledPaymentsCents:number};history:{month:string;invoicedCents:number;receiptsCents:number;paymentsCents:number}[];allocation:{reserveTargetCents:number|null;reserveFundedCents:number;reserveGapCents:number;surplusCents:number;budgetBaseCents:number;equipmentCents:number;contingencyCents:number;unallocatedCents:number;blocked:boolean}}
export interface PublicStatus{available:boolean;notice:string;metadata?:{version:string;selectedModel:string;source:string;license:string;attribution:string;originalRows:number;duplicatesRemoved:number;outOfUnitRangeTargets:number;targetRange:number[];features:string[];excludedColumns:string[];partitions:Record<string,{rows:number;firstDate:string;lastDate:string}>;validation:Record<string,{mae:number;rmse:number;r2:number}>;test:Record<string,{mae:number;rmse:number;r2:number}>;selection:string;assumption:string}}
export interface PublicPrediction{value:number;notice:string;algorithm:string;modelVersion:string;unit:string}
export async function request<T>(path:string,body?:unknown,method='POST'):Promise<T>{
 const response=await fetch('/api/business'+path,body===undefined?{}:{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 const data:unknown=await response.json();
 if(!response.ok){const detail=(data as {detail?:unknown}).detail;throw new Error(typeof detail==='string'?detail:'Campos inválidos. Confira valores, datas e preenchimento.');}
 return data as T;
}
export const money=(value:number|null|undefined)=>value==null?'Sem estimativa':(value/100).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
export const decimal=(value:number)=>value.toLocaleString('pt-BR',{maximumFractionDigits:4});
export function inputCents(value:string){const text=value.trim().replace(',','.');if(!/^-?\d+(\.\d{1,2})?$/.test(text))throw new Error('Saldo inicial deve ter até duas casas decimais.');const negative=text.startsWith('-'),parts=text.replace('-','').split('.');return (Number(parts[0])*100+Number((parts[1]||'').padEnd(2,'0')))*(negative?-1:1)}

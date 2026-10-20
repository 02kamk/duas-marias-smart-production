import type {ProductionOrder,ProductionRecord} from '../types';

export function validateProduction(order:ProductionOrder,good:number,rework:number){
 if(order.status==='Concluído')return 'Este lote já está concluído.';
 if(!Number.isSafeInteger(good)||!Number.isSafeInteger(rework)||good<0||rework<0||good+rework===0)return 'Informe quantidades inteiras, não negativas, com pelo menos uma peça.';
 if(order.produced+good>order.quantity)return 'A produção boa excede a quantidade restante do lote. Revise o registro.';
 return null;
}

export function filterRecords(records:ProductionRecord[],orderId:string,employeeId:string){
 return records.filter(r=>(!orderId||r.orderId===orderId)&&(!employeeId||r.employeeId===employeeId));
}

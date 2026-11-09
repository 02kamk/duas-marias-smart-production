export interface Order {id:string;code:string;client:string;model:string;quantity:number;produced:number;dueDate:string;capacityPerDay:number;recentRate:number;reworkRate:number;status:string}
export interface Employee {id:string;name:string;active:boolean;availableMinutes:number;skills:Record<string,{rate:number;quality:number;experience:number}>}
export interface RecordRow {id:string;orderId:string;employeeId:string;operation:string;day:string;goodQuantity:number;reworkQuantity:number}
export interface Decision {id:string;orderId:string;employeeId?:string;operation?:string;minutes?:number;period?:string;decision?:string;reason?:string;at:string}
export interface State {orders:Order[];employees:Employee[];operations:string[];records:RecordRow[];referenceDate:string;notice:string;audit:{at:string;action:string;reason:string}[];assignments:Decision[];decisions:Decision[]}
export interface Analysis {mlAvailable:boolean;ml:null|{riskScore:number;futureRate:number;estimatedDays:number|null};reason?:string;notice:string;generatedAt:string;modelVersion:string;snapshot:{remaining:number;days:number;requiredPerDay:number|null;estimatedDaysAtRecentRate:number|null;baselineLate:boolean;factors:string[]};suggestions:string[]}
export interface Recommendation {eligible:{employeeId:string;name:string;score:number;availableMinutes:number;components:Record<string,number>}[];excluded:{employeeId:string;name:string;reason:string}[];notice:string}
export interface ModelStatus {available:boolean;error?:string;notice:string;metadata?:{version:string;generatedAt:string;seed:number;count:number;sklearnVersion:string;trainCount:number;test:{support:number;lateCount:number;randomForest:{f1:number;recall:number;precision:number};logisticRegression:{f1:number};capacityBaseline:{f1:number};productionMAE:number;productionBaselineMAE:number};notice:string}}
export async function api<T>(path:string,body?:unknown,method='POST'):Promise<T>{
 const response=await fetch('/api/gestao'+path,body===undefined?{}:{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 const data:unknown=await response.json();
 if(!response.ok){const error=data as {detail?:unknown};throw new Error(typeof error.detail==='string'?error.detail:'Dados inválidos. Confira os campos e tente novamente.');}
 return data as T;
}

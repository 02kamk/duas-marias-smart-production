export interface ProductionOrder { id:string; code:string; client:string; model:string; quantity:number; produced:number; dueDate:string; status:'Em andamento'|'Planejado'|'Concluído'; risk:number }
export interface Employee { id:string; name:string; role:string; rate:number; availableMinutes:number }
export interface ProductionRecord { id:string; employeeId:string; orderId:string; operation:string; goodQuantity:number; reworkQuantity:number; time:string }
export interface QualityInspection { id:string; orderId:string; predictedLabel:string; decision:'Pendente'|'Confirmada'|'Rejeitada'; humanLabel:string|null }
export interface AIPrediction { executionMode:'mock'; dataOrigin:'mock'; modelVersion:null; generatedAt:string; label:string; score:number; notice:string }
export interface DashboardMetrics { good:number; rework:number; target:number; attainment:number }

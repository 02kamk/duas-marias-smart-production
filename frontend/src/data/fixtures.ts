import type {ProductionOrder,Employee,ProductionRecord} from '../types';
export const referenceDate='2026-10-19';
export const orders:ProductionOrder[]=[
 {id:'1',code:'OP-001',client:'Cliente A',model:'Camiseta básica',quantity:3000,produced:1950,dueDate:'2026-10-22',status:'Em andamento',risk:81},
 {id:'2',code:'OP-002',client:'Cliente B',model:'Calça de sarja',quantity:1500,produced:1280,dueDate:'2026-10-24',status:'Em andamento',risk:43},
 {id:'3',code:'OP-003',client:'Cliente C',model:'Blusa feminina',quantity:2000,produced:1900,dueDate:'2026-10-25',status:'Em andamento',risk:12},
 {id:'4',code:'OP-004',client:'Cliente A',model:'Camisa social',quantity:1200,produced:420,dueDate:'2026-10-23',status:'Em andamento',risk:58},
 {id:'5',code:'OP-005',client:'Cliente D',model:'Bermuda',quantity:800,produced:400,dueDate:'2026-10-28',status:'Em andamento',risk:22},
 {id:'6',code:'OP-006',client:'Cliente B',model:'Uniforme',quantity:600,produced:0,dueDate:'2026-11-02',status:'Planejado',risk:15},
 {id:'7',code:'OP-007',client:'Cliente C',model:'Saia',quantity:500,produced:500,dueDate:'2026-10-18',status:'Concluído',risk:0},
 {id:'8',code:'OP-008',client:'Cliente D',model:'Vestido',quantity:400,produced:400,dueDate:'2026-10-17',status:'Concluído',risk:0}];
export const employees:Employee[]=['Ana Demo','Bia Demo','Clara Demo','Dora Demo'].map((name,i)=>({id:String(i+1),name,role:'Costura e revisão',rate:40+i*5,availableMinutes:i===3?0:240}));
export const operations=['Gola','Manga','Barra','Costura lateral','Etiqueta','Acabamento','Revisão'];
export const records:ProductionRecord[]=[340,308,300,300].map((goodQuantity,i)=>({id:String(i+1),employeeId:String(i+1),orderId:String(i+1),operation:'Revisão',goodQuantity,reworkQuantity:[12,10,10,12][i],time:`${10+i}:00`}));
export const series=[780,950,1020,890,1150,1190,1248].map((pieces,i)=>({day:`${13+i}/10`,pieces}));

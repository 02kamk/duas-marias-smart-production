import type {AIPrediction,ProductionOrder} from '../types';
const prediction=(label:string,score:number):AIPrediction=>({executionMode:'mock',dataOrigin:'mock',modelVersion:null,generatedAt:new Date().toISOString(),label,score,notice:'Resultado fixo demonstrativo; nenhum modelo foi executado.'});
export const predictDelayMock=(order:ProductionOrder)=>prediction('Score de risco demonstrativo',order.risk);
export const analyzeQualityMock=async()=>{await new Promise(resolve=>setTimeout(resolve,1000));return prediction('Costura torta',87);};
export const recommendWorkerMock=()=>prediction('Recomendação planejada; sem alocação automática',0);

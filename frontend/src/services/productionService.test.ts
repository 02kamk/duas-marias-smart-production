import {describe,expect,it} from 'vitest';
import {orders,records} from '../data/fixtures';
import {filterRecords,validateProduction} from './productionService';
describe('Registro de revisão final',()=>{
 it('recusa negativos, frações, vazio e excesso sem truncar',()=>{
  for(const [good,rework] of [[-1,0],[1.5,0],[0,-1],[0,0],[1051,0]])expect(validateProduction(orders[0],good,rework)).not.toBeNull();
 });
 it('aceita o saldo exato e retrabalho separado',()=>{
  expect(validateProduction(orders[0],1050,20)).toBeNull();
  expect(validateProduction(orders[0],0,20)).toBeNull();
  expect(validateProduction(orders[6],1,0)).not.toBeNull();
 });
 it('combina filtros sem alterar os registros',()=>{
  expect(filterRecords(records,'1','1')).toHaveLength(1);
  expect(filterRecords(records,'1','2')).toHaveLength(0);
  expect(filterRecords(records,'','')).toHaveLength(4);
 });
});

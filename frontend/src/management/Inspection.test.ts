import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {expect,it,vi} from 'vitest';
import {fireEvent,waitFor} from '@testing-library/dom';

it('mostra a classe humana corrigida e limpa a explicação antiga',async()=>{
 document.body.innerHTML='<select id="upload-classe"></select><input id="upload-observacao"><p id="upload-revisao-status"></p><button id="upload-confirmar"></button><button id="upload-corrigir"></button><p id="teste-classe"></p><p id="teste-confianca"></p><div id="teste-ia">Explicação antiga</div>';
 const fetch=vi.fn(async(url:RequestInfo|URL)=>({ok:true,status:200,json:async()=>String(url).includes('taxonomia')?{classes:[{key:'pinched_fabric',nome:'Tecido beliscado'},{key:'crooked_seam',nome:'Costura torta'}]}:{evento:{nome_final:'Costura torta',revisao_humana:{decisao:'corrigida'}}}}));
 vi.stubGlobal('fetch',fetch);
 const source=readFileSync(resolve('../src/pontocerto/app/static/js/operacao.js'),'utf-8');
 new Function(source)();document.dispatchEvent(new Event('DOMContentLoaded'));
 await waitFor(()=>expect(document.querySelectorAll('#upload-classe option').length).toBe(2));
 window.dispatchEvent(new CustomEvent('inspecao-analisada',{detail:{evento_id:'e1',predicao:{classe_key:'pinched_fabric',nome:'Tecido beliscado',confianca:.63}}}));
 fireEvent.change(document.querySelector('#upload-classe')!,{target:{value:'crooked_seam'}});
 fireEvent.click(document.querySelector('#upload-corrigir')!);
 await waitFor(()=>expect(document.querySelector('#teste-classe')?.textContent).toBe('Costura torta'));
 expect(document.querySelector('#teste-confianca')?.textContent).toContain('Sugestão original do modelo: Tecido beliscado');
 expect(document.querySelector('#teste-ia')?.textContent).toBe('');
 vi.unstubAllGlobals();document.body.replaceChildren();
});

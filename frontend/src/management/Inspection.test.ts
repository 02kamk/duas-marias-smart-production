import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {expect,it,vi} from 'vitest';
import {fireEvent,waitFor} from '@testing-library/dom';

const STATIC='../src/pontocerto/app/static';

it('envia a foto, mostra o resultado e salva a correção com um toque na classe certa',async()=>{
 const html=readFileSync(resolve(STATIC+'/index.html'),'utf-8');
 document.body.innerHTML=html.slice(html.indexOf('<body>')+6,html.indexOf('</body>'));
 const evento={id:'e1',classe_key:'pinched_fabric',classe_final:'pinched_fabric',nome:'Tecido beliscado',nome_final:'Tecido beliscado',confianca:.63,precisa_revisao:true,revisao_humana:null,e_falha:true};
 const fetch=vi.fn(async(url:RequestInfo|URL,init?:RequestInit)=>{
  const u=String(url);
  let body:unknown={};
  if(u.includes('/api/taxonomia'))body={classes:[{key:'pinched_fabric',nome:'Tecido beliscado'},{key:'crooked_seam',nome:'Costura torta'}],tecidos:[]};
  else if(u.includes('/api/analisar'))body={evento_id:'e1',evento,imagem:'data:image/png;base64,AA==',heatmap:'data:image/png;base64,AA==',predicao:{classe_key:'pinched_fabric',nome:'Tecido beliscado',confianca:.63,e_falha:true,top:[]}};
  else if(u.includes('/conferencia'))body={ok:true,evento:{...evento,classe_final:'crooked_seam',nome_final:'Costura torta',precisa_revisao:false,revisao_humana:{decisao:'corrigida'}}};
  else if(u.includes('/api/eventos'))body={eventos:[]};
  return {ok:true,status:200,text:async()=>JSON.stringify(body),json:async()=>body};
 });
 vi.stubGlobal('fetch',fetch);
 vi.stubGlobal('matchMedia',()=>({matches:false,addEventListener(){},removeEventListener(){}}));
 new Function(readFileSync(resolve(STATIC+'/js/app.js'),'utf-8'))();
 document.dispatchEvent(new Event('DOMContentLoaded'));
 await waitFor(()=>expect(fetch.mock.calls.some(c=>String(c[0]).includes('taxonomia'))).toBe(true));

 const input=document.querySelector<HTMLInputElement>('#input-arquivo')!;
 Object.defineProperty(input,'files',{value:[new File(['x'],'peca.png',{type:'image/png'})]});
 fireEvent.change(input);
 await waitFor(()=>expect(document.querySelector('#teste-classe')?.textContent).toBe('Tecido beliscado'));
 // Peça incerta: a conferência já vem aberta, com a sugestão da IA marcada.
 expect(document.querySelector('.conferencia-caixa')?.hasAttribute('open')).toBe(true);
 expect(document.querySelector('.classe-opcao.ativo')?.getAttribute('data-classe')).toBe('pinched_fabric');

 fireEvent.click(document.querySelector('.classe-opcao[data-classe="crooked_seam"]')!);
 fireEvent.click(document.querySelector('.conferencia-salvar')!);
 await waitFor(()=>expect(document.querySelector('#teste-classe')?.textContent).toBe('Costura torta'));
 const pedido=fetch.mock.calls.find(c=>String(c[0]).includes('/conferencia'))!;
 expect(JSON.parse(String((pedido[1] as RequestInit).body)).classe).toBe('crooked_seam');
 expect(document.querySelector('#teste-confianca')?.textContent).toContain('Sugestão da IA: Tecido beliscado');
 vi.unstubAllGlobals();document.body.replaceChildren();
});

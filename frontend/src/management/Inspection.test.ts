import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {expect,it,vi} from 'vitest';
import {fireEvent,waitFor} from '@testing-library/dom';

const STATIC='../src/pontocerto/app/static';

it('envia a foto, mostra o resultado e salva a correção escolhendo a classe certa',async()=>{
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
 // Peça incerta: "Está certo" e "Corrigir" à vista; a lista de classes só abre em "Corrigir".
 expect(document.querySelector('.conferencia-certo')).toBeTruthy();
 expect(document.querySelector<HTMLElement>('.conferencia-corrigir-caixa')?.hidden).toBe(true);
 fireEvent.click(document.querySelector('.conferencia-corrigir')!);
 expect(document.querySelector<HTMLElement>('.conferencia-corrigir-caixa')?.hidden).toBe(false);
 expect(document.querySelector('.classe-opcao.ativo')?.getAttribute('data-classe')).toBe('pinched_fabric');

 fireEvent.click(document.querySelector('.classe-opcao[data-classe="crooked_seam"]')!);
 fireEvent.click(document.querySelector('.conferencia-salvar')!);
 await waitFor(()=>expect(document.querySelector('#teste-classe')?.textContent).toBe('Costura torta'));
 const pedido=fetch.mock.calls.find(c=>String(c[0]).includes('/conferencia'))!;
 expect(JSON.parse(String((pedido[1] as RequestInit).body)).classe).toBe('crooked_seam');
 expect(document.querySelector('#teste-confianca')?.textContent).toContain('Sugestão da IA: Tecido beliscado');
 vi.unstubAllGlobals();document.body.replaceChildren();
});

it('confirma a sugestão da IA com um toque em "Está certo"',async()=>{
 const html=readFileSync(resolve(STATIC+'/index.html'),'utf-8');
 document.body.innerHTML=html.slice(html.indexOf('<body>')+6,html.indexOf('</body>'));
 const evento={id:'e2',classe_key:'crooked_seam',classe_final:'crooked_seam',nome:'Costura torta',nome_final:'Costura torta',confianca:.94,precisa_revisao:true,revisao_humana:null,e_falha:true};
 const fetch=vi.fn(async(url:RequestInfo|URL,_init?:RequestInit)=>{
  const u=String(url);
  let body:unknown={};
  if(u.includes('/api/taxonomia'))body={classes:[{key:'pinched_fabric',nome:'Tecido beliscado'},{key:'crooked_seam',nome:'Costura torta'}],tecidos:[]};
  else if(u.includes('/api/analisar'))body={evento_id:'e2',evento,imagem:'data:image/png;base64,AA==',heatmap:null,predicao:{classe_key:'crooked_seam',nome:'Costura torta',confianca:.94,e_falha:true,top:[]}};
  else if(u.includes('/conferencia'))body={ok:true,evento:{...evento,precisa_revisao:false,revisao_humana:{decisao:'confirmada'}}};
  else if(u.includes('/diagnostico'))body={diagnostico:{nome:'Costura torta',resumo:'A carreira fugiu.',acoes:['Reposicione a guia de margem.','Reduza a velocidade.'],causas:['Falta de guia.'],prevencao:[],fonte:'base_local'}};
  else if(u.includes('/api/eventos'))body={eventos:[]};
  return {ok:true,status:200,text:async()=>JSON.stringify(body),json:async()=>body};
 });
 vi.stubGlobal('fetch',fetch);
 vi.stubGlobal('matchMedia',()=>({matches:false,addEventListener(){},removeEventListener(){}}));
 new Function(readFileSync(resolve(STATIC+'/js/app.js'),'utf-8'))();
 document.dispatchEvent(new Event('DOMContentLoaded'));
 await waitFor(()=>expect(fetch.mock.calls.some(c=>String(c[0]).includes('taxonomia'))).toBe(true));
 const input=document.querySelector<HTMLInputElement>('#foto-camera')!;
 Object.defineProperty(input,'files',{value:[new File(['x'],'peca.png',{type:'image/png'})]});
 fireEvent.change(input);
 await waitFor(()=>expect(document.querySelector('#teste-classe')?.textContent).toBe('Costura torta'));
 // A explicação chega resumida: a primeira ação à vista, o resto recolhido.
 await waitFor(()=>expect(document.querySelector('#teste-ia .explicacao-frase')?.textContent).toBe('Reposicione a guia de margem.'));
 expect(document.querySelector('#teste-ia details')?.hasAttribute('open')).toBe(false);
 // "Próxima peça" repete o caminho usado (a câmera do celular).
 expect(document.querySelector('#btn-proxima')?.getAttribute('for')).toBe('foto-camera');
 fireEvent.click(document.querySelector('.conferencia-certo')!);
 await waitFor(()=>expect(document.querySelector('.conferencia-situacao .estado')?.textContent).toBe('Conferida'));
 const pedido=fetch.mock.calls.find(c=>String(c[0]).includes('/conferencia'))!;
 expect(JSON.parse(String((pedido[1] as RequestInit).body)).classe).toBe('crooked_seam');
 vi.unstubAllGlobals();document.body.replaceChildren();
});

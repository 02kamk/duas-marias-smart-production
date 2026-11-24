/* =========================================================================
 * Ponto Certo - interface do operador (JavaScript puro, sem framework)
 * -------------------------------------------------------------------------
 * Organizacao do arquivo:
 *   00. Constantes e estado interno
 *   01. Utilitarios de DOM, texto e rede
 *   02. Toasts
 *   03. Icones SVG inline (nada de emoji como icone principal)
 *   04. Roteamento SPA
 *   05. Bootstrap (taxonomia, saude, dispositivos de camera)
 *   06. Camera
 *   07. Polling de /api/status e render da pagina AO VIVO
 *   08. Painel de IA (diagnostico e segunda opiniao)
 *   09. Pagina TESTAR
 *   10. Pagina HISTORICO (stories, grade e modal)
 *   11. Pagina TREINAMENTO (grafico em Canvas 2D puro)
 *   12. Pagina RELATORIOS (markdown renderizado na mao)
 *   13. Pagina AJUSTES
 *   14. Inicializacao e registro unico de listeners
 *
 * Regras seguidas aqui:
 *   - tudo dentro de uma IIFE: nenhuma variavel global solta;
 *   - todo texto vindo da API passa por escapeHtml antes de virar innerHTML
 *     (a justificativa do LLM e texto livre: nunca confiar nela);
 *   - o DOM so e tocado quando o valor realmente mudou (o polling roda a 5 Hz);
 *   - se um elemento do contrato nao existir, nada quebra (helper $ devolve null).
 * ========================================================================= */

(function () {
  "use strict";

  /* =======================================================================
   * 00. CONSTANTES E ESTADO INTERNO
   * ===================================================================== */

  var PAGINAS = ["inicio", "ao-vivo", "conferir", "historico", "lotes", "relatorios", "perfil"];

  // Situacao do banco (chip da barra superior): consulta lenta, o servidor ja
  // guarda o teste de conexao em cache.
  var INTERVALO_BANCO_MS = 60000;
  var PAGINA_PADRAO = "inicio";

  // Intervalo do polling da pagina ao vivo (5 Hz). Encadeado com setTimeout,
  // nunca setInterval, para que uma resposta lenta nao empilhe requisicoes.
  var INTERVALO_STATUS_MS = 200;
  var INTERVALO_STATUS_OCULTO_MS = 1000;

  // Pixel transparente 1x1: placeholder de <img> para nunca mostrar icone de
  // imagem quebrada enquanto a captura real nao existe.
  var PIXEL_VAZIO =
    "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7";

  // Estado unico da aplicacao. Nada fora daqui.
  var App = {
    pagina: null,
    classes: [],          // taxonomia vinda de /api/taxonomia
    tecidos: [],
    porChave: {},         // classe_key -> {index,key,nome,descricao,gravidade,ok}
    saude: null,
    cameraAtiva: false,
    gradcamLigado: false,
    ultimoEventoId: null,
    eventoAberto: null,
    analiseAtual: null,   // resultado da pagina Testar
    ultimoEvento: null,   // ultimo evento visto pela camera ao vivo
    banco: null,          // ultimo /api/db/status
    lotes: { lista: [], ativo: null },
    poll: { ativo: false, timer: null, abort: null, falhas: 0 },
    cache: {}             // memoria do ultimo valor escrito em cada elemento
  };

  /* =======================================================================
   * 01. UTILITARIOS DE DOM, TEXTO E REDE
   * ===================================================================== */

  /** Busca por id tolerante: o HTML esta sendo escrito em paralelo, entao
   *  qualquer elemento pode ainda nao existir. Devolve null sem reclamar. */
  function $(id) {
    return document.getElementById(id);
  }

  function $$(seletor, raiz) {
    return Array.prototype.slice.call((raiz || document).querySelectorAll(seletor));
  }

  function criar(tag, classe, texto) {
    var el = document.createElement(tag);
    if (classe) el.className = classe;
    if (texto != null) el.textContent = String(texto);
    return el;
  }

  /** Escapa TUDO que vem da API antes de virar innerHTML. */
  function esc(valor) {
    if (valor == null) return "";
    return String(valor)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  /** Escreve texto so quando mudou (evita repaint e piscada a 5 Hz). */
  function setTexto(el, valor) {
    if (!el) return false;
    var novo = valor == null ? "" : String(valor);
    if (el.textContent === novo) return false;
    el.textContent = novo;
    return true;
  }

  /** Igual ao setTexto, porem para innerHTML ja montado e escapado. */
  function setHTML(el, html, chaveCache) {
    if (!el) return false;
    var chave = chaveCache || el.id || null;
    if (chave && App.cache[chave] === html) return false;
    el.innerHTML = html;
    if (chave) App.cache[chave] = html;
    return true;
  }

  function mostrar(el, visivel) {
    if (!el) return;
    // O contrato usa o atributo [hidden]; manipular a propriedade evita
    // brigar com o CSS de quem escreveu o HTML.
    el.hidden = !visivel;
  }

  function habilitar(el, ligado) {
    if (!el) return;
    el.disabled = !ligado;
  }

  function numero(valor, padrao) {
    var n = Number(valor);
    return isFinite(n) ? n : (padrao == null ? 0 : padrao);
  }

  function limitar(valor, minimo, maximo) {
    return Math.min(maximo, Math.max(minimo, valor));
  }

  /** Aceita 0..1 (o normal na API) ou 0..100 e devolve "87%". */
  function formatarPercentual(valor, casas) {
    if (valor == null || valor === "" || isNaN(Number(valor))) return "--";
    var n = Number(valor);
    if (n <= 1.0001) n *= 100;
    return n.toFixed(casas == null ? 0 : casas).replace(".", ",") + "%";
  }

  function formatarNumero(valor, casas) {
    if (valor == null || isNaN(Number(valor))) return "--";
    return Number(valor).toFixed(casas == null ? 3 : casas).replace(".", ",");
  }

  /** Aceita "14:22:03", epoch em segundos ou em milissegundos. */
  function formatarHora(valor) {
    if (valor == null || valor === "") return "--:--";
    if (typeof valor === "string" && !/^\d+(\.\d+)?$/.test(valor)) return valor;
    var n = Number(valor);
    if (!isFinite(n)) return String(valor);
    if (n < 1e11) n = n * 1000; // veio em segundos
    var d = new Date(n);
    if (isNaN(d.getTime())) return "--:--";
    function dois(x) { return x < 10 ? "0" + x : String(x); }
    return dois(d.getHours()) + ":" + dois(d.getMinutes());
  }

  /** "14:22:03" -> "14:22". Segundos não ajudam ninguém na bancada. */
  function horaCurta(ev) {
    var h = (ev && ev.hora) || formatarHora(ev && ev.timestamp);
    return /^\d{2}:\d{2}/.test(h) ? h.slice(0, 5) : h;
  }

  /**
   * fetch com timeout, parse tolerante e mensagem de erro em portugues.
   * Aceita opcoes.sinal para o chamador poder abortar de fora (usado no polling).
   */
  function fetchJSON(url, opcoes) {
    opcoes = opcoes || {};
    var tempoLimite = opcoes.timeout == null ? 15000 : opcoes.timeout;
    var externo = opcoes.sinal || null;
    var init = {};
    for (var k in opcoes) {
      if (!Object.prototype.hasOwnProperty.call(opcoes, k)) continue;
      if (k === "timeout" || k === "sinal") continue;
      init[k] = opcoes[k];
    }
    var ctrl = new AbortController();
    init.signal = ctrl.signal;

    var expirou = false;
    var tid = setTimeout(function () { expirou = true; ctrl.abort(); }, tempoLimite);
    var desligarExterno = null;
    if (externo) {
      if (externo.aborted) ctrl.abort();
      else {
        var aoAbortar = function () { ctrl.abort(); };
        externo.addEventListener("abort", aoAbortar);
        desligarExterno = function () { externo.removeEventListener("abort", aoAbortar); };
      }
    }

    return fetch(url, init)
      .then(function (resp) {
        return resp.text().then(function (texto) {
          var dados = null;
          if (texto) { try { dados = JSON.parse(texto); } catch (e) { dados = null; } }
          if (resp.status === 401) {
            // Sessao expirada: volta ao login em vez de repetir avisos de erro.
            location.assign("/login");
            var sessao = new Error("Sessão encerrada. Entre novamente.");
            sessao.status = 401;
            throw sessao;
          }
          if (!resp.ok) {
            var msg = "HTTP " + resp.status;
            if (dados && typeof dados.erro === "string") msg = dados.erro;
            else if (dados && typeof dados.detail === "string") msg = dados.detail;
            var erro = new Error(msg);
            erro.status = resp.status;
            throw erro;
          }
          if (dados === null) return {};
          return dados;
        });
      })
      .catch(function (e) {
        if (e && e.name === "AbortError") {
          var abortado = new Error(expirou ? "Tempo esgotado ao falar com o servidor." : "Requisição cancelada.");
          abortado.abortada = true;
          abortado.expirou = expirou;
          throw abortado;
        }
        if (e instanceof TypeError) throw new Error("Não foi possível falar com o servidor.");
        throw e;
      })
      .then(
        function (v) { clearTimeout(tid); if (desligarExterno) desligarExterno(); return v; },
        function (e) { clearTimeout(tid); if (desligarExterno) desligarExterno(); throw e; }
      );
  }

  function postJSON(url, corpo, opcoes) {
    opcoes = opcoes || {};
    opcoes.method = "POST";
    opcoes.headers = { "Content-Type": "application/json" };
    opcoes.body = JSON.stringify(corpo || {});
    return fetchJSON(url, opcoes);
  }

  /** Estado "carregando" no proprio botao, preservando o rotulo original. */
  function botaoCarregando(btn, ligado, textoCarregando) {
    if (!btn) return;
    if (ligado) {
      if (btn.dataset.rotuloOriginal == null) btn.dataset.rotuloOriginal = btn.innerHTML;
      btn.disabled = true;
      btn.classList.add("carregando");
      btn.setAttribute("aria-busy", "true");
      btn.innerHTML = '<span class="btn-spin" aria-hidden="true"></span>' +
        esc(textoCarregando || "Consultando...");
    } else {
      btn.disabled = false;
      btn.classList.remove("carregando");
      btn.removeAttribute("aria-busy");
      if (btn.dataset.rotuloOriginal != null) {
        btn.innerHTML = btn.dataset.rotuloOriginal;
        delete btn.dataset.rotuloOriginal;
      }
    }
  }

  function nomeDaClasse(chave) {
    var info = App.porChave[chave];
    if (info && info.nome) return info.nome;
    return chave || "Desconhecida";
  }

  function gravidadeDaClasse(chave) {
    var info = App.porChave[chave];
    return (info && info.gravidade) || "media";
  }

  /* =======================================================================
   * 02. TOASTS
   * ===================================================================== */

  /** tipo: "ok" | "erro" | "aviso" | "info" (o padrao). */
  function toast(mensagem, tipo) {
    var caixa = $("toasts");
    if (!caixa) {
      // Sem container ainda: pelo menos nao perder a informacao.
      if (window.console && console.info) console.info("[toast]", tipo || "info", mensagem);
      return;
    }
    var t = criar("div", "toast toast-" + (tipo || "info"));
    t.setAttribute("role", tipo === "erro" ? "alert" : "status");
    t.innerHTML =
      '<span class="toast-icone" aria-hidden="true">' + iconeToast(tipo) + "</span>" +
      '<span class="toast-texto">' + esc(mensagem) + "</span>";
    caixa.appendChild(t);

    var removido = false;
    function remover() {
      if (removido) return;
      removido = true;
      t.classList.add("saindo");
      setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 220);
    }
    t.addEventListener("click", remover);
    setTimeout(remover, 4000);
  }

  /* =======================================================================
   * 03. ICONES SVG INLINE
   * O briefing proibe emoji como icone; todos os simbolos abaixo sao SVG
   * com currentColor para herdar a cor do CSS.
   * ===================================================================== */

  var SVG_ABRE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">';

  var ICONES = {
    ok: SVG_ABRE + '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.6 2.6L16 9.6"/></svg>',
    falha: SVG_ABRE + '<path d="M10.3 3.9L1.9 18.2A2 2 0 0 0 3.6 21h16.8a2 2 0 0 0 1.7-2.8L13.7 3.9a2 2 0 0 0-3.4 0z"/>' +
      '<path d="M12 9v4.5"/><path d="M12 17.2h.01"/></svg>',
    incerto: SVG_ABRE + '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.2a2.6 2.6 0 1 1 3.4 2.5c-.7.3-1 .9-1 1.6v.4"/>' +
      '<path d="M12 17.3h.01"/></svg>',
    aquecendo: SVG_ABRE + '<circle cx="12" cy="12" r="9"/><path d="M12 7.5V12l3 1.8"/></svg>',
    camera: SVG_ABRE + '<path d="M3 8.5A2.5 2.5 0 0 1 5.5 6h1.7l1.2-2h6.2l1.2 2h1.7A2.5 2.5 0 0 1 20 8.5v8A2.5 2.5 0 0 1 17.5 19h-11A2.5 2.5 0 0 1 4 16.5z"/>' +
      '<circle cx="12" cy="12.5" r="3.2"/></svg>',
    chama: '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" focusable="false">' +
      '<path d="M12.7 2.1c.3 2.6-.7 4-2 5.3-1.5 1.5-3.3 3-3.3 6.1A6.6 6.6 0 0 0 14 20a6.2 6.2 0 0 0 3.9-5.9c0-2.6-1.2-4.2-2.3-5.6-.4.8-1 1.3-1.7 1.6.6-2.6-.2-5.7-1.2-8z"/>' +
      '</svg>',
    ia: SVG_ABRE + '<path d="M12 3l1.7 4.1L18 8.8l-4.3 1.7L12 14.6l-1.7-4.1L6 8.8l4.3-1.7z"/>' +
      '<path d="M17.5 15l.8 1.9 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z"/></svg>',
    livro: SVG_ABRE + '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H19v15H6.5A2.5 2.5 0 0 0 4 20.5z"/><path d="M4 20.5A2.5 2.5 0 0 1 6.5 18H19v3H6.5A2.5 2.5 0 0 1 4 20.5z"/></svg>',
    check: SVG_ABRE + '<path d="M4.5 12.5l5 5 10-11"/></svg>',
    erro: SVG_ABRE + '<circle cx="12" cy="12" r="9"/><path d="M15 9l-6 6M9 9l6 6"/></svg>',
    aviso: SVG_ABRE + '<path d="M12 4l8.5 15H3.5z"/><path d="M12 10v3.6"/><path d="M12 16.6h.01"/></svg>',
    info: SVG_ABRE + '<circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 8h.01"/></svg>'
  };

  function iconeToast(tipo) {
    if (tipo === "ok") return ICONES.check;
    if (tipo === "erro") return ICONES.erro;
    if (tipo === "aviso") return ICONES.aviso;
    return ICONES.info;
  }

  function iconeDoEstado(estado) {
    if (estado === "ok") return ICONES.ok;
    if (estado === "falha") return ICONES.falha;
    if (estado === "incerto") return ICONES.incerto;
    return ICONES.aquecendo;
  }

  /* =======================================================================
   * 04. ROTEAMENTO SPA
   * ===================================================================== */

  function paginaDoHash() {
    var bruto = (location.hash || "").replace(/^#\/?/, "").trim();
    // Ajustes agora é uma aba do Perfil; o endereço antigo continua valendo.
    if (bruto === "ajustes") { App.abaPerfil = "ajustes"; return "perfil"; }
    return PAGINAS.indexOf(bruto) >= 0 ? bruto : PAGINA_PADRAO;
  }

  function irPara(pagina, atualizarHash) {
    // Endereços antigos (#testar, #treinamento) caem na inspeção.
    if (pagina === "testar" || pagina === "treinamento") pagina = "ao-vivo";
    if (pagina === "ajustes") { App.abaPerfil = "ajustes"; pagina = "perfil"; }
    if (PAGINAS.indexOf(pagina) < 0) pagina = PAGINA_PADRAO;
    var anterior = App.pagina;
    if (anterior === pagina) {
      // Mesmo assim garante o hash sincronizado (ex.: clique repetido).
      if (atualizarHash !== false && location.hash !== "#" + pagina) location.hash = "#" + pagina;
      return;
    }
    App.pagina = pagina;

    $$(".pagina").forEach(function (sec) {
      sec.classList.toggle("ativa", sec.id === "pagina-" + pagina);
    });

    // Sidebar e tabbar compartilham .nav-item[data-pagina]; marcamos as duas.
    // Marcamos "ativo" e "ativa" porque o CSS esta sendo escrito em paralelo
    // e pode usar qualquer um dos dois nomes para a pilula do item atual.
    $$(".nav-item[data-pagina]").forEach(function (btn) {
      var atual = btn.getAttribute("data-pagina") === pagina;
      btn.classList.toggle("ativo", atual);
      btn.classList.toggle("ativa", atual);
      if (atual) btn.setAttribute("aria-current", "page");
      else btn.removeAttribute("aria-current");
    });

    if (atualizarHash !== false && location.hash !== "#" + pagina) location.hash = "#" + pagina;

    aoSairDaPagina(anterior);
    aoEntrarNaPagina(pagina);
  }

  function aoSairDaPagina(pagina) {
    if (pagina === "ao-vivo") pararPolling();
  }

  function aoEntrarNaPagina(pagina) {
    if (pagina === "ao-vivo") {
      iniciarPolling();
      carregarLotes();
      carregarRecentes();
    } else if (pagina === "conferir") {
      carregarFila();
    } else if (pagina === "historico") {
      carregarHistorico();
    } else if (pagina === "lotes") {
      carregarPaginaLotes();
    } else if (pagina === "ajustes") {
      carregarAjustes();
      atualizarBanco(false);
    }
    // Início, Relatórios e Perfil ficam em paineis.js.
    if (window.Paineis && typeof window.Paineis[pagina] === "function") window.Paineis[pagina]();
  }

  /* =======================================================================
   * 05. BOOTSTRAP
   * ===================================================================== */

  function carregarTaxonomia() {
    return fetchJSON("/api/taxonomia")
      .then(function (d) {
        App.classes = Array.isArray(d.classes) ? d.classes : [];
        App.tecidos = Array.isArray(d.tecidos) ? d.tecidos : [];
        App.porChave = {};
        App.classes.forEach(function (c) { if (c && c.key) App.porChave[c.key] = c; });
      })
      .catch(function (e) {
        toast("Não foi possível carregar os tipos de defeito: " + e.message, "erro");
      });
  }

  function carregarSaude() {
    return fetchJSON("/api/saude")
      .then(function (d) {
        App.saude = d || {};
        var modelo = (d && d.modelo) || {};
        var llm = (d && d.llm) || {};

        // Online (e com OPENROUTER_API_KEY) quem lê as peças é a IA de visão; o modelo
        // local é só reserva. Só avisa quando não há nenhuma das duas leituras.
        var leitura = (d && d.leitura) || {};
        if (leitura.modo !== "ia" && !modelo.carregado) {
          toast("A leitura das peças está indisponível neste servidor." +
            (leitura.motivo ? " " + leitura.motivo : " Fale com o responsável."), "aviso");
        }
        atualizarChipCamera((d && d.camera) || {});
      })
      .catch(function (e) {
        toast("Servidor indisponível: " + e.message, "erro");
      });
  }

  function carregarDispositivos() {
    var sel = $("sel-camera");
    if (!sel) return Promise.resolve();
    return fetchJSON("/api/camera/dispositivos")
      .then(function (d) {
        var lista = (d && d.dispositivos) || [];
        sel.innerHTML = "";
        mostrar($("bloco-camera"), lista.length > 0);
        if (!lista.length) {
          var vazia = criar("option", null, "Nenhuma câmera encontrada");
          vazia.value = "";
          sel.appendChild(vazia);
          habilitar(sel, false);
          return;
        }
        habilitar(sel, true);
        lista.forEach(function (indice, i) {
          var opt = criar("option", null, "Câmera " + indice);
          opt.value = String(indice);
          if (i === 0) opt.selected = true;
          sel.appendChild(opt);
        });
      })
      .catch(function () {
        sel.innerHTML = "";
        var opt = criar("option", null, "Câmera 0");
        opt.value = "0";
        sel.appendChild(opt);
      });
  }

  /* =======================================================================
   * 06. CAMERA
   * ===================================================================== */

  function atualizarChipCamera(info) {
    var chip = $("chip-camera");
    info = info || {};
    var ativa = !!info.ativa;
    App.cameraAtiva = ativa;

    if (chip) {
      var texto;
      if (info.erro) texto = "Câmera com erro";
      else if (ativa) {
        texto = "Câmera " + (info.indice == null ? "" : info.indice) + " - " +
          (info.largura || "?") + "x" + (info.altura || "?");
        if (info.fps_real) texto += " - " + Number(info.fps_real).toFixed(0) + " fps";
      } else texto = "Câmera desligada";
      setTexto(chip, texto);
      chip.classList.toggle("estado-ok", ativa && !info.erro);
      chip.classList.toggle("estado-defeito", !!info.erro);
      chip.classList.toggle("estado-neutro", !ativa && !info.erro);
      chip.setAttribute("data-estado", info.erro ? "erro" : (ativa ? "ligada" : "desligada"));
    }

    var btn = $("btn-camera");
    if (btn) {
      btn.setAttribute("aria-pressed", ativa ? "true" : "false");
      btn.classList.toggle("ligado", ativa);
      var rotulo = btn.querySelector(".btn-rotulo");
      if (rotulo) setTexto(rotulo, ativa ? "Parar câmera" : "Ligar câmera");
      else if (!btn.querySelector("svg")) setTexto(btn, ativa ? "Parar câmera" : "Ligar câmera");
      btn.setAttribute("aria-label", ativa ? "Parar a câmera" : "Ligar a câmera");
    }

    mostrar($("video-pill"), ativa);
    mostrar($("video-vazio"), !ativa);
    var wrap = $("video-wrap");
    if (wrap) wrap.classList.toggle("com-video", ativa);
  }

  function ligarCamera() {
    var sel = $("sel-camera");
    var corpo = {};
    if (sel && sel.value !== "") corpo.indice = parseInt(sel.value, 10);
    var btn = $("btn-camera");
    habilitar(btn, false);
    return postJSON("/api/camera/iniciar", corpo, { timeout: 20000 })
      .then(function (d) {
        habilitar(btn, true);
        if (d && d.ok === false) {
          var msg = (d.camera && d.camera.erro) || d.erro || "Não foi possível abrir a câmera.";
          toast(msg, "erro");
          atualizarChipCamera((d && d.camera) || { ativa: false });
          return;
        }
        var img = $("video-ao-vivo");
        if (img) {
          // Cache-busting: sem isso o navegador reaproveita o stream antigo.
          img.src = "/api/video?t=" + Math.round(performance.now());
          img.hidden = false;
        }
        atualizarChipCamera((d && d.camera) || { ativa: true });
        toast("Câmera ligada.", "ok");
      })
      .catch(function (e) {
        habilitar(btn, true);
        toast("Não consegui ligar a câmera: " + e.message, "erro");
      });
  }

  function desligarCamera() {
    var btn = $("btn-camera");
    habilitar(btn, false);
    // Limpar o src ANTES do POST encerra o consumo do MJPEG e libera o servidor.
    var img = $("video-ao-vivo");
    if (img) {
      img.removeAttribute("src");
      img.hidden = true;
    }
    return postJSON("/api/camera/parar", {}, { timeout: 15000 })
      .then(function () {
        habilitar(btn, true);
        atualizarChipCamera({ ativa: false });
        toast("Câmera desligada.", "info");
      })
      .catch(function (e) {
        habilitar(btn, true);
        atualizarChipCamera({ ativa: false });
        toast("Não consegui desligar a câmera: " + e.message, "erro");
      });
  }

  function alternarCamera() {
    if (App.cameraAtiva) desligarCamera();
    else ligarCamera();
  }

  function alternarGradcam(ligado) {
    return postJSON("/api/gradcam", { ligado: !!ligado })
      .then(function (d) {
        App.gradcamLigado = !!(d && d.ligado);
        var chk = $("toggle-gradcam");
        if (chk) chk.checked = App.gradcamLigado;
        toast(App.gradcamLigado ? "Mapa de calor ligado." : "Mapa de calor desligado.", "info");
      })
      .catch(function (e) {
        var chk = $("toggle-gradcam");
        if (chk) chk.checked = App.gradcamLigado; // desfaz visualmente
        toast("Não consegui mudar a opção: " + e.message, "erro");
      });
  }

  /**
   * Captura o quadro atual do MJPEG desenhando a <img> num canvas e manda para
   * /api/analisar. Como o stream e da mesma origem, o canvas nao fica "tainted".
   * O resultado abre na pagina Testar, que ja sabe exibir predicao e heatmap.
   */
  function capturarQuadro(automatico) {
    var img = $("video-ao-vivo");
    if (!App.cameraAtiva || !img || !img.naturalWidth) {
      toast("Ligue a câmera antes de analisar.", "aviso");
      return Promise.reject(new Error("câmera desligada"));
    }
    var btn = $("btn-capturar");
    var canvas = document.createElement("canvas");
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    try {
      canvas.getContext("2d").drawImage(img, 0, 0);
    } catch (e) {
      toast("Não consegui capturar a imagem.", "erro");
      return;
    }
    botaoCarregando(btn, true, "Lendo...");
    var fimVideo = iniciarEspera($("video-lendo"));
    return new Promise(function (resolver, rejeitar) {
      canvas.toBlob(function (blob) {
        if (!blob) {
          botaoCarregando(btn, false); fimVideo();
          toast("Captura vazia.", "erro");
          rejeitar(new Error("captura vazia"));
          return;
        }
        var arquivo = new File([blob], "captura.jpg", { type: "image/jpeg" });
        enviarParaAnalise(arquivo, "camera_servidor", { semRolar: !!automatico })
          .then(function (d) { botaoCarregando(btn, false); fimVideo(); resolver(d); })
          .catch(function (e) { botaoCarregando(btn, false); fimVideo(); rejeitar(e); });
      }, "image/jpeg", 0.92);
    });
  }

  /* --- Tela de espera enquanto a IA lê a peça ------------------------------ */

  var MENSAGENS_LEITURA = [
    "Recebendo a foto...",
    "Procurando pontos falhados...",
    "Olhando a linha e a tensão da costura...",
    "Conferindo o tecido...",
    "Comparando com os 12 tipos de defeito...",
    "Separando franzido de defeito...",
    "Quase pronto..."
  ];

  function iniciarEspera(caixa) {
    if (!caixa) return function () {};
    var texto = caixa.querySelector("[data-analisando-texto]");
    var barra = caixa.querySelector("[data-analisando-barra]");
    var inicio = Date.now(), i = 0;
    caixa.hidden = false;
    caixa.classList.remove("concluido");
    if (texto) texto.textContent = MENSAGENS_LEITURA[0];
    if (barra) barra.style.width = "4%";
    var relogio = setInterval(function () {
      var t = Date.now() - inicio;
      // Anda rápido no começo e desacelera: nunca chega a 100% antes da resposta.
      if (barra) barra.style.width = (4 + 88 * (1 - Math.exp(-t / 3200))).toFixed(1) + "%";
      var proxima = Math.min(MENSAGENS_LEITURA.length - 1, Math.floor(t / 1400));
      if (proxima !== i && texto) { i = proxima; texto.textContent = MENSAGENS_LEITURA[i]; }
    }, 120);
    return function () {
      clearInterval(relogio);
      if (barra) barra.style.width = "100%";
      caixa.classList.add("concluido");
      setTimeout(function () { caixa.hidden = true; }, 260);
    };
  }

  /* --- Câmera ao vivo: lê sozinha quando a peça fica parada ---------------- */

  var Auto = { timer: null, anterior: null, paradoDesde: 0, armado: true, ocupado: false, canvas: null };

  function textoAuto(titulo, sub) {
    setTexto($("veredito-titulo"), titulo);
    setTexto($("veredito-sub"), sub || "");
  }

  function iniciarAuto() {
    if (Auto.timer) return;
    Auto.anterior = null; Auto.paradoDesde = 0; Auto.armado = true;
    Auto.timer = setInterval(passoAuto, 300);
  }

  function pararAuto() {
    if (Auto.timer) clearInterval(Auto.timer);
    Auto.timer = null;
  }

  function passoAuto() {
    if (App.leituraModo !== "ia" || !App.cameraAtiva || App.pagina !== "ao-vivo") return;
    var img = $("video-ao-vivo");
    var ligado = $("auto-ler") && $("auto-ler").checked;
    if (!img || !img.naturalWidth || Auto.ocupado) return;
    if (!ligado) { textoAuto("Leitura por IA", "Toque em “Analisar esta peça” para ler."); return; }
    if (!Auto.canvas) { Auto.canvas = document.createElement("canvas"); Auto.canvas.width = 40; Auto.canvas.height = 30; }
    var ctx = Auto.canvas.getContext("2d", { willReadFrequently: true });
    try { ctx.drawImage(img, 0, 0, 40, 30); } catch (e) { return; }
    var px = ctx.getImageData(0, 0, 40, 30).data, cinza = new Float32Array(1200);
    for (var k = 0; k < 1200; k++) cinza[k] = 0.3 * px[k * 4] + 0.59 * px[k * 4 + 1] + 0.11 * px[k * 4 + 2];
    var dif = 0;
    if (Auto.anterior) { for (var j = 0; j < 1200; j++) dif += Math.abs(cinza[j] - Auto.anterior[j]); dif /= 1200; }
    Auto.anterior = cinza;
    var agora = Date.now();
    if (dif > 10) {
      Auto.armado = true; Auto.paradoDesde = 0;
      textoAuto("Peça em movimento", "Quando ela parar, a leitura começa sozinha.");
      return;
    }
    if (dif > 4) { Auto.paradoDesde = 0; return; }
    if (!Auto.paradoDesde) Auto.paradoDesde = agora;
    if (!Auto.armado) { textoAuto("Peça lida", "Troque de peça (ou mexa nela) para ler a próxima."); return; }
    if (agora - Auto.paradoDesde < 1200) { textoAuto("Segure a peça parada", "Lendo em um instante..."); return; }
    Auto.armado = false;
    Auto.ocupado = true;
    textoAuto("Lendo a peça", "A IA está olhando a costura.");
    var fim = capturarQuadro(true);
    Promise.resolve(fim).then(function () { Auto.ocupado = false; }, function () { Auto.ocupado = false; Auto.armado = true; });
  }


  /* =======================================================================
   * 07. POLLING DE /api/status E RENDER DA PAGINA AO VIVO
   * ===================================================================== */

  var anelCircunferencia = 0;

  function prepararAnel() {
    var arco = $("anel-arco");
    if (!arco) return;
    var r = parseFloat(arco.getAttribute("r") || "0");
    if (!r) {
      // Sem raio declarado nao da para calcular a circunferencia; usa um valor
      // grande o suficiente e deixa o CSS cuidar do resto.
      r = 52;
    }
    anelCircunferencia = 2 * Math.PI * r;
    arco.style.strokeDashoffset = "0";
    aplicarAnel(0);
  }

  function aplicarAnel(fracao) {
    var arco = $("anel-arco");
    if (!arco || !anelCircunferencia) return;
    var f = limitar(numero(fracao, 0), 0, 1);
    if (App.cache.anelFracao != null && Math.abs(App.cache.anelFracao - f) < 0.005) return;
    App.cache.anelFracao = f;
    arco.style.strokeDasharray = (f * anelCircunferencia).toFixed(2) + " " + anelCircunferencia.toFixed(2);
  }

  function iniciarPolling() {
    if (App.poll.ativo) return;
    App.poll.ativo = true;
    App.poll.falhas = 0;
    cicloStatus();
  }

  function pararPolling() {
    App.poll.ativo = false;
    if (App.poll.timer) { clearTimeout(App.poll.timer); App.poll.timer = null; }
    if (App.poll.abort) { try { App.poll.abort.abort(); } catch (e) { /* ignora */ } App.poll.abort = null; }
  }

  function agendarProximoStatus(ms) {
    if (!App.poll.ativo) return;
    // Rápido só com a câmera do computador ligada; sem ela, os números mudam
    // só quando alguém fotografa (e online cada consulta conta no plano grátis).
    if (!App.cameraAtiva) ms = Math.max(ms, document.hidden ? 60000 : 10000);
    App.poll.timer = setTimeout(cicloStatus, ms);
  }

  function cicloStatus() {
    if (!App.poll.ativo) return;
    // Aba escondida: nao adianta redesenhar, mas mantemos um pulso lento para
    // voltar instantaneo quando o operador retornar.
    if (document.hidden) {
      agendarProximoStatus(INTERVALO_STATUS_OCULTO_MS);
      return;
    }
    App.poll.abort = new AbortController();
    fetchJSON("/api/status", { sinal: App.poll.abort.signal, timeout: 4000 })
      .then(function (d) {
        App.poll.abort = null;
        App.poll.falhas = 0;
        renderAoVivo(d || {});
        agendarProximoStatus(INTERVALO_STATUS_MS);
      })
      .catch(function (e) {
        App.poll.abort = null;
        if (e && e.abortada && !e.expirou) return; // parada proposital
        App.poll.falhas += 1;
        if (App.poll.falhas === 3) toast("Perdi contato com o servidor. Tentando de novo...", "erro");
        // Backoff simples: nao martelar um servidor que caiu.
        agendarProximoStatus(Math.min(3000, INTERVALO_STATUS_MS * Math.pow(2, Math.min(4, App.poll.falhas))));
      });
  }

  function renderAoVivo(d) {
    var veredito = d.veredito || {};
    var predicao = d.predicao || null;
    var stats = d.estatisticas || {};

    App.leituraModo = (d.leitura && d.leitura.modo) || "local";
    var daIA = App.leituraModo === "ia";
    mostrar($("auto-ler-rotulo"), daIA);
    mostrar($("gradcam-rotulo"), !daIA);
    if (daIA && App.cameraAtiva) {
      iniciarAuto();
      var caixaVeredito = $("veredito");
      if (caixaVeredito && App.cache.vereditoEstado !== "ia") {
        App.cache.vereditoEstado = "ia";
        caixaVeredito.classList.remove("estado-aquecendo", "estado-ok", "estado-falha", "estado-incerto");
        caixaVeredito.classList.add("estado-aquecendo");
        setHTML($("veredito-icone"), iconeDoEstado("aquecendo"), "veredito-icone");
      }
    } else {
      pararAuto();
      renderVeredito(veredito, predicao);
      renderTop(predicao);
    }
    renderEstatisticas(stats);

    if (d.camera) atualizarChipCamera(d.camera);
    if ("lote_ativo" in d) renderChipLote(d.lote_ativo);

    var fps = $("fps");
    if (fps) {
      var v = numero(d.fps, 0).toFixed(1).replace(".", ",");
      setTexto(fps, v + " fps");
    }

    var ev = d.ultimo_evento || null;
    var novoId = ev && ev.id ? ev.id : null;
    if (novoId !== App.ultimoEventoId) {
      App.ultimoEventoId = novoId;
      App.ultimoEvento = ev;
      habilitar($("btn-diagnostico"), !!novoId);
      habilitar($("btn-conferir-ultimo"), !!novoId);
      if (novoId) atualizarPendentes();
      if (novoId) {
        // Evento novo: limpa o painel para nao misturar com a analise anterior.
        mostrar($("painel-ia"), false);
        setHTML($("ia-conteudo"), "", "ia-conteudo");
      }
    }
  }

  function renderVeredito(veredito, predicao) {
    var caixa = $("veredito");
    var estado = veredito.estado || "aquecendo";

    if (caixa && App.cache.vereditoEstado !== estado) {
      App.cache.vereditoEstado = estado;
      caixa.classList.remove("estado-aquecendo", "estado-ok", "estado-falha", "estado-incerto");
      caixa.classList.add("estado-" + estado);
      caixa.setAttribute("data-estado", estado);
      setHTML($("veredito-icone"), iconeDoEstado(estado), "veredito-icone");
    }

    var titulo, sub;
    if (estado === "aquecendo" && !App.cameraAtiva) {
      titulo = "Câmera desligada";
      sub = "Toque em Ligar câmera, ou use Fotografar acima.";
    } else if (estado === "aquecendo") {
      titulo = "Lendo a costura";
      sub = "Mantenha a peça parada por um instante...";
    } else if (estado === "ok") {
      titulo = "Costura aprovada";
      sub = "Pontos uniformes - " + formatarPercentual(veredito.confianca) + " de certeza";
    } else if (estado === "falha") {
      titulo = veredito.nome || nomeDaClasse(veredito.classe_key);
      sub = "Defeito encontrado - " + formatarPercentual(veredito.confianca) + " de certeza";
    } else {
      titulo = "Leitura incerta";
      sub = (veredito.nome ? veredito.nome + " - " : "") +
        formatarPercentual(veredito.confianca) + " de certeza - confira a peça";
    }

    setTexto($("veredito-titulo"), titulo);
    setTexto($("veredito-sub"), sub);

    var conf = veredito.confianca;
    if (conf == null && predicao) conf = predicao.confianca;
    aplicarAnel(numero(conf, 0));
    setTexto($("anel-valor"), conf == null ? "--" : formatarPercentual(conf));

    // Leitura insegura: destaca o "Por que?", que já inclui a segunda opinião.
    var btnLlm = $("btn-diagnostico");
    if (btnLlm) btnLlm.classList.toggle("destaque", !!veredito.pede_llm);
  }

  var refsTop = null;

  function renderTop(predicao) {
    var lista = $("lista-top");
    if (!lista) return;
    var top = (predicao && Array.isArray(predicao.top)) ? predicao.top.slice(0, 3) : [];

    if (!top.length) {
      if (App.cache.topVazio !== true) {
        lista.innerHTML = "";
        refsTop = null;
        App.cache.topVazio = true;
      }
      return;
    }
    App.cache.topVazio = false;

    // Estrutura montada uma unica vez; depois so trocamos texto e largura.
    if (!refsTop || refsTop.length !== top.length) {
      lista.innerHTML = "";
      refsTop = top.map(function () {
        var li = criar("li", "barra-item");
        var linha = criar("div", "barra-linha");
        var nome = criar("span", "barra-nome");
        var valor = criar("span", "barra-valor");
        linha.appendChild(nome);
        linha.appendChild(valor);
        var trilho = criar("div", "barra-trilho");
        var preenche = criar("div", "barra-preenche");
        trilho.appendChild(preenche);
        li.appendChild(linha);
        li.appendChild(trilho);
        lista.appendChild(li);
        return { li: li, nome: nome, valor: valor, preenche: preenche, largura: -1, classe: null };
      });
    }

    top.forEach(function (item, i) {
      var ref = refsTop[i];
      if (!ref) return;
      var nome = item.nome || nomeDaClasse(item.key);
      setTexto(ref.nome, nome);
      setTexto(ref.valor, formatarPercentual(item.prob, 1));
      var pct = limitar(numero(item.prob, 0) * 100, 0, 100);
      if (Math.abs(ref.largura - pct) > 0.4) {
        ref.preenche.style.width = pct.toFixed(1) + "%";
        ref.largura = pct;
      }
      if (ref.classe !== item.key) {
        ref.classe = item.key;
        ref.li.setAttribute("data-classe", item.key || "");
        ref.li.classList.toggle("classe-ok", item.index === 0);
        ref.preenche.setAttribute("data-gravidade", gravidadeDaClasse(item.key));
      }
    });
  }

  function renderEstatisticas(s) {
    setTexto($("stat-total"), numero(s.total, 0));
    setTexto($("stat-aprovadas"), numero(s.aprovadas, 0));
    setTexto($("stat-reprovadas"), numero(s.reprovadas, 0));
    setTexto($("stat-taxa"), formatarPercentual(s.taxa_aprovacao));
    setTexto($("stat-sequencia"), numero(s.sequencia_ok, 0));
    setTexto($("stat-recorde"), numero(s.melhor_sequencia, 0));
    renderBarraMeta(s);
    renderChama(numero(s.sequencia_ok, 0));
    // Peça nova (foto ou câmera ao vivo): atualiza a lista lateral.
    var total = numero(s.total, 0);
    if (App.cache.totalRecentes !== total) {
      App.cache.totalRecentes = total;
      carregarRecentes();
    }
  }

  function renderBarraMeta(s) {
    var barra = $("barra-meta");
    if (!barra) return;
    var meta = Math.max(1, Math.round(numero(s.meta_pecas, 10)));
    setTexto($("meta-texto"), numero(s.total, 0) + " de " + meta + " peças");
    // Muitos segmentos viram serrilhado visual; 12 e o teto confortavel.
    var qtd = Math.min(12, meta);
    if (App.cache.metaSegmentos !== qtd) {
      App.cache.metaSegmentos = qtd;
      App.cache.metaCheios = -1;
      barra.innerHTML = "";
      for (var i = 0; i < qtd; i++) barra.appendChild(criar("div", "segmento"));
      barra.setAttribute("role", "progressbar");
      barra.setAttribute("aria-valuemin", "0");
      barra.setAttribute("aria-valuemax", "100");
    }
    var progresso = limitar(numero(s.progresso_meta, 0), 0, 1);
    if (progresso > 1.0001) progresso = limitar(progresso / 100, 0, 1);
    var cheios = Math.round(progresso * qtd);
    if (App.cache.metaCheios === cheios) return;
    App.cache.metaCheios = cheios;
    var segmentos = barra.children;
    for (var j = 0; j < segmentos.length; j++) {
      segmentos[j].classList.toggle("cheio", j < cheios);
    }
    barra.setAttribute("aria-valuenow", Math.round(progresso * 100));
    barra.setAttribute("aria-label", "Progresso da meta: " + numero(s.total, 0) + " de " + meta + " peças");
  }

  function renderChama(sequencia) {
    var el = $("chama-sequencia");
    if (!el) return;
    if (App.cache.chamaEstrutura !== true) {
      App.cache.chamaEstrutura = true;
      el.innerHTML = '<span class="chama-icone" aria-hidden="true">' + ICONES.chama + "</span>" +
        '<span class="chama-num">0</span>';
    }
    var num = el.querySelector(".chama-num");
    setTexto(num, sequencia);
    // Nivel visual da sequencia: o CSS decide a cor, aqui so classificamos.
    var nivel = sequencia <= 0 ? 0 : (sequencia < 5 ? 1 : (sequencia < 15 ? 2 : 3));
    if (App.cache.chamaNivel !== nivel) {
      App.cache.chamaNivel = nivel;
      el.classList.remove("nivel-0", "nivel-1", "nivel-2", "nivel-3");
      el.classList.add("nivel-" + nivel);
      el.classList.toggle("acesa", nivel > 0);
    }
    el.setAttribute("aria-label", "Sequencia de " + sequencia + " peças aprovadas");
  }

  /* =======================================================================
   * 08. PAINEL DE IA (DIAGNOSTICO E SEGUNDA OPINIAO)
   * ===================================================================== */

  function seloFonte(fonte) {
    return '<p class="explicacao-fonte">Fonte: ' + esc(fonte === "llm" ? "IA generativa" : "base técnica do sistema") + "</p>";
  }

  function listaHTML(titulo, itens) {
    if (!Array.isArray(itens) || !itens.length) return "";
    var li = itens.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("");
    return "<h4>" + esc(titulo) + '</h4><ul class="explicacao-lista">' + li + "</ul>";
  }

  /**
   * Explicação em uma frase (a primeira ação), com causas e prevenção recolhidas.
   * Quem está na bancada precisa saber o que fazer agora; o resto é consulta.
   */
  function htmlDiagnostico(diag) {
    if (!diag) return "";
    var acoes = Array.isArray(diag.acoes) ? diag.acoes : [];
    var frase = acoes[0] || diag.resumo || "";
    var resto = (diag.resumo && acoes[0] ? '<p>' + esc(diag.resumo) + "</p>" : "") +
      listaHTML("O que fazer agora", acoes) +
      listaHTML("Causas prováveis", diag.causas) +
      listaHTML("Como prevenir", diag.prevencao) +
      seloFonte(diag.fonte);
    return (frase ? '<p class="explicacao-frase">' + esc(frase) + "</p>" : "") +
      '<button type="button" class="btn-link" data-alternar="Esconder causas e prevenção" aria-expanded="false">Ver causas e prevenção</button>' +
      '<div class="explicacao-mais" hidden>' + resto + "</div>";
  }

  function htmlRevisao(rev) {
    if (!rev) return "";
    var concorda = rev.concorda;
    var rotulo, classeSelo;
    if (concorda === true) { rotulo = "A segunda opinião concordou"; classeSelo = "selo-ok"; }
    else if (concorda === false) { rotulo = "A segunda opinião discordou"; classeSelo = "selo-nao"; }
    else { rotulo = "Sem resposta da segunda opinião"; classeSelo = "selo-neutro"; }

    var html = '<div class="explicacao ia-revisao"><h4>Segunda opinião</h4>' +
      '<span class="selo-fonte ' + classeSelo + '">' + esc(rotulo) + "</span>";

    if (rev.erro) {
      html += '<p class="ia-erro">' + esc(rev.erro) + "</p>";
    } else {
      if (rev.classe_sugerida) {
        html += '<p class="ia-sugestao">Classe sugerida: <strong>' +
          esc(rev.nome_sugerido || nomeDaClasse(rev.classe_sugerida)) + "</strong>" +
          (rev.confianca != null ? " (" + esc(formatarPercentual(rev.confianca)) + ")" : "") + "</p>";
      }
      if (rev.justificativa) html += '<p class="ia-resumo">' + esc(rev.justificativa) + "</p>";
      html += listaHTML("Sinais observados", rev.sinais, "ia-sinais");
    }
    html += "</div>";
    return html;
  }

  function pedirDiagnostico() {
    var id = App.ultimoEventoId;
    var btn = $("btn-diagnostico");
    if (!id) { toast("Nenhuma peça registrada ainda.", "aviso"); return; }
    botaoCarregando(btn, true, "Buscando explicação...");
    mostrar($("painel-ia"), true);
    setHTML($("ia-conteudo"), '<p class="ia-carregando">Buscando causas e soluções...</p>', "ia-conteudo");
    postJSON("/api/eventos/" + encodeURIComponent(id) + "/diagnostico", {}, { timeout: 60000 })
      .then(function (d) {
        botaoCarregando(btn, false);
        if (d && d.erro) {
          setHTML($("ia-conteudo"), '<p class="ia-erro">' + esc(d.erro) + "</p>", "ia-conteudo");
          toast(d.erro, "erro");
          return;
        }
        setHTML($("ia-conteudo"), htmlDiagnostico(d && d.diagnostico), "ia-conteudo");
        // Leitura incerta: pede também a segunda opinião, sem outro clique.
        var ultimo = App.ultimoEvento;
        if (ultimo && ultimo.id === id && ultimo.precisa_revisao && !ultimo.revisao_humana) pedirSegundaOpiniao(true);
      })
      .catch(function (e) {
        botaoCarregando(btn, false);
        setHTML($("ia-conteudo"), '<p class="ia-erro">' + esc(e.message) + "</p>", "ia-conteudo");
        toast("Não consegui buscar a explicação: " + e.message, "erro");
      });
  }

  function pedirSegundaOpiniao(anexar) {
    var id = App.ultimoEventoId;
    var btn = $("btn-diagnostico");
    if (!id) return;
    var antes = anexar ? (($("ia-conteudo") || {}).innerHTML || "") : "";
    botaoCarregando(btn, true, "Pedindo segunda opinião...");
    mostrar($("painel-ia"), true);
    setHTML($("ia-conteudo"), antes + '<p class="ia-carregando">Pedindo uma segunda opinião...</p>', "ia-conteudo");
    postJSON("/api/eventos/" + encodeURIComponent(id) + "/revisao", {}, { timeout: 90000 })
      .then(function (d) {
        botaoCarregando(btn, false);
        if (d && d.erro && !d.revisao) {
          setHTML($("ia-conteudo"), antes + '<p class="ia-erro">' + esc(d.erro) + "</p>", "ia-conteudo");
          return;
        }
        setHTML($("ia-conteudo"), antes + htmlRevisao(d && d.revisao), "ia-conteudo");
      })
      .catch(function (e) {
        botaoCarregando(btn, false);
        setHTML($("ia-conteudo"), antes + '<p class="ia-erro">' + esc(e.message) + "</p>", "ia-conteudo");
      });
  }

  /* =======================================================================
   * 09. CAPTURA POR FOTO E CONFERENCIA HUMANA
   * ===================================================================== */

  var NOMES_ORIGEM = { upload: "Foto enviada", camera_aparelho: "Foto do celular", camera_servidor: "Câmera ao vivo", ao_vivo: "Câmera ao vivo" };

  window.analisarArquivoInspecao = tratarArquivoEscolhido;
  function tratarArquivoEscolhido(arquivo, origem) {
    if (!arquivo) return;
    if (!/^image\//.test(arquivo.type)) {
      toast("Escolha um arquivo de imagem (JPG ou PNG).", "aviso");
      return;
    }
    enviarParaAnalise(arquivo, origem || "upload").catch(function () {});
  }

  /** Foto grande (celular) vira JPEG de até 1600 px: leve para enviar e suficiente para a IA. */
  function reduzirParaEnvio(arquivo) {
    return new Promise(function (resolver) {
      if (!arquivo || arquivo.size < 900 * 1024 || !window.createImageBitmap) { resolver(arquivo); return; }
      createImageBitmap(arquivo).then(function (bmp) {
        var escala = Math.min(1, 1600 / Math.max(bmp.width, bmp.height));
        var tela = document.createElement("canvas");
        tela.width = Math.round(bmp.width * escala);
        tela.height = Math.round(bmp.height * escala);
        tela.getContext("2d").drawImage(bmp, 0, 0, tela.width, tela.height);
        tela.toBlob(function (blob) {
          resolver(blob ? new File([blob], "foto.jpg", { type: "image/jpeg" }) : arquivo);
        }, "image/jpeg", 0.88);
      }).catch(function () { resolver(arquivo); });
    });
  }

  function enviarParaAnalise(arquivo, origem, opcoes) {
    opcoes = opcoes || {};
    var resultado = $("resultado-teste");
    mostrar(resultado, true);
    // "Próxima peça" repete o caminho que a pessoa acabou de usar.
    var proxima = $("btn-proxima");
    if (proxima) proxima.setAttribute("for", origem === "camera_aparelho" ? "foto-camera" : "input-arquivo");
    setHTML($("teste-ia"), "", "teste-ia");
    setHTML($("conferencia-upload"), "", "conferencia-upload");
    setTexto($("teste-classe"), "Lendo a peça...");
    setTexto($("teste-confianca"), App.leituraModo === "ia" ? "A IA leva alguns segundos para olhar com cuidado." : "");
    mostrar($("teste-explicacao"), false);
    if (resultado) resultado.classList.remove("resultado-ok", "resultado-falha", "resultado-incerto");
    var fotoAnterior = $("peca-analisada");
    if (fotoAnterior) {
      if (App.urlPrevia) URL.revokeObjectURL(App.urlPrevia);
      App.urlPrevia = URL.createObjectURL(arquivo);
      fotoAnterior.src = App.urlPrevia;
    }
    var fimEspera = iniciarEspera(resultado && resultado.querySelector("[data-analisando]"));
    if (!opcoes.semRolar && resultado && resultado.scrollIntoView) resultado.scrollIntoView({ behavior: "smooth", block: "start" });

    return reduzirParaEnvio(arquivo).then(function (leve) {
      var fd = new FormData();
      fd.append("arquivo", leve, leve.name || "imagem.jpg");
      fd.append("origem", origem || "upload");
      return fetchJSON("/api/analisar", { method: "POST", body: fd, timeout: 60000 });
    })
      .then(function (d) {
        fimEspera();
        if (d && d.erro) {
          setTexto($("teste-classe"), "Não foi possível analisar");
          setTexto($("teste-confianca"), d.erro);
          throw new Error(d.erro);
        }
        App.analiseAtual = d || {};
        renderResultadoTeste(App.analiseAtual);
        atualizarPendentes();
        carregarRecentes();
        if (d.aviso) toast(d.aviso, "aviso");
        fetchJSON("/api/status").then(function (st) { if (st) renderAoVivo(st); }).catch(function () {});
        return App.analiseAtual;
      })
      .catch(function (e) {
        fimEspera();
        setTexto($("teste-classe"), "Não foi possível analisar");
        toast(e.message, "erro");
        throw e;
      });
  }

  function mostrarMidiaResultado(mapa) {
    var d = App.analiseAtual || {};
    var img = $("peca-analisada");
    if (img) img.src = (mapa && d.heatmap) ? d.heatmap : (d.imagem || PIXEL_VAZIO);
    [["ver-foto", !mapa], ["ver-mapa", !!mapa]].forEach(function (par) {
      var b = $(par[0]);
      if (!b) return;
      b.classList.toggle("ativo", par[1]);
      b.setAttribute("aria-pressed", par[1] ? "true" : "false");
    });
  }

  function renderResultadoTeste(d) {
    var p = d.predicao || {};
    var ev = d.evento || {};
    // A predição nem sempre traz e_falha; o evento sempre traz.
    if (p.e_falha == null) p.e_falha = ev.e_falha != null ? !!ev.e_falha : p.classe_key !== "normal";
    mostrar($("resultado-teste"), true);
    var daIA = d.fonte === "ia";
    setTexto($("ver-mapa"), daIA ? "Onde está o defeito" : "Onde a IA olhou");
    mostrarMidiaResultado(daIA && !!d.heatmap);
    var leitura = p.leitura || {};
    setTexto($("teste-explicacao"), daIA ? (leitura.explicacao || "") : "");
    mostrar($("teste-explicacao"), daIA && !!leitura.explicacao);
    setTexto($("resultado-lote"), ev.lote_codigo ? "Lote " + ev.lote_codigo : "Sem lote");
    setTexto($("resultado-ordem"), (NOMES_ORIGEM[ev.origem] || "Foto enviada") + (ev.hora ? " · " + horaCurta(ev) : ""));
    habilitar($("ver-mapa"), !!d.heatmap);

    var incerta = !p.e_falha && !!ev.precisa_revisao;
    setTexto($("teste-classe"), p.e_falha ? (p.nome || nomeDaClasse(p.classe_key))
      : (incerta ? "Leitura incerta: parece normal" : "Costura aprovada"));
    setTexto($("teste-confianca"), daIA
      ? (incerta || leitura.veredito === "incerta" ? "A IA ficou em dúvida. Confira a peça."
        : "Lida pela IA, com " + formatarPercentual(p.confianca, 0) + " de certeza.")
      : "Leitura local, com " + formatarPercentual(p.confianca, 0) + " de certeza" + (incerta ? ". Confira a peça." : "."));

    var caixa = $("resultado-teste");
    if (caixa) {
      caixa.classList.toggle("resultado-ok", p.e_falha === false && !incerta);
      caixa.classList.toggle("resultado-incerto", incerta);
      caixa.classList.toggle("resultado-falha", p.e_falha === true);
      caixa.setAttribute("data-gravidade", p.gravidade || "");
    }

    var topo = $("teste-top");
    if (topo) {
      var itens = Array.isArray(p.top) ? p.top : [];
      setHTML(topo, itens.map(function (item) {
        var pct = limitar(numero(item.prob, 0) * 100, 0, 100);
        return '<li class="barra-item" data-classe="' + esc(item.key) + '">' +
          '<div class="barra-linha">' +
          '<span class="barra-nome">' + esc(item.nome || nomeDaClasse(item.key)) + "</span>" +
          '<span class="barra-valor">' + esc(formatarPercentual(item.prob, 0)) + "</span>" +
          "</div>" +
          '<div class="barra-trilho"><div class="barra-preenche" style="width:' +
          pct.toFixed(1) + '%"></div></div>' +
          "</li>";
      }).join(""), "teste-top");
    }

    montarConferencia($("conferencia-upload"), ev, function (salvo) {
      App.analiseAtual.evento = salvo;
      setTexto($("teste-classe"), salvo.e_falha ? salvo.nome_final : "Costura aprovada");
      var c = $("resultado-teste");
      if (c) {
        c.classList.remove("resultado-incerto");
        c.classList.toggle("resultado-ok", !salvo.e_falha);
        c.classList.toggle("resultado-falha", !!salvo.e_falha);
      }
      setTexto($("teste-confianca"), "Conferido por você. Sugestão da IA: " + (p.nome || nomeDaClasse(p.classe_key)));
    });

    habilitar($("btn-teste-diagnostico"), true);
    // Com defeito, a explicação e a solução já aparecem sem precisar pedir.
    if (p.e_falha) diagnosticoDoTeste();
  }

  /**
   * Bloco único de conferência, usado no resultado da foto e no detalhe da peça.
   * A classe sugerida pela IA vem marcada; trocar a classe registra "corrigida".
   */
  function montarConferencia(host, ev, aoSalvar) {
    if (!host || !ev || !ev.id) { setHTML(host, "", host && host.id); return; }
    var escolhida = ev.classe_final || ev.classe_key;
    var feita = !!ev.revisao_humana;
    var pendente = !feita && !!ev.precisa_revisao;

    var opcoes = App.classes.map(function (c) {
      var ativo = c.key === escolhida;
      return '<button type="button" class="classe-opcao' + (ativo ? " ativo" : "") +
        '" data-classe="' + esc(c.key) + '" aria-pressed="' + (ativo ? "true" : "false") + '">' + esc(c.nome) +
        (c.key === ev.classe_key ? " <small>(sugestão da IA)</small>" : "") + "</button>";
    }).join("");

    var topo = pendente
      ? '<div class="conferencia-acoes">' +
        '<button type="button" class="btn btn-principal conferencia-certo">Está certo</button>' +
        '<button type="button" class="btn btn-secundario conferencia-corrigir">Corrigir</button></div>'
      : '<div class="conferencia-situacao"><span class="estado ' + (feita ? "estado-ok" : "estado-neutro") + '">' +
        esc(feita ? "Conferida" : "Aprovada automaticamente") + "</span>" +
        '<button type="button" class="btn btn-quieto conferencia-corrigir">' + (feita ? "Alterar" : "Corrigir") + "</button></div>";

    host.innerHTML = topo +
      '<div class="conferencia-corrigir-caixa" hidden>' +
      '<p class="campo-rotulo">Qual é o resultado certo?</p>' +
      '<div class="classe-opcoes" role="group" aria-label="Resultado certo">' + opcoes + "</div>" +
      '<label class="campo"><span class="campo-rotulo">Observação (opcional)</span>' +
      '<input class="entrada conferencia-obs" maxlength="1000" value="' + esc((ev.revisao_humana && ev.revisao_humana.observacao) || "") + '"></label>' +
      '<div class="linha-botoes"><button type="button" class="btn btn-principal conferencia-salvar">Salvar correção</button>' +
      '<button type="button" class="btn btn-quieto conferencia-cancelar">Cancelar</button></div>' +
      "</div>";
    if (host.id) App.cache[host.id] = null;

    var caixa = host.querySelector(".conferencia-corrigir-caixa");
    function abrir(sim) { caixa.hidden = !sim; }
    host.querySelector(".conferencia-corrigir").addEventListener("click", function () { abrir(caixa.hidden); });
    host.querySelector(".conferencia-cancelar").addEventListener("click", function () { abrir(false); });

    host.querySelectorAll(".classe-opcao").forEach(function (b) {
      b.addEventListener("click", function () {
        escolhida = b.getAttribute("data-classe");
        host.querySelectorAll(".classe-opcao").forEach(function (x) {
          var on = x === b;
          x.classList.toggle("ativo", on);
          x.setAttribute("aria-pressed", on ? "true" : "false");
        });
      });
    });

    function enviar(botao, classe) {
      botaoCarregando(botao, true, "Salvando...");
      postJSON("/api/eventos/" + encodeURIComponent(ev.id) + "/conferencia",
        { classe: classe, observacao: host.querySelector(".conferencia-obs").value })
        .then(function (d) {
          botaoCarregando(botao, false);
          if (d && d.erro) { toast(d.erro, "erro"); return; }
          Object.assign(ev, d.evento || {});
          toast(ev.revisao_humana && ev.revisao_humana.decisao === "corrigida"
            ? "Correção salva. Ela ajuda a treinar a IA." : "Conferência salva.", "ok");
          atualizarPendentes();
          montarConferencia(host, ev, aoSalvar);
          if (aoSalvar) aoSalvar(ev);
        })
        .catch(function (e) {
          botaoCarregando(botao, false);
          toast("Não consegui salvar: " + e.message, "erro");
        });
    }
    var certo = host.querySelector(".conferencia-certo");
    // "Está certo" confirma a sugestão da IA com um toque.
    if (certo) certo.addEventListener("click", function () { enviar(certo, ev.classe_key); });
    var salvar = host.querySelector(".conferencia-salvar");
    salvar.addEventListener("click", function () { enviar(salvar, escolhida); });
  }

  function diagnosticoDoTeste() {
    var d = App.analiseAtual;
    var btn = $("btn-teste-diagnostico");
    var eventoId = d && (d.evento_id || (d.evento && d.evento.id));
    if (!eventoId) { toast("Analise uma foto primeiro.", "aviso"); return; }

    setHTML($("teste-ia"), '<p class="ia-carregando">Buscando o que fazer...</p>', "teste-ia");
    postJSON("/api/eventos/" + encodeURIComponent(eventoId) + "/diagnostico", {}, { timeout: 60000 })
      .then(function (r) {
        botaoCarregando(btn, false);
        var diag = (r && r.diagnostico) || r;
        if (!diag || diag.erro) {
          setHTML($("teste-ia"), '<p class="ia-erro">' + esc((diag && diag.erro) || "Explicação indisponível.") + "</p>", "teste-ia");
          return;
        }
        setHTML($("teste-ia"), htmlDiagnostico(diag), "teste-ia");
      })
      .catch(function (e) {
        botaoCarregando(btn, false);
        setHTML($("teste-ia"), '<p class="ia-erro">' + esc(e.message) + "</p>", "teste-ia");
      });
  }

  /* =======================================================================
   * 10. PAGINA HISTORICO E DETALHE DA PECA
   * ===================================================================== */

  var historico = { eventos: [], filtro: null, modo: "todas", porId: {} };

  function hojeISO() {
    var d = new Date();
    function dois(x) { return x < 10 ? "0" + x : String(x); }
    return d.getFullYear() + "-" + dois(d.getMonth() + 1) + "-" + dois(d.getDate());
  }

  function carregarHistorico() {
    var params = "?limite=500";
    if ($("historico-dia") && $("historico-dia").value) params += "&dia=" + encodeURIComponent($("historico-dia").value);
    if (historico.modo === "defeitos") params += "&defeitos=true";
    if (historico.modo === "pendentes") params += "&pendentes=true";
    if (historico.filtro) params += "&classe=" + encodeURIComponent(historico.filtro);
    return fetchJSON("/api/eventos" + params)
      .then(function (d) {
        historico.eventos = (d && d.eventos) || [];
        historico.porId = {};
        historico.eventos.forEach(function (ev) { if (ev && ev.id) historico.porId[ev.id] = ev; });
        renderTipos(historico.eventos);
        renderGrade(historico.eventos);
      })
      .catch(function (e) {
        toast("Não consegui carregar o histórico: " + e.message, "erro");
      });
  }

  /** Conta as peças aguardando conferência (todos os dias) e mostra nos menus. */
  function atualizarPendentes() {
    return fetchJSON("/api/eventos?limite=500&pendentes=true")
      .then(function (d) {
        var n = ((d && d.eventos) || []).length;
        document.querySelectorAll("[data-badge-pendentes]").forEach(function (el) {
          el.textContent = n >= 500 ? "500+" : String(n);
          el.hidden = n === 0;
        });
      })
      .catch(function () {});
  }

  /** Menu "Tipo": só os tipos que apareceram no dia, com a contagem. */
  function renderTipos(eventos) {
    var sel = $("historico-tipo");
    if (!sel) return;
    var contagem = {};
    eventos.forEach(function (ev) {
      if (!ev || !ev.classe_key) return;
      var key = ev.classe_final || ev.classe_key;
      contagem[key] = (contagem[key] || 0) + 1;
    });
    var html = '<option value="">Todos os tipos</option>';
    App.classes.forEach(function (c) {
      var n = numero(contagem[c.key], 0);
      if (!n && historico.filtro !== c.key) return;
      html += '<option value="' + esc(c.key) + '"' + (historico.filtro === c.key ? " selected" : "") + ">" +
        esc(c.nome) + " (" + n + ")</option>";
    });
    setHTML(sel, html, "historico-tipo");
    sel.value = historico.filtro || "";
  }

  function classeDoEstado(ev) {
    if (ev.revisao_humana) return "estado-ok";
    return ev.precisa_revisao ? "estado-atencao" : "estado-neutro";
  }


  function situacaoConferencia(ev) {
    if (ev.revisao_humana) return "Conferida";
    return ev.precisa_revisao ? "Aguardando conferência" : "Aprovada automaticamente";
  }

  function renderGrade(eventos) {
    var grade = $("grade-historico");
    if (!grade) return;
    if (!eventos.length) {
      setHTML(grade, "", "grade-historico");
      mostrar($("historico-vazio"), true);
      return;
    }
    mostrar($("historico-vazio"), false);

    var html = eventos.map(function (ev) {
      var nome = ev.nome_final || ev.nome || nomeDaClasse(ev.classe_key);
      var semFoto = ev.imagem ? "" : " sem-foto";
      return '<button type="button" class="celula linha linha-clicavel' + semFoto + '" data-id="' + esc(ev.id) +
        '" aria-label="' + esc(nome + " às " + horaCurta(ev)) + '">' +
        '<span class="h-foto"><img class="miniatura" src="' + esc(ev.imagem || PIXEL_VAZIO) + '" alt="" loading="lazy"></span>' +
        '<span class="h-nome"><strong>' + esc(nome) + "</strong></span>" +
        '<span class="h-lote">' + esc(ev.lote_codigo || "Sem lote") + "</span>" +
        '<span class="h-hora num">' + esc(horaCurta(ev)) + "</span>" +
        '<span class="h-origem">' + esc(NOMES_ORIGEM[ev.origem] || "Câmera ao vivo") + "</span>" +
        '<span class="h-situacao"><span class="estado ' + classeDoEstado(ev) + '">' + esc(situacaoConferencia(ev)) + "</span></span>" +
        "</button>";
    }).join("");
    setHTML(grade, html, "grade-historico");
  }

  /** Linha compacta de peça (lateral do Inspecionar e da fila). Abre o detalhe ao tocar. */
  function linhaCompacta(ev, atributo) {
    var nome = ev.nome_final || ev.nome || nomeDaClasse(ev.classe_key);
    // "celula" + data-id reaproveita o clique do histórico, que abre o detalhe da peça.
    var classe = "recente" + (atributo === "data-id" ? " celula" : "") + (ev.imagem ? "" : " sem-foto");
    return '<button type="button" class="' + classe + '" ' + atributo + '="' + esc(ev.id) +
      '" aria-label="' + esc(nome + " às " + horaCurta(ev)) + '">' +
      '<img class="miniatura" src="' + esc(ev.imagem || PIXEL_VAZIO) + '" alt="" loading="lazy">' +
      '<span class="recente-texto"><strong>' + esc(nome) + "</strong>" +
      '<small class="num">' + esc(horaCurta(ev)) + " · " + esc(ev.lote_codigo || "Sem lote") + "</small></span>" +
      '<span class="estado ' + classeDoEstado(ev) + '"><span class="so-leitor">' + esc(situacaoConferencia(ev)) + "</span></span>" +
      "</button>";
  }

  /** Últimas peças de hoje, na lateral do Inspecionar. */
  function carregarRecentes() {
    var host = $("recentes");
    if (!host) return Promise.resolve();
    return fetchJSON("/api/eventos?limite=8&dia=" + encodeURIComponent(hojeISO()))
      .then(function (d) {
        var eventos = ((d && d.eventos) || []).filter(function (ev) { return ev && ev.id; });
        eventos.forEach(function (ev) { historico.porId[ev.id] = ev; });
        setHTML(host, eventos.map(function (ev) { return linhaCompacta(ev, "data-id"); }).join(""), "recentes");
        mostrar($("recentes-vazio"), !eventos.length);
      })
      .catch(function () {});
  }

  function filtrarHistorico(chave) {
    historico.filtro = (chave === "tudo" || !chave) ? null : chave;
    carregarHistorico();
  }

  function mudarModoHistorico(modo) {
    historico.modo = modo;
    carregarHistorico();
  }

  /* --- Conferir: fila das peças que pedem conferência -------------------- */

  var fila = { eventos: [], puladas: {} };

  function carregarFila() {
    return fetchJSON("/api/eventos?limite=500&pendentes=true")
      .then(function (d) {
        fila.eventos = ((d && d.eventos) || []).filter(function (ev) { return ev && ev.id; });
        mostrarProximaDaFila();
      })
      .catch(function (e) { toast("Não consegui carregar a fila: " + e.message, "erro"); });
  }

  function mostrarProximaDaFila() {
    var restantes = fila.eventos.filter(function (ev) { return ev.precisa_revisao && !ev.revisao_humana; });
    // As puladas voltam para o fim: só some da fila o que foi conferido.
    var escolhida = restantes.filter(function (x) { return x.id === fila.escolhida; })[0];
    var ev = escolhida || restantes.filter(function (x) { return !fila.puladas[x.id]; })[0] || restantes[0];
    if (ev && !escolhida && fila.puladas[ev.id]) fila.puladas = {};
    fila.escolhida = null;
    var n = restantes.length;
    // Lateral: as outras peças da fila, para escolher qual conferir.
    var outras = restantes.filter(function (x) { return !ev || x.id !== ev.id; });
    mostrar($("fila-lateral"), outras.length > 0);
    setHTML($("fila-lista"), outras.slice(0, 12).map(function (x) { return linhaCompacta(x, "data-fila-id"); }).join("") +
      (outras.length > 12 ? '<p class="texto-apoio">e mais ' + (outras.length - 12) + "</p>" : ""), "fila-lista");
    setTexto($("fila-contagem"), n ? (n === 1 ? "1 peça aguardando" : n + " peças aguardando") : "");
    mostrar($("fila-peca"), !!ev);
    mostrar($("fila-vazia"), !ev);
    mostrar($("fila-pular"), n > 1);
    if (!ev) return;

    var img = $("fila-img");
    if (img) img.src = ev.imagem || PIXEL_VAZIO;
    var falha = ev.e_falha != null ? !!ev.e_falha : ev.classe_key !== "normal";
    var caixa = $("fila-peca");
    caixa.classList.toggle("resultado-falha", falha);
    caixa.classList.toggle("resultado-incerto", !falha);
    setTexto($("fila-classe"), falha ? (ev.nome || nomeDaClasse(ev.classe_key)) : "Leitura incerta: parece normal");
    setTexto($("fila-confianca"), "A IA tem " + formatarPercentual(ev.confianca, 0) + " de certeza");
    setTexto($("fila-lote"), ev.lote_codigo ? "Lote " + ev.lote_codigo : "Sem lote");
    setTexto($("fila-hora"), (ev.data ? ev.data.split("-").reverse().slice(0, 2).join("/") + " " : "") + horaCurta(ev));
    $("fila-pular").onclick = function () { fila.puladas[ev.id] = true; mostrarProximaDaFila(); };
    // Depois de conferir, passa sozinha para a próxima.
    montarConferencia($("fila-conferencia"), ev, function () { mostrarProximaDaFila(); });
  }

  function abrirModal(id) {
    var ev = historico.porId[id];
    if (ev) abrirModalEvento(ev);
  }

  function abrirModalEvento(ev) {
    if (!ev) return;
    App.eventoAberto = ev;

    var img = $("modal-img");
    if (img) { img.src = ev.imagem || PIXEL_VAZIO; img.alt = ev.nome_final || ev.nome || ""; }
    atualizarFotoDoModal(ev);

    setTexto($("modal-classe"), ev.nome_final || ev.nome || nomeDaClasse(ev.classe_key));
    setTexto($("modal-confianca"), "IA: " + formatarPercentual(ev.confianca, 0) + " de certeza");
    setTexto($("modal-hora"), (ev.data ? ev.data.split("-").reverse().join("/") + " " : "") + horaCurta(ev));
    setTexto($("modal-lote"), ev.lote_codigo ? "Lote " + ev.lote_codigo : "Sem lote");

    montarConferencia($("modal-conferencia"), ev, function (salvo) {
      setTexto($("modal-classe"), salvo.nome_final);
      if (historico.porId[salvo.id]) Object.assign(historico.porId[salvo.id], salvo);
      if (App.pagina === "historico") carregarHistorico();
    });

    var diag = $("modal-diagnostico");
    if (diag) setHTML(diag, ev.diagnostico ? htmlDiagnostico(ev.diagnostico) : "", "modal-diagnostico");

    var modal = $("modal-evento");
    if (modal) {
      modal.hidden = false;
      modal.setAttribute("aria-hidden", "false");
      document.body.classList.add("modal-aberto");
      var fechar = $("btn-modal-fechar");
      if (fechar) fechar.focus();
    }
  }

  /** Excluir a peça inteira. O primeiro clique pede confirmação; não há como desfazer. */
  function desarmarExcluir() {
    var btn = $("btn-modal-excluir");
    if (!btn) return;
    btn.classList.remove("confirmando");
    btn.innerHTML = "<span>Excluir peça</span>";
    mostrar($("btn-modal-cancelar-excluir"), false);
    setTexto($("modal-excluir-texto"), "Excluir tira a peça do histórico, dos números, do lote e do banco.");
  }

  function excluirDoModal() {
    var ev = App.eventoAberto;
    var btn = $("btn-modal-excluir");
    if (!ev || !btn) return;
    if (!btn.classList.contains("confirmando")) {
      btn.classList.add("confirmando");
      btn.innerHTML = "<span>Excluir de vez</span>";
      mostrar($("btn-modal-cancelar-excluir"), true);
      setTexto($("modal-excluir-texto"), "Tem certeza? Não dá para desfazer.");
      return;
    }
    botaoCarregando(btn, true, "Excluindo...");
    fetchJSON("/api/eventos/" + encodeURIComponent(ev.id), { method: "DELETE", timeout: 30000 })
      .then(function (d) {
        botaoCarregando(btn, false);
        desarmarExcluir();
        delete historico.porId[ev.id];
        fecharModal();
        var aviso = d && d.nuvem && d.nuvem.erro;
        toast(aviso ? "Peça excluída aqui, mas o banco não respondeu: " + aviso : "Peça excluída.", aviso ? "aviso" : "ok");
        atualizarPendentes();
        carregarRecentes();
        if (App.pagina === "historico") carregarHistorico();
        if (App.pagina === "conferir") carregarFila();
      })
      .catch(function (e) {
        botaoCarregando(btn, false);
        desarmarExcluir();
        toast("Não consegui excluir: " + e.message, "erro");
      });
  }

  function fecharModal() {
    var modal = $("modal-evento");
    if (!modal || modal.hidden) return;
    modal.hidden = true;
    modal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("modal-aberto");
    App.eventoAberto = null;
  }

  /** Mostra/esconde o botão "Apagar foto" e o aviso "Foto apagada" no detalhe. */
  function atualizarFotoDoModal(ev) {
    var temFoto = !!(ev && ev.imagem);
    var midia = document.querySelector("#modal-evento .modal-midia");
    if (midia) midia.classList.toggle("sem-foto", !temFoto);
    var btn = $("btn-modal-apagar-foto");
    if (btn) {
      desarmarApagarFoto(btn);
      btn.hidden = !temFoto;
    }
    desarmarExcluir();
    setTexto($("modal-foto-texto"), temFoto
      ? "A peça continua no histórico; só a imagem é apagada."
      : "A foto desta peça foi apagada. A inspeção continua contando nos números.");
  }

  function desarmarApagarFoto(btn) {
    if (!btn) return;
    btn.classList.remove("confirmando");
    mostrar($("btn-modal-cancelar-apagar"), false);
    if (btn.dataset.rotuloOriginal != null && !btn.disabled) {
      btn.innerHTML = btn.dataset.rotuloOriginal;
      delete btn.dataset.rotuloOriginal;
    }
  }

  /**
   * Apagar a foto de um evento. O primeiro clique pede confirmação ("Apagar de
   * vez" ou "Cancelar"); não há como desfazer.
   */
  function apagarFotoDoModal() {
    var ev = App.eventoAberto;
    var btn = $("btn-modal-apagar-foto");
    if (!ev || !btn || !ev.imagem) return;

    if (!btn.classList.contains("confirmando")) {
      btn.dataset.rotuloOriginal = btn.innerHTML;
      btn.classList.add("confirmando");
      btn.innerHTML = "<span>Apagar de vez</span>";
      mostrar($("btn-modal-cancelar-apagar"), true);
      return;
    }

    btn.classList.remove("confirmando");
    mostrar($("btn-modal-cancelar-apagar"), false);
    var original = btn.dataset.rotuloOriginal;
    delete btn.dataset.rotuloOriginal;
    btn.innerHTML = original;
    botaoCarregando(btn, true, "Apagando...");

    fetchJSON("/api/eventos/" + encodeURIComponent(ev.id) + "/foto", { method: "DELETE", timeout: 30000 })
      .then(function (d) {
        botaoCarregando(btn, false);
        if (d && d.erro) { toast(d.erro, "erro"); return; }
        ev.imagem = null;
        if (historico.porId[ev.id]) historico.porId[ev.id].imagem = null;
        var nuvem = (d && d.nuvem) || {};
        if (nuvem.erro) toast("Foto apagada deste computador, mas não do banco: " + nuvem.erro, "aviso");
        else toast("Foto apagada.", "ok");
        atualizarFotoDoModal(ev);
        if (App.pagina === "historico") carregarHistorico();
      })
      .catch(function (e) {
        botaoCarregando(btn, false);
        toast("Não consegui apagar a foto: " + e.message, "erro");
      });
  }

  function diagnosticoDoModal() {
    var ev = App.eventoAberto;
    var btn = $("btn-modal-diagnostico");
    if (!ev) return;
    botaoCarregando(btn, true, "Buscando explicação...");
    setHTML($("modal-diagnostico"), '<p class="ia-carregando">Buscando causas e soluções...</p>', "modal-diagnostico");
    postJSON("/api/eventos/" + encodeURIComponent(ev.id) + "/diagnostico", {}, { timeout: 60000 })
      .then(function (d) {
        botaoCarregando(btn, false);
        if (d && d.erro) {
          setHTML($("modal-diagnostico"), '<p class="ia-erro">' + esc(d.erro) + "</p>", "modal-diagnostico");
          return;
        }
        ev.diagnostico = d && d.diagnostico;
        setHTML($("modal-diagnostico"), htmlDiagnostico(ev.diagnostico), "modal-diagnostico");
      })
      .catch(function (e) {
        botaoCarregando(btn, false);
        setHTML($("modal-diagnostico"), '<p class="ia-erro">' + esc(e.message) + "</p>", "modal-diagnostico");
      });
  }

  /* =======================================================================
   * 13. PAGINA AJUSTES
   * ===================================================================== */

  var CAMPOS_AJUSTE = [
    { id: "aj-limiar-alerta", chave: "limiar_alerta", casas: 2 },
    { id: "aj-limiar-incerteza", chave: "limiar_incerteza", casas: 2 },
    { id: "aj-frames", chave: "frames_para_confirmar", casas: 0 },
    { id: "aj-ema", chave: "ema_alpha", casas: 2 }
  ];

  // Cada nível de rigor é só uma combinação pronta dos controles avançados.
  var NIVEIS_RIGOR = {
    baixa: { limiar_alerta: 0.75, limiar_incerteza: 0.6, frames_para_confirmar: 6, ema_alpha: 0.35 },
    normal: { limiar_alerta: 0.55, limiar_incerteza: 0.7, frames_para_confirmar: 4, ema_alpha: 0.45 },
    alta: { limiar_alerta: 0.4, limiar_incerteza: 0.8, frames_para_confirmar: 3, ema_alpha: 0.55 }
  };

  function sincronizarSaida(input) {
    var out = document.querySelector('output[for="' + input.id + '"]');
    if (!out) return;
    var casas = 2;
    CAMPOS_AJUSTE.forEach(function (c) { if (c.id === input.id) casas = c.casas; });
    var v = Number(input.value);
    out.textContent = isFinite(v) ? v.toFixed(casas).replace(".", ",") : input.value;
  }

  function valoresAvancados() {
    var v = {};
    CAMPOS_AJUSTE.forEach(function (c) {
      var input = $(c.id);
      if (input && isFinite(Number(input.value))) v[c.chave] = c.casas === 0 ? Math.round(Number(input.value)) : Number(input.value);
    });
    return v;
  }

  /** Descobre qual nível de rigor bate com os controles avançados. */
  function marcarNivelRigor() {
    var sel = $("aj-sensibilidade");
    if (!sel) return;
    var atual = valoresAvancados();
    var achou = "personalizado";
    Object.keys(NIVEIS_RIGOR).forEach(function (nome) {
      var n = NIVEIS_RIGOR[nome];
      var igual = Object.keys(n).every(function (k) { return Math.abs(numero(atual[k], -1) - n[k]) < 0.001; });
      if (igual) achou = nome;
    });
    sel.value = achou;
    var opt = sel.querySelector('option[value="personalizado"]');
    if (opt) opt.hidden = achou !== "personalizado";
  }

  function aplicarNivelRigor(nome) {
    var n = NIVEIS_RIGOR[nome];
    if (!n) return;
    CAMPOS_AJUSTE.forEach(function (c) {
      var input = $(c.id);
      if (input && n[c.chave] != null) { input.value = String(n[c.chave]); sincronizarSaida(input); }
    });
    marcarNivelRigor();
  }

  function carregarAjustes() {
    return fetchJSON("/api/ajustes")
      .then(function (d) {
        d = d || {};
        CAMPOS_AJUSTE.forEach(function (c) {
          var input = $(c.id);
          if (!input) return;
          if (d[c.chave] != null) input.value = String(d[c.chave]);
          sincronizarSaida(input);
        });
        if ($("aj-meta") && d.meta_pecas != null) $("aj-meta").value = String(d.meta_pecas);
        if ($("aj-limite-ia") && d.leitura_limite_diario != null) $("aj-limite-ia").value = String(d.leitura_limite_diario);
        carregarLeituraIA();
        marcarNivelRigor();
        setTexto($("ajustes-status"), "");
      })
      .catch(function (e) {
        setTexto($("ajustes-status"), "Não consegui ler os ajustes: " + e.message);
      });
  }

  function salvarAjustes() {
    var btn = $("btn-salvar-ajustes");
    var corpo = valoresAvancados();
    var meta = $("aj-meta") && Number($("aj-meta").value);
    if (meta && isFinite(meta)) corpo.meta_pecas = Math.round(meta);
    var limite = $("aj-limite-ia") && $("aj-limite-ia").value !== "" ? Number($("aj-limite-ia").value) : NaN;
    if (isFinite(limite)) corpo.leitura_limite_diario = Math.round(limite);

    botaoCarregando(btn, true, "Salvando...");
    setTexto($("ajustes-status"), "");
    postJSON("/api/ajustes", corpo)
      .then(function (d) {
        botaoCarregando(btn, false);
        if (d && d.erro) { setTexto($("ajustes-status"), d.erro); toast(d.erro, "erro"); return; }
        setTexto($("ajustes-status"), "");
        toast("Ajustes salvos.", "ok");
        carregarLeituraIA();
      })
      .catch(function (e) {
        botaoCarregando(btn, false);
        setTexto($("ajustes-status"), "Falhou: " + e.message);
        toast("Não consegui salvar: " + e.message, "erro");
      });
  }

  /** Cartão "Leitura por IA" em Ajustes: uso do dia, gasto e modelo. */
  function carregarLeituraIA() {
    return fetchJSON("/api/status").then(function (d) {
      var l = (d && d.leitura) || {};
      var ligada = l.modo === "ia";
      var est = $("ia-estado");
      if (est) {
        est.className = "estado " + (ligada ? "estado-ok" : "estado-atencao");
        est.textContent = ligada ? "Ligada" : "Desligada";
      }
      var feitas = numero(l.chamadas, 0), limite = numero(l.limite, 0);
      setTexto($("ia-chamadas"), feitas.toLocaleString("pt-BR"));
      setTexto($("ia-limite"), "de " + limite.toLocaleString("pt-BR") + " leituras hoje");
      var barra = $("ia-barra");
      if (barra) barra.style.width = (limite ? Math.min(100, feitas / limite * 100) : 0).toFixed(1) + "%";
      setTexto($("ia-custo"), "US$ " + numero(l.custo_usd, 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 4 }));
      var nomeModelo = String(l.modelo || "—").split("/").pop().replace(/-/g, " ");
      setTexto($("ia-modelo"), nomeModelo.split(" ").map(function (w) { return w.charAt(0).toUpperCase() + w.slice(1); }).join(" "));
      setTexto($("ia-motivo"), ligada ? "" : (l.motivo || ""));
      mostrar($("ia-motivo"), !ligada && !!l.motivo);
    }).catch(function () {});
  }

  function testarLLM() {
    var btn = $("btn-testar-llm");
    var caixa = $("llm-status");
    botaoCarregando(btn, true, "Testando...");
    setHTML(caixa, '<p class="ia-carregando">Testando a conexão...</p>', "llm-status");
    fetchJSON("/api/llm/status", { timeout: 45000 })
      .then(function (d) {
        botaoCarregando(btn, false);
        d = d || {};
        var ok = !!d.ok;
        setHTML(caixa, '<div class="llm-cartao ' + (ok ? "llm-ok" : "llm-erro") + '">' +
          '<span class="selo-fonte ' + (ok ? "selo-ok" : "selo-nao") + '">' +
          '<span class="selo-icone" aria-hidden="true">' + (ok ? ICONES.check : ICONES.erro) + "</span>" +
          esc(ok ? "OpenRouter respondeu" : "Sem conexão") + "</span>" +
          (ok ? "" : '<p class="llm-mensagem">' + esc(d.mensagem || "Sem conexão com o OpenRouter.") + "</p>") + "</div>", "llm-status");
      })
      .catch(function (e) {
        botaoCarregando(btn, false);
        setHTML(caixa, '<div class="llm-cartao llm-erro"><p class="llm-mensagem">' + esc(e.message) + "</p></div>", "llm-status");
      });
  }

  /* =======================================================================
   * 13b. BANCO E LOTE EM PRODUCAO
   * ===================================================================== */

  function formatarData(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
    return m ? m[3] + "/" + m[2] + "/" + m[1] : "--";
  }

  /* --- Situação do banco (chip da barra + card em Ajustes) --------------- */

  function iniciarMonitorBanco() {
    atualizarBanco(false).then(function () {
      setTimeout(iniciarMonitorBanco, INTERVALO_BANCO_MS);
    });
  }

  function atualizarBanco(forcar) {
    return fetchJSON("/api/db/status" + (forcar ? "?forcar=true" : ""), { timeout: 20000 })
      .then(function (d) {
        App.banco = d || {};
        renderBanco(App.banco);
        if ("lote_ativo" in App.banco) renderChipLote(App.banco.lote_ativo);
      })
      .catch(function (e) {
        App.banco = null;
        renderBanco({ configurado: false, erro: e.message, servidorFora: true });
      });
  }

  function renderBanco(d) {
    var chip = $("chip-banco");
    var pend = numero(d.pendentes, 0);
    var classe = "";
    var texto = "Dados neste computador";
    var titulo = "Banco não configurado: as inspeções ficam guardadas neste computador.";
    if (d.configurado) {
      if (d.conectado && pend === 0) {
        classe = "estado-ok"; texto = "Banco conectado";
        titulo = "Inspeções sendo enviadas ao banco.";
      } else if (d.conectado) {
        classe = "estado-atencao"; texto = "Enviando " + pend;
        titulo = pend + " inspeções aguardando envio.";
      } else {
        classe = "estado-atencao";
        texto = "Banco sem conexão" + (pend ? " (" + pend + ")" : "");
        titulo = "Sem conexão com o banco. As inspeções ficam guardadas e sobem quando a conexão voltar.";
      }
    }
    if (chip) {
      chip.className = "menu-estado " + classe;
      chip.title = titulo;
      setTexto(chip.querySelector(".chip-texto"), texto);
    }

    var caixa = $("banco-status");
    if (!caixa) return;
    if (!d.configurado) {
      setHTML(caixa, "<p>As inspeções ficam guardadas neste computador. Para guardar também na nuvem, " +
        "configure o Supabase no .env (veja o README).</p>", "banco-status");
      return;
    }
    var st = d.storage || {};
    var sinc = d.sincronizacao || {};
    function linha(nome, ok, texto) {
      return '<li><span>' + esc(nome) + '</span><span class="estado ' + (ok ? "estado-ok" : "estado-atencao") + '">' + esc(texto) + "</span></li>";
    }
    var linhas = [
      linha("Banco (Supabase)", d.conectado, d.conectado ? "Conectado" : "Sem conexão"),
      linha("Fotos de defeito", st.ok, st.ok ? "Sendo enviadas" : "Sem envio"),
      linha("Aguardando envio", pend === 0, pend === 0 ? "Nada" : String(pend))
    ];
    var erro = !d.conectado ? d.erro : (sinc.ultimo_erro || (!st.ok && st.erro));
    setHTML(caixa, '<ul class="conexoes">' + linhas.join("") + "</ul>" +
      (erro ? '<p class="conexoes-erro">' + esc(erro) + "</p>" : ""), "banco-status");
  }

  /* --- Lote em inspeção (seletor da tela Inspecionar) ------------------- */

  function renderChipLote(lote) {
    App.lotes.ativo = lote || null;
    var sel = $("sel-lote");
    if (sel) {
      var id = lote && lote.id != null ? String(lote.id) : "";
      // O lote ativo pode não estar na lista (ex.: sem internet agora).
      if (id && !sel.querySelector('option[value="' + id.replace(/"/g, "") + '"]')) {
        var opt = criar("option", null, lote.codigo + (lote.cliente ? " · " + lote.cliente : ""));
        opt.value = id;
        sel.appendChild(opt);
      }
      if (document.activeElement !== sel) sel.value = id;
    }
    mostrar($("aviso-sem-lote"), !lote && App.lotes.lista.length > 0);
  }

  function carregarLotes() {
    return fetchJSON("/api/lotes")
      .then(function (d) {
        App.lotes.lista = (d && d.lotes) || [];
        App.lotes.ativo = (d && d.ativo) || null;
        renderLotes();
      })
      .catch(function () {
        App.lotes.lista = [];
        renderLotes();
      });
  }

  function renderLotes() {
    var sel = $("sel-lote");
    if (!sel) return;
    var html = '<option value="">Sem lote</option>' + App.lotes.lista.map(function (l) {
      return '<option value="' + esc(l.id) + '">' + esc(l.codigo) + " · " + esc(l.cliente) + "</option>";
    }).join("");
    setHTML(sel, html, "sel-lote");
    renderChipLote(App.lotes.ativo);
  }

  function usarLote(id) {
    return postJSON("/api/lotes/" + encodeURIComponent(id) + "/inspecionar", {})
      .then(function (d) {
        renderChipLote(d.lote);
        toast("As próximas peças vão para o lote " + d.lote.codigo + ".", "ok");
        return d.lote;
      })
      .catch(function (e) {
        renderChipLote(App.lotes.ativo);
        toast("Não consegui escolher o lote: " + e.message, "erro");
        throw e;
      });
  }

  function pararLote() {
    return postJSON("/api/lotes/ativo", {})
      .then(function () {
        renderChipLote(null);
        toast("As próximas peças ficam sem lote.", "info");
      })
      .catch(function (e) { toast("Não consegui parar: " + e.message, "erro"); });
  }

  /* --- Página Lotes ------------------------------------------------------ */

  var Lotes = { lista: [], escolhido: null };

  function pctBR(v) { return (Math.round(v * 1000) / 10).toLocaleString("pt-BR") + "%"; }
  function numBR(v) { return Number(v || 0).toLocaleString("pt-BR"); }

  function carregarPaginaLotes() {
    var todos = $("lotes-concluidos") && $("lotes-concluidos").checked;
    return fetchJSON("/api/lotes" + (todos ? "?todos=true" : ""))
      .then(function (d) {
        Lotes.lista = d.lotes || [];
        App.lotes.ativo = d.ativo || null;
        var erro = $("lotes-erro");
        setTexto(erro, d.disponivel === false ? d.erro : "");
        mostrar(erro, d.disponivel === false);
        $("btn-novo-lote").disabled = d.disponivel === false;
        renderListaLotes(d.disponivel !== false);
        if (Lotes.escolhido) abrirLote(Lotes.escolhido, true);
      })
      .catch(function (e) {
        setTexto($("lotes-erro"), "Não consegui carregar os lotes: " + e.message);
        mostrar($("lotes-erro"), true);
      });
  }

  function renderListaLotes(disponivel) {
    var tem = Lotes.lista.length > 0;
    mostrar($("lotes-bloco"), tem);
    mostrar($("lotes-vazio"), disponivel && !tem);
    var ativo = App.lotes.ativo && App.lotes.ativo.id;
    setHTML($("lista-lotes"), Lotes.lista.map(function (l) {
      var situacao = l.concluido ? '<span class="estado estado-neutro">Concluído</span>'
        : l.id === ativo ? '<span class="estado estado-ok">Inspecionando agora</span>'
        : '<span class="estado estado-neutro">Aberto</span>';
      var feito = l.quantidade ? Math.min(1, l.inspecionadas / l.quantidade) : 0;
      var defeito = l.inspecionadas
        ? '<span class="num">' + numBR(l.reprovadas) + "</span> <small>" + pctBR(l.taxa_defeito) + "</small>"
        : '<small class="texto-apoio">—</small>';
      return '<button type="button" class="linha linha-lote linha-clicavel' + (Lotes.escolhido === l.id ? " selecionada" : "") +
        '" data-lote-id="' + esc(l.id) + '">' +
        "<span><strong>" + esc(l.codigo) + "</strong><small>" + esc(l.cliente) + (l.modelo_peca ? " · " + esc(l.modelo_peca) : "") + "</small></span>" +
        '<span class="lote-feito"><span class="num">' + numBR(l.inspecionadas) + " de " + numBR(l.quantidade) +
          '</span><span class="progresso"><i style="width:' + (feito * 100).toFixed(1) + '%"></i></span></span>' +
        "<span>" + defeito + "</span>" +
        "<span>" + situacao + "</span></button>";
    }).join(""), "lista-lotes");
  }

  function abrirLote(id, silencioso) {
    Lotes.escolhido = id;
    $$("#lista-lotes .linha").forEach(function (el) {
      el.classList.toggle("selecionada", String(el.getAttribute("data-lote-id")) === String(id));
    });
    mostrar($("form-lote"), false);
    return fetchJSON("/api/lotes/" + encodeURIComponent(id))
      .then(renderDetalheLote)
      .catch(function (e) {
        if (!silencioso) toast("Não consegui abrir o lote: " + e.message, "erro");
      });
  }

  function renderDetalheLote(d) {
    var l = d.lote, caixa = $("lote-detalhe");
    var maior = d.defeitos.length ? d.defeitos[0].quantidade : 0;
    var defeitos = d.defeitos.length ? '<ul class="lote-defeitos">' + d.defeitos.map(function (x) {
      return "<li><span>" + esc(x.nome) + '</span><span class="num">' + numBR(x.quantidade) + "</span>" +
        '<span class="progresso"><i style="width:' + (maior ? x.quantidade / maior * 100 : 0).toFixed(1) + '%"></i></span></li>';
    }).join("") + "</ul>"
      : '<p class="texto-apoio">' + (l.inspecionadas ? "Nenhum defeito encontrado até agora." : "Nenhuma peça inspecionada neste lote ainda.") + "</p>";
    var acoes = [];
    if (!l.concluido) {
      acoes.push(l.ativo
        ? '<button type="button" class="btn btn-secundario" data-lote-acao="parar">Parar de inspecionar este lote</button>'
        : '<button type="button" class="btn btn-principal" data-lote-acao="inspecionar">Inspecionar este lote</button>');
    }
    acoes.push('<a class="btn btn-secundario" href="/api/lotes/' + esc(l.id) + '/pdf" download>Relatório de qualidade (PDF)</a>');
    acoes.push(l.concluido
      ? '<button type="button" class="btn-link" data-lote-acao="reabrir">Reabrir lote</button>'
      : '<button type="button" class="btn-link" data-lote-acao="concluir">Concluir lote</button>');
    setHTML(caixa,
      '<div class="bloco-cabecalho"><div><h2>' + esc(l.codigo) + '</h2><p class="texto-apoio">' + esc(l.cliente) +
        (l.modelo_peca ? " · " + esc(l.modelo_peca) : "") + "</p></div>" +
        (l.concluido ? '<span class="estado estado-neutro">Concluído</span>'
          : l.ativo ? '<span class="estado estado-ok">Inspecionando agora</span>' : "") + "</div>" +
      '<dl class="lote-numeros">' +
        "<div><dt>Inspecionadas</dt><dd>" + numBR(l.inspecionadas) + " <small>de " + numBR(l.quantidade) + "</small></dd></div>" +
        "<div><dt>Aprovadas</dt><dd>" + numBR(l.aprovadas) + "</dd></div>" +
        "<div><dt>Com defeito</dt><dd>" + numBR(l.reprovadas) + (l.inspecionadas ? " <small>" + pctBR(l.taxa_defeito) + "</small>" : "") + "</dd></div>" +
      "</dl>" +
      "<h3>Defeitos encontrados</h3>" + defeitos +
      '<div class="lote-acoes">' + acoes.join("") + "</div>", "lote-detalhe");
    mostrar(caixa, true);
    mostrar($("lote-dica"), false);
  }

  function acaoLote(acao) {
    var id = Lotes.escolhido;
    if (!id) return;
    var feito = null;
    if (acao === "inspecionar") {
      usarLote(id).then(function () { irPara("ao-vivo"); }).catch(function () {});
      return;
    } else if (acao === "parar") {
      feito = pararLote();
    } else if (acao === "concluir") {
      if (!confirm("Concluir este lote? Ele sai da lista de lotes em aberto e não recebe mais peças.")) return;
      feito = postJSON("/api/lotes/" + id + "/concluir", {}).then(function () { toast("Lote concluído.", "ok"); });
    } else if (acao === "reabrir") {
      feito = postJSON("/api/lotes/" + id + "/reabrir", {}).then(function () { toast("Lote reaberto.", "ok"); });
    }
    if (feito) feito.then(carregarPaginaLotes).catch(function (e) { toast(e.message, "erro"); });
  }

  function abrirFormLote() {
    Lotes.escolhido = null;
    $$("#lista-lotes .linha").forEach(function (el) { el.classList.remove("selecionada"); });
    mostrar($("lote-detalhe"), false);
    mostrar($("lote-dica"), false);
    var form = $("form-lote");
    form.reset();
    setTexto($("lote-form-erro"), "");
    mostrar(form, true);
    $("lote-codigo").focus();
    fetchJSON("/api/lotes/clientes").then(function (d) {
      setHTML($("lista-clientes"), (d.clientes || []).map(function (c) {
        return '<option value="' + esc(c) + '">';
      }).join(""), "lista-clientes");
    }).catch(function () {});
  }

  function fecharFormLote() {
    mostrar($("form-lote"), false);
    mostrar($("lote-dica"), !Lotes.escolhido);
  }

  function enviarFormLote(ev) {
    ev.preventDefault();
    var corpo = {
      codigo: $("lote-codigo").value.trim(),
      cliente: $("lote-cliente").value.trim(),
      modelo_peca: $("lote-peca").value.trim() || null,
      quantidade: parseInt($("lote-quantidade").value, 10) || 0
    };
    if (!corpo.codigo || !corpo.cliente || corpo.quantidade < 1) {
      setTexto($("lote-form-erro"), "Preencha código, cliente e a quantidade de peças.");
      return;
    }
    var botao = ev.target.querySelector('button[type="submit"]');
    botao.disabled = true;
    postJSON("/api/lotes", corpo)
      .then(function (d) {
        toast("Lote " + d.lote.codigo + " criado.", "ok");
        mostrar($("form-lote"), false);
        Lotes.escolhido = d.lote.id;
        return carregarPaginaLotes();
      })
      .catch(function (e) { setTexto($("lote-form-erro"), e.message); })
      .then(function () { botao.disabled = false; });
  }

  /* =======================================================================
   * 14. INICIALIZACAO E LISTENERS (registrados uma unica vez)
   * ===================================================================== */

  function ligar(el, evento, fn) {
    if (el) el.addEventListener(evento, fn);
  }

  function registrarListeners() {
    /* --- Navegacao: delegacao cobre sidebar e tabbar de uma vez ---------- */
    document.addEventListener("click", function (ev) {
      var item = ev.target.closest ? ev.target.closest(".nav-item[data-pagina]") : null;
      if (item) {
        ev.preventDefault();
        irPara(item.getAttribute("data-pagina"));
        return;
      }
      // Miniaturas do historico
      var celula = ev.target.closest ? ev.target.closest(".celula[data-id]") : null;
      if (celula) {
        abrirModal(celula.getAttribute("data-id"));
        return;
      }
      // Peça escolhida na lateral da fila: passa a ser a conferida agora
      var naFila = ev.target.closest ? ev.target.closest("[data-fila-id]") : null;
      if (naFila) {
        fila.escolhida = naFila.getAttribute("data-fila-id");
        mostrarProximaDaFila();
        var peca = $("fila-peca");
        if (peca && peca.scrollIntoView) peca.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    });

    window.addEventListener("hashchange", function () {
      irPara(paginaDoHash(), false);
    });

    /* --- Ao vivo -------------------------------------------------------- */
    ligar($("btn-camera"), "click", alternarCamera);
    ligar($("sel-camera"), "change", function () {
      // Trocar de dispositivo com a camera ligada exige reabrir o stream.
      if (App.cameraAtiva) {
        desligarCamera().then(ligarCamera);
      }
    });
    ligar($("toggle-gradcam"), "change", function (e) { alternarGradcam(e.target.checked); });
    ligar($("btn-capturar"), "click", function () { capturarQuadro(false).catch(function () {}); });
    ligar($("btn-diagnostico"), "click", pedirDiagnostico);
    ligar($("btn-conferir-ultimo"), "click", function () { abrirModalEvento(App.ultimoEvento); });
    // A câmera começa fechada; abre de novo se a pessoa deixou aberta.
    function abrirCamera(aberta) {
      mostrar($("camera-corpo"), aberta);
      var b = $("btn-mostrar-camera");
      if (b) { b.textContent = aberta ? "Fechar câmera" : "Abrir câmera"; b.setAttribute("aria-expanded", String(aberta)); }
      try { localStorage.setItem("blocoCameraAberto", aberta ? "1" : "0"); } catch (e) {}
    }
    var salvo = null;
    try { salvo = localStorage.getItem("blocoCameraAberto"); } catch (e) {}
    abrirCamera(salvo === "1");
    ligar($("btn-mostrar-camera"), "click", function () { abrirCamera($("camera-corpo").hidden); });

    // "Ver causas e prevenção" e afins: o botão mostra o bloco logo depois dele.
    document.addEventListener("click", function (e) {
      var b = e.target.closest("[data-alternar]");
      if (!b) return;
      var alvo = b.nextElementSibling;
      if (!alvo) return;
      var abrir = alvo.hidden;
      alvo.hidden = !abrir;
      var outro = b.getAttribute("data-alternar");
      b.setAttribute("data-alternar", b.textContent);
      b.textContent = outro;
      b.setAttribute("aria-expanded", String(abrir));
    });

    var video = $("video-ao-vivo");
    ligar(video, "error", function () {
      if (App.cameraAtiva) toast("A imagem da câmera parou de chegar. Tente religar a câmera.", "erro");
    });

    /* --- Foto ----------------------------------------------------------- */
    [["input-arquivo", "upload"], ["foto-camera", "camera_aparelho"]].forEach(function (par) {
      ligar($(par[0]), "change", function (e) {
        var f = e.target.files && e.target.files[0];
        tratarArquivoEscolhido(f, par[1]);
        e.target.value = ""; // permite reescolher o mesmo arquivo
      });
    });
    var drop = document.querySelector(".card-captura");
    if (drop) {
      ["dragenter", "dragover"].forEach(function (nome) {
        drop.addEventListener(nome, function (e) { e.preventDefault(); drop.classList.add("arrastando"); });
      });
      ["dragleave", "drop"].forEach(function (nome) {
        drop.addEventListener(nome, function (e) {
          e.preventDefault();
          if (nome === "dragleave" && drop.contains(e.relatedTarget)) return;
          drop.classList.remove("arrastando");
        });
      });
      drop.addEventListener("drop", function (e) {
        var f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
        tratarArquivoEscolhido(f, "upload");
      });
    }
    ligar($("ver-foto"), "click", function () { mostrarMidiaResultado(false); });
    ligar($("ver-mapa"), "click", function () { mostrarMidiaResultado(true); });
    ligar($("historico-dia"), "change", carregarHistorico);
    ligar($("historico-modo"), "change", function (e) { mudarModoHistorico(e.target.value); });
    ligar($("historico-tipo"), "change", function (e) { filtrarHistorico(e.target.value); });
    ligar($("sel-lote"), "change", function (e) {
      if (e.target.value) usarLote(e.target.value).catch(function () {});
      else pararLote();
    });

    /* --- Lotes ---------------------------------------------------------- */
    ligar($("btn-novo-lote"), "click", abrirFormLote);
    ligar($("lote-cancelar"), "click", fecharFormLote);
    ligar($("form-lote"), "submit", enviarFormLote);
    ligar($("lotes-concluidos"), "change", carregarPaginaLotes);
    ligar($("lista-lotes"), "click", function (e) {
      var linha = e.target.closest("[data-lote-id]");
      if (linha) abrirLote(Number(linha.getAttribute("data-lote-id")));
    });
    ligar($("lote-detalhe"), "click", function (e) {
      var botao = e.target.closest("[data-lote-acao]");
      if (botao) acaoLote(botao.getAttribute("data-lote-acao"));
    });

    /* --- Historico e modal ---------------------------------------------- */
    ligar($("btn-modal-fechar"), "click", fecharModal);
    ligar($("btn-modal-diagnostico"), "click", diagnosticoDoModal);
    ligar($("btn-modal-apagar-foto"), "click", apagarFotoDoModal);
    ligar($("btn-modal-excluir"), "click", excluirDoModal);
    ligar($("btn-modal-cancelar-excluir"), "click", desarmarExcluir);
    ligar($("btn-modal-cancelar-apagar"), "click", function () { desarmarApagarFoto($("btn-modal-apagar-foto")); });

    var modal = $("modal-evento");
    if (modal) {
      modal.addEventListener("click", function (e) {
        // Clique no overlay (fora do conteudo) fecha o post.
        if (e.target === modal || (e.target.closest && e.target.closest("[data-fechar-modal]"))) {
          fecharModal();
        }
      });
    }
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") fecharModal();
    });


    /* --- Ajustes --------------------------------------------------------- */
    CAMPOS_AJUSTE.forEach(function (campo) {
      var el = $(campo.id);
      ligar(el, "input", function () { sincronizarSaida(el); marcarNivelRigor(); });
    });
    ligar($("aj-sensibilidade"), "change", function (e) { aplicarNivelRigor(e.target.value); });
    ligar($("form-ajustes"), "submit", function (e) { e.preventDefault(); salvarAjustes(); });
    ligar($("btn-testar-llm"), "click", testarLLM);

    /* --- Lotes e banco --------------------------------------------------- */
    ligar($("btn-testar-banco"), "click", function () {
      var btn = $("btn-testar-banco");
      botaoCarregando(btn, true, "Testando...");
      atualizarBanco(true).then(function () { botaoCarregando(btn, false); });
    });

    /* --- Janela ---------------------------------------------------------- */

    document.addEventListener("visibilitychange", function () {
      // Voltar para a aba deve retomar o ritmo de 5 Hz imediatamente.
      if (!document.hidden && App.pagina === "ao-vivo" && App.poll.ativo) {
        if (App.poll.timer) clearTimeout(App.poll.timer);
        App.poll.timer = setTimeout(cicloStatus, 0);
      }
    });

    window.addEventListener("beforeunload", function () {
      pararPolling();
      var img = $("video-ao-vivo");
      if (img) img.removeAttribute("src"); // libera o MJPEG no servidor
    });
  }

  function iniciar() {
    registrarListeners();
    prepararAnel();
    habilitar($("btn-diagnostico"), false);
    habilitar($("btn-conferir-ultimo"), false);
    habilitar($("btn-teste-diagnostico"), false);
    if ($("historico-dia") && !$("historico-dia").value) $("historico-dia").value = hojeISO();
    atualizarPendentes();
    setInterval(atualizarPendentes, 30000);
    atualizarChipCamera({ ativa: false });
    renderVeredito({ estado: "aquecendo" }, null);
    renderChipLote(null);
    iniciarMonitorBanco();

    // A página pedida abre na hora; o resto carrega em segundo plano.
    // Listar câmeras no servidor pode levar segundos e não deve segurar a tela.
    irPara(paginaDoHash(), false);
    var chk = $("toggle-gradcam");
    if (chk) App.gradcamLigado = !!chk.checked;
    carregarTaxonomia()
      .then(function () {
        // Conferência e filtros dependem dos tipos de defeito.
        if (App.pagina === "historico") carregarHistorico();
        if (App.pagina === "conferir") carregarFila();
        return carregarSaude();
      })
      .then(function () { return carregarDispositivos(); });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", iniciar);
  } else {
    iniciar();
  }

  // Um unico ponto de entrada global, so para depuracao no console do navegador.
  window.PontoCerto = {
    estado: App,
    irPara: irPara,
    toast: toast,
    carregarAjustes: carregarAjustes,
    recarregarHistorico: carregarHistorico
  };
})();

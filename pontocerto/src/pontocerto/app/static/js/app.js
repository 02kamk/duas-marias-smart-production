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

  var PAGINAS = ["ao-vivo", "testar", "historico", "treinamento", "relatorios", "ajustes"];
  var PAGINA_PADRAO = "ao-vivo";

  // Intervalo do polling da pagina ao vivo (5 Hz). Encadeado com setTimeout,
  // nunca setInterval, para que uma resposta lenta nao empilhe requisicoes.
  var INTERVALO_STATUS_MS = 200;
  var INTERVALO_STATUS_OCULTO_MS = 1000;

  // Pixel transparente 1x1: placeholder de <img> para nunca mostrar icone de
  // imagem quebrada enquanto a captura real nao existe.
  var PIXEL_VAZIO =
    "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7";

  // Paleta usada apenas pelo Canvas do grafico de treino (o CSS nao alcanca o canvas).
  var COR = {
    terracota: "#C1502E",
    terracotaClaro: "#E08258",
    terracotaEscuro: "#9A3D21",
    barro: "#7C3A1F",
    grafite: "#6B625C",
    grafiteClaro: "#9A918A",
    linha: "#E4DAD1",
    areia: "#F2EAE3",
    osso: "#FAF7F3",
    branco: "#FFFFFF",
    tinta: "#1C1917",
    sage: "#4F7A56"
  };

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
    treino: { dados: null, historico: [], metricas: null },
    relatorioMarkdown: "",
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
    return dois(d.getHours()) + ":" + dois(d.getMinutes()) + ":" + dois(d.getSeconds());
  }

  function formatarDuracao(segundos) {
    var s = Math.max(0, Math.round(numero(segundos, 0)));
    var h = Math.floor(s / 3600);
    var m = Math.floor((s % 3600) / 60);
    var r = s % 60;
    function dois(x) { return x < 10 ? "0" + x : String(x); }
    return (h > 0 ? h + "h " : "") + dois(m) + "min " + dois(r) + "s";
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
          var abortado = new Error(expirou ? "Tempo esgotado ao falar com o servidor." : "Requisicao cancelada.");
          abortado.abortada = true;
          abortado.expirou = expirou;
          throw abortado;
        }
        if (e instanceof TypeError) throw new Error("Nao foi possivel falar com o servidor.");
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
    return PAGINAS.indexOf(bruto) >= 0 ? bruto : PAGINA_PADRAO;
  }

  function irPara(pagina, atualizarHash) {
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
    } else if (pagina === "historico") {
      carregarHistorico();
    } else if (pagina === "treinamento") {
      carregarTreinamento();
    } else if (pagina === "ajustes") {
      carregarAjustes();
    }
    // A pagina "testar" e a "relatorios" nao precisam buscar nada ao entrar.
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
        popularSelectRotulo();
      })
      .catch(function (e) {
        toast("Nao foi possivel carregar a taxonomia: " + e.message, "erro");
      });
  }

  function carregarSaude() {
    return fetchJSON("/api/saude")
      .then(function (d) {
        App.saude = d || {};
        var modelo = (d && d.modelo) || {};
        var llm = (d && d.llm) || {};

        if (!modelo.carregado) {
          toast(
            "Modelo ainda nao treinado. Rode o treino para liberar a inspecao ao vivo." +
            (modelo.erro ? " (" + modelo.erro + ")" : ""),
            "aviso"
          );
        }
        if (!llm.configurado) {
          toast("Sem chave do OpenRouter: os diagnosticos usarao a base tecnica local.", "aviso");
        }
        atualizarChipCamera((d && d.camera) || {});
      })
      .catch(function (e) {
        toast("Servidor indisponivel: " + e.message, "erro");
      });
  }

  function carregarDispositivos() {
    var sel = $("sel-camera");
    if (!sel) return Promise.resolve();
    return fetchJSON("/api/camera/dispositivos")
      .then(function (d) {
        var lista = (d && d.dispositivos) || [];
        sel.innerHTML = "";
        if (!lista.length) {
          var vazia = criar("option", null, "Nenhuma camera encontrada");
          vazia.value = "";
          sel.appendChild(vazia);
          habilitar(sel, false);
          return;
        }
        habilitar(sel, true);
        lista.forEach(function (indice, i) {
          var opt = criar("option", null, "Camera " + indice);
          opt.value = String(indice);
          if (i === 0) opt.selected = true;
          sel.appendChild(opt);
        });
      })
      .catch(function () {
        sel.innerHTML = "";
        var opt = criar("option", null, "Camera 0");
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
      if (info.erro) texto = "Camera com erro";
      else if (ativa) {
        texto = "Camera " + (info.indice == null ? "" : info.indice) + " - " +
          (info.largura || "?") + "x" + (info.altura || "?");
        if (info.fps_real) texto += " - " + Number(info.fps_real).toFixed(0) + " fps";
      } else texto = "Camera desligada";
      setTexto(chip, texto);
      chip.classList.toggle("chip-ligada", ativa && !info.erro);
      chip.classList.toggle("chip-desligada", !ativa || !!info.erro);
      chip.setAttribute("data-estado", info.erro ? "erro" : (ativa ? "ligada" : "desligada"));
    }

    var btn = $("btn-camera");
    if (btn) {
      btn.setAttribute("aria-pressed", ativa ? "true" : "false");
      btn.classList.toggle("ligado", ativa);
      var rotulo = btn.querySelector(".btn-rotulo");
      if (rotulo) setTexto(rotulo, ativa ? "Parar camera" : "Ligar camera");
      else if (!btn.querySelector("svg")) setTexto(btn, ativa ? "Parar camera" : "Ligar camera");
      btn.setAttribute("aria-label", ativa ? "Parar a camera" : "Ligar a camera");
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
          var msg = (d.camera && d.camera.erro) || d.erro || "Nao foi possivel abrir a camera.";
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
        toast("Camera ligada.", "ok");
      })
      .catch(function (e) {
        habilitar(btn, true);
        toast("Falha ao ligar a camera: " + e.message, "erro");
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
        toast("Camera desligada.", "info");
      })
      .catch(function (e) {
        habilitar(btn, true);
        atualizarChipCamera({ ativa: false });
        toast("Falha ao desligar a camera: " + e.message, "erro");
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
        toast("Nao foi possivel mudar o mapa de calor: " + e.message, "erro");
      });
  }

  /**
   * Captura o quadro atual do MJPEG desenhando a <img> num canvas e manda para
   * /api/analisar. Como o stream e da mesma origem, o canvas nao fica "tainted".
   * O resultado abre na pagina Testar, que ja sabe exibir predicao e heatmap.
   */
  function capturarQuadro() {
    var img = $("video-ao-vivo");
    if (!App.cameraAtiva || !img || !img.naturalWidth) {
      toast("Ligue a camera antes de capturar.", "aviso");
      return;
    }
    var btn = $("btn-capturar");
    var canvas = document.createElement("canvas");
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    try {
      canvas.getContext("2d").drawImage(img, 0, 0);
    } catch (e) {
      toast("Nao foi possivel capturar o quadro.", "erro");
      return;
    }
    botaoCarregando(btn, true, "Capturando...");
    canvas.toBlob(function (blob) {
      if (!blob) {
        botaoCarregando(btn, false);
        toast("Captura vazia.", "erro");
        return;
      }
      var arquivo = new File([blob], "captura.jpg", { type: "image/jpeg" });
      enviarParaAnalise(arquivo)
        .then(function () {
          botaoCarregando(btn, false);
          irPara("testar");
        })
        .catch(function () { botaoCarregando(btn, false); });
    }, "image/jpeg", 0.92);
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

    renderVeredito(veredito, predicao);
    renderTop(predicao);
    renderEstatisticas(stats);

    if (d.camera) atualizarChipCamera(d.camera);

    var fps = $("fps");
    if (fps) {
      var v = numero(d.fps, 0).toFixed(1).replace(".", ",");
      setTexto(fps, v + " fps");
    }

    var ev = d.ultimo_evento || null;
    var novoId = ev && ev.id ? ev.id : null;
    if (novoId !== App.ultimoEventoId) {
      App.ultimoEventoId = novoId;
      habilitar($("btn-diagnostico"), !!novoId);
      habilitar($("btn-segunda-opiniao"), !!novoId);
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
    if (estado === "aquecendo") {
      titulo = "Aquecendo";
      sub = "Estabilizando a leitura da costura...";
    } else if (estado === "ok") {
      titulo = "Costura aprovada";
      sub = "Pontos uniformes - " + formatarPercentual(veredito.confianca) + " de confianca";
    } else if (estado === "falha") {
      titulo = veredito.nome || nomeDaClasse(veredito.classe_key);
      sub = "Falha detectada - " + formatarPercentual(veredito.confianca) + " de confianca";
    } else {
      titulo = "Leitura incerta";
      sub = (veredito.nome ? veredito.nome + " - " : "") +
        formatarPercentual(veredito.confianca) + " - vale uma segunda opiniao";
    }

    setTexto($("veredito-titulo"), titulo);
    setTexto($("veredito-sub"), sub);

    var conf = veredito.confianca;
    if (conf == null && predicao) conf = predicao.confianca;
    aplicarAnel(numero(conf, 0));
    setTexto($("anel-valor"), conf == null ? "--" : formatarPercentual(conf));

    // A segunda opiniao so faz sentido quando a rede ficou insegura; mesmo assim
    // o botao continua clicavel, apenas destacado.
    var btnLlm = $("btn-segunda-opiniao");
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
  }

  function renderBarraMeta(s) {
    var barra = $("barra-meta");
    if (!barra) return;
    var meta = Math.max(1, Math.round(numero(s.meta_pecas, 10)));
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
    barra.setAttribute("aria-label", "Progresso da meta: " + numero(s.total, 0) + " de " + meta + " pecas");
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
    el.setAttribute("aria-label", "Sequencia de " + sequencia + " pecas aprovadas");
  }

  /* =======================================================================
   * 08. PAINEL DE IA (DIAGNOSTICO E SEGUNDA OPINIAO)
   * ===================================================================== */

  function seloFonte(fonte, modelo) {
    var eLlm = fonte === "llm";
    return '<span class="selo-fonte ' + (eLlm ? "selo-llm" : "selo-local") + '">' +
      '<span class="selo-icone" aria-hidden="true">' + (eLlm ? ICONES.ia : ICONES.livro) + "</span>" +
      esc(eLlm ? "IA generativa" : "base tecnica local") +
      (eLlm && modelo ? ' <span class="selo-modelo">' + esc(modelo) + "</span>" : "") +
      "</span>";
  }

  function listaHTML(titulo, itens, classe) {
    if (!Array.isArray(itens) || !itens.length) return "";
    var li = itens.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("");
    return '<div class="ia-bloco ' + (classe || "") + '">' +
      '<h4 class="ia-subtitulo">' + esc(titulo) + "</h4>" +
      '<ul class="ia-lista">' + li + "</ul></div>";
  }

  function htmlDiagnostico(diag) {
    if (!diag) return "";
    var html = '<article class="ia-card ia-diagnostico">' +
      '<header class="ia-cabecalho">' +
      '<h3 class="ia-titulo">' + esc(diag.nome || nomeDaClasse(diag.classe_key)) + "</h3>" +
      seloFonte(diag.fonte, diag.modelo) +
      "</header>";
    if (diag.resumo) html += '<p class="ia-resumo">' + esc(diag.resumo) + "</p>";
    html += listaHTML("Causas provaveis", diag.causas, "ia-causas");
    html += listaHTML("O que fazer agora", diag.acoes, "ia-acoes");
    html += listaHTML("Como prevenir", diag.prevencao, "ia-prevencao");
    if (diag.ms) html += '<p class="ia-rodape">Resposta em ' + esc(Math.round(diag.ms)) + " ms</p>";
    html += "</article>";
    return html;
  }

  function htmlRevisao(rev) {
    if (!rev) return "";
    var concorda = rev.concorda;
    var rotulo, classeSelo;
    if (concorda === true) { rotulo = "A IA de visao concordou"; classeSelo = "selo-ok"; }
    else if (concorda === false) { rotulo = "A IA de visao discordou"; classeSelo = "selo-nao"; }
    else { rotulo = "Sem veredito da IA de visao"; classeSelo = "selo-neutro"; }

    var html = '<article class="ia-card ia-revisao">' +
      '<header class="ia-cabecalho">' +
      '<h3 class="ia-titulo">Segunda opiniao</h3>' +
      '<span class="selo-fonte ' + classeSelo + '">' + esc(rotulo) + "</span>" +
      "</header>";

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
    if (rev.modelo) html += '<p class="ia-rodape">' + esc(rev.modelo) +
      (rev.ms ? " - " + esc(Math.round(rev.ms)) + " ms" : "") + "</p>";
    html += "</article>";
    return html;
  }

  function pedirDiagnostico() {
    var id = App.ultimoEventoId;
    var btn = $("btn-diagnostico");
    if (!id) { toast("Nenhum evento registrado ainda.", "aviso"); return; }
    botaoCarregando(btn, true, "Diagnosticando...");
    mostrar($("painel-ia"), true);
    setHTML($("ia-conteudo"), '<p class="ia-carregando">Consultando a base tecnica...</p>', "ia-conteudo");
    postJSON("/api/eventos/" + encodeURIComponent(id) + "/diagnostico", {}, { timeout: 60000 })
      .then(function (d) {
        botaoCarregando(btn, false);
        if (d && d.erro) {
          setHTML($("ia-conteudo"), '<p class="ia-erro">' + esc(d.erro) + "</p>", "ia-conteudo");
          toast(d.erro, "erro");
          return;
        }
        setHTML($("ia-conteudo"), htmlDiagnostico(d && d.diagnostico), "ia-conteudo");
      })
      .catch(function (e) {
        botaoCarregando(btn, false);
        setHTML($("ia-conteudo"), '<p class="ia-erro">' + esc(e.message) + "</p>", "ia-conteudo");
        toast("Diagnostico falhou: " + e.message, "erro");
      });
  }

  function pedirSegundaOpiniao() {
    var id = App.ultimoEventoId;
    var btn = $("btn-segunda-opiniao");
    if (!id) { toast("Nenhum evento registrado ainda.", "aviso"); return; }
    botaoCarregando(btn, true, "Revisando...");
    mostrar($("painel-ia"), true);
    setHTML($("ia-conteudo"), '<p class="ia-carregando">Enviando a imagem para o modelo de visao...</p>', "ia-conteudo");
    postJSON("/api/eventos/" + encodeURIComponent(id) + "/revisao", {}, { timeout: 90000 })
      .then(function (d) {
        botaoCarregando(btn, false);
        if (d && d.erro && !d.revisao) {
          setHTML($("ia-conteudo"), '<p class="ia-erro">' + esc(d.erro) + "</p>", "ia-conteudo");
          toast(d.erro, "erro");
          return;
        }
        setHTML($("ia-conteudo"), htmlRevisao(d && d.revisao), "ia-conteudo");
      })
      .catch(function (e) {
        botaoCarregando(btn, false);
        setHTML($("ia-conteudo"), '<p class="ia-erro">' + esc(e.message) + "</p>", "ia-conteudo");
        toast("Segunda opiniao falhou: " + e.message, "erro");
      });
  }

  /* =======================================================================
   * 09. PAGINA TESTAR
   * ===================================================================== */

  function tratarArquivoEscolhido(arquivo) {
    if (!arquivo) return;
    if (!/^image\//.test(arquivo.type)) {
      toast("Escolha um arquivo de imagem (JPG ou PNG).", "aviso");
      return;
    }
    // Preview local imediato: o operador ve a foto antes de a rede responder.
    var preview = $("preview-teste");
    if (preview) {
      var url = URL.createObjectURL(arquivo);
      if (preview.dataset.blobUrl) URL.revokeObjectURL(preview.dataset.blobUrl);
      preview.dataset.blobUrl = url;
      preview.src = url;
      preview.hidden = false;
    }
    mostrar($("teste-vazio"), false);
    enviarParaAnalise(arquivo);
  }

  function enviarParaAnalise(arquivo) {
    var resultado = $("resultado-teste");
    mostrar(resultado, false);
    setHTML($("teste-ia"), "", "teste-ia");
    setTexto($("teste-classe"), "Analisando...");
    setTexto($("teste-confianca"), "");

    var fd = new FormData();
    fd.append("arquivo", arquivo, arquivo.name || "imagem.jpg");

    return fetchJSON("/api/analisar", { method: "POST", body: fd, timeout: 60000 })
      .then(function (d) {
        if (d && d.erro) {
          toast(d.erro, "erro");
          setTexto($("teste-classe"), "Falhou");
          throw new Error(d.erro);
        }
        App.analiseAtual = d || {};
        renderResultadoTeste(App.analiseAtual);
        return App.analiseAtual;
      })
      .catch(function (e) {
        setTexto($("teste-classe"), "Falhou");
        toast("Analise falhou: " + e.message, "erro");
        throw e;
      });
  }

  function renderResultadoTeste(d) {
    var p = d.predicao || {};
    mostrar($("resultado-teste"), true);

    setTexto($("teste-classe"), p.nome || nomeDaClasse(p.classe_key));
    setTexto($("teste-confianca"), formatarPercentual(p.confianca, 1) + " de confianca" +
      (p.ms ? " - " + Math.round(p.ms) + " ms" : ""));

    var caixa = $("resultado-teste");
    if (caixa) {
      caixa.classList.toggle("resultado-ok", p.e_falha === false);
      caixa.classList.toggle("resultado-falha", p.e_falha === true);
      caixa.setAttribute("data-gravidade", p.gravidade || "");
    }

    var topo = $("teste-top");
    if (topo) {
      var itens = Array.isArray(p.top) ? p.top : [];
      var html = itens.map(function (item) {
        var pct = limitar(numero(item.prob, 0) * 100, 0, 100);
        return '<li class="barra-item" data-classe="' + esc(item.key) + '">' +
          '<div class="barra-linha">' +
          '<span class="barra-nome">' + esc(item.nome || nomeDaClasse(item.key)) + "</span>" +
          '<span class="barra-valor">' + esc(formatarPercentual(item.prob, 1)) + "</span>" +
          "</div>" +
          '<div class="barra-trilho"><div class="barra-preenche" style="width:' +
          pct.toFixed(1) + '%"></div></div>' +
          "</li>";
      }).join("");
      setHTML(topo, html, "teste-top");
    }

    var heat = $("teste-heatmap");
    if (heat) {
      if (d.heatmap) { heat.src = d.heatmap; heat.hidden = false; }
      else { heat.src = PIXEL_VAZIO; heat.hidden = true; }
    }

    // Se a API tambem devolveu a imagem processada, usamos ela no preview
    // (ja vem no tamanho que a rede enxergou).
    var preview = $("preview-teste");
    if (preview && d.imagem) {
      preview.src = d.imagem;
      preview.hidden = false;
    }

    habilitar($("btn-teste-diagnostico"), true);
  }

  /**
   * Diagnostico da classe prevista na aba Testar.
   * A rota oficial e por evento; quando a analise avulsa nao gera evento,
   * tentamos a rota generica /api/diagnostico. Se nenhuma existir, avisamos
   * sem quebrar a interface.
   */
  function diagnosticoDoTeste() {
    var d = App.analiseAtual;
    var btn = $("btn-teste-diagnostico");
    if (!d || !d.predicao) { toast("Analise uma imagem primeiro.", "aviso"); return; }
    var p = d.predicao;
    var eventoId = d.evento_id || (d.evento && d.evento.id) || null;

    botaoCarregando(btn, true, "Diagnosticando...");
    setHTML($("teste-ia"), '<p class="ia-carregando">Consultando a base tecnica...</p>', "teste-ia");

    var pedido = eventoId
      ? postJSON("/api/eventos/" + encodeURIComponent(eventoId) + "/diagnostico", {}, { timeout: 60000 })
      : postJSON("/api/diagnostico", { classe_key: p.classe_key, confianca: p.confianca }, { timeout: 60000 });

    pedido
      .then(function (r) {
        botaoCarregando(btn, false);
        var diag = (r && r.diagnostico) || r;
        if (!diag || diag.erro) {
          var msg = (diag && diag.erro) || "Diagnostico indisponivel.";
          setHTML($("teste-ia"), '<p class="ia-erro">' + esc(msg) + "</p>", "teste-ia");
          return;
        }
        setHTML($("teste-ia"), htmlDiagnostico(diag), "teste-ia");
      })
      .catch(function (e) {
        botaoCarregando(btn, false);
        var aviso = e.status === 404
          ? "Esta versao do servidor so diagnostica eventos registrados ao vivo."
          : e.message;
        setHTML($("teste-ia"), '<p class="ia-erro">' + esc(aviso) + "</p>", "teste-ia");
        toast(aviso, "aviso");
      });
  }

  /* =======================================================================
   * 10. PAGINA HISTORICO
   * ===================================================================== */

  var historico = { eventos: [], filtro: null, porId: {} };

  function carregarHistorico() {
    var params = "?limite=200";
    if (historico.filtro) params += "&classe=" + encodeURIComponent(historico.filtro);
    return fetchJSON("/api/eventos" + params)
      .then(function (d) {
        historico.eventos = (d && d.eventos) || [];
        historico.porId = {};
        historico.eventos.forEach(function (ev) { if (ev && ev.id) historico.porId[ev.id] = ev; });
        renderStories(historico.eventos, (d && d.estatisticas) || {});
        renderGrade(historico.eventos);
      })
      .catch(function (e) {
        toast("Nao consegui carregar o historico: " + e.message, "erro");
      });
  }

  function renderStories(eventos, stats) {
    var caixa = $("stories");
    if (!caixa) return;

    // Contagem por classe: prefere a estatistica do servidor, mas cai para a
    // contagem local quando o filtro esta ativo (a lista vem filtrada).
    var contagem = {};
    var capa = {};
    eventos.forEach(function (ev) {
      if (!ev || !ev.classe_key) return;
      contagem[ev.classe_key] = (contagem[ev.classe_key] || 0) + 1;
      if (!capa[ev.classe_key] && ev.imagem) capa[ev.classe_key] = ev.imagem;
    });
    var porClasse = (stats && stats.por_classe) || null;
    if (porClasse && !historico.filtro) contagem = porClasse;

    var total = 0;
    Object.keys(contagem).forEach(function (k) { total += numero(contagem[k], 0); });

    var partes = [];
    partes.push(storyHTML("tudo", "Tudo", total, eventos.length ? eventos[0].imagem : null, historico.filtro === null));

    App.classes.forEach(function (c) {
      var n = numero(contagem[c.key], 0);
      if (!n && historico.filtro !== c.key) return; // so mostra classes com ocorrencia
      partes.push(storyHTML(c.key, c.nome, n, capa[c.key], historico.filtro === c.key));
    });

    setHTML(caixa, partes.join(""), "stories");
  }

  function storyHTML(chave, nome, contagem, imagem, ativo) {
    return '<button type="button" class="story' + (ativo ? " ativo" : "") +
      '" data-classe="' + esc(chave) + '" aria-pressed="' + (ativo ? "true" : "false") +
      '" aria-label="' + esc("Filtrar por " + nome + " (" + contagem + ")") + '">' +
      '<span class="story-anel"><img class="story-img" src="' + esc(imagem || PIXEL_VAZIO) +
      '" alt="" loading="lazy"></span>' +
      '<span class="story-nome">' + esc(nome) + "</span>" +
      '<span class="story-contagem">' + esc(contagem) + "</span>" +
      "</button>";
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
      var nome = ev.nome || nomeDaClasse(ev.classe_key);
      var corrigido = ev.rotulo_operador ? " corrigido" : "";
      return '<button type="button" class="celula' + corrigido + '" data-id="' + esc(ev.id) +
        '" data-gravidade="' + esc(ev.gravidade || "") + '" aria-label="' +
        esc(nome + " as " + (ev.hora || formatarHora(ev.timestamp))) + '">' +
        '<img src="' + esc(ev.imagem || PIXEL_VAZIO) + '" alt="" loading="lazy">' +
        '<span class="selo">' + esc(nome) + "</span>" +
        "</button>";
    }).join("");
    setHTML(grade, html, "grade-historico");
  }

  function filtrarHistorico(chave) {
    historico.filtro = (chave === "tudo" || !chave) ? null : chave;
    carregarHistorico();
  }

  function popularSelectRotulo() {
    var sel = $("modal-select-rotulo");
    if (!sel || !App.classes.length) return;
    sel.innerHTML = "";
    App.classes.forEach(function (c) {
      var opt = criar("option", null, c.nome);
      opt.value = c.key;
      sel.appendChild(opt);
    });
  }

  function abrirModal(id) {
    var ev = historico.porId[id];
    if (!ev) return;
    App.eventoAberto = ev;

    var img = $("modal-img");
    if (img) { img.src = ev.imagem || PIXEL_VAZIO; img.alt = esc(ev.nome || ""); }

    var heat = $("modal-heatmap");
    if (heat) {
      var url = ev.heatmap || ev.imagem_heatmap || ev.mapa || null;
      if (url) { heat.src = url; heat.hidden = false; }
      else { heat.src = PIXEL_VAZIO; heat.hidden = true; }
    }

    setTexto($("modal-classe"), ev.nome || nomeDaClasse(ev.classe_key));
    setTexto($("modal-confianca"), formatarPercentual(ev.confianca, 1));
    setTexto($("modal-hora"), ev.hora || formatarHora(ev.timestamp));
    setTexto($("modal-tecido"), ev.tecido || "Tecido nao informado");

    var sel = $("modal-select-rotulo");
    if (sel) sel.value = ev.rotulo_operador || ev.classe_key || "";

    var diag = $("modal-diagnostico");
    if (diag) {
      if (ev.diagnostico) setHTML(diag, htmlDiagnostico(ev.diagnostico), "modal-diagnostico");
      else setHTML(diag, '<p class="ia-vazio">Sem diagnostico ainda. Peca um para esta peca.</p>', "modal-diagnostico");
    }

    var modal = $("modal-evento");
    if (modal) {
      modal.hidden = false;
      modal.setAttribute("aria-hidden", "false");
      document.body.classList.add("modal-aberto");
      var fechar = $("btn-modal-fechar");
      if (fechar) fechar.focus();
    }
  }

  function fecharModal() {
    var modal = $("modal-evento");
    if (!modal || modal.hidden) return;
    modal.hidden = true;
    modal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("modal-aberto");
    App.eventoAberto = null;
  }

  /**
   * Correcao de rotulo pelo operador.
   * Cada correcao vira uma linha em artifacts/correcoes_operador.csv, que e
   * exatamente o insumo do proximo ciclo de re-treino: o operador no chao de
   * fabrica esta rotulando dado novo sem sair da tela de inspecao.
   */
  function enviarRotulo(chave, botao) {
    var ev = App.eventoAberto;
    if (!ev) return;
    if (!chave) { toast("Escolha uma classe.", "aviso"); return; }
    botaoCarregando(botao, true, "Salvando...");
    postJSON("/api/eventos/" + encodeURIComponent(ev.id) + "/rotulo", { classe_key: chave })
      .then(function (d) {
        botaoCarregando(botao, false);
        if (d && d.erro) { toast(d.erro, "erro"); return; }
        ev.rotulo_operador = chave;
        toast("Rotulo registrado para o proximo re-treino.", "ok");
        renderGrade(historico.eventos);
        fecharModal();
      })
      .catch(function (e) {
        botaoCarregando(botao, false);
        toast("Nao consegui salvar o rotulo: " + e.message, "erro");
      });
  }

  function diagnosticoDoModal() {
    var ev = App.eventoAberto;
    var btn = $("btn-modal-diagnostico");
    if (!ev) return;
    botaoCarregando(btn, true, "Diagnosticando...");
    setHTML($("modal-diagnostico"), '<p class="ia-carregando">Consultando...</p>', "modal-diagnostico");
    postJSON("/api/eventos/" + encodeURIComponent(ev.id) + "/diagnostico", {}, { timeout: 60000 })
      .then(function (d) {
        botaoCarregando(btn, false);
        if (d && d.erro) {
          setHTML($("modal-diagnostico"), '<p class="ia-erro">' + esc(d.erro) + "</p>", "modal-diagnostico");
          return;
        }
        var diag = d && d.diagnostico;
        ev.diagnostico = diag;
        setHTML($("modal-diagnostico"), htmlDiagnostico(diag), "modal-diagnostico");
      })
      .catch(function (e) {
        botaoCarregando(btn, false);
        setHTML($("modal-diagnostico"), '<p class="ia-erro">' + esc(e.message) + "</p>", "modal-diagnostico");
      });
  }

  /* =======================================================================
   * 11. PAGINA TREINAMENTO
   * ===================================================================== */

  function carregarTreinamento() {
    return fetchJSON("/api/treino/historico")
      .then(function (d) {
        d = d || {};
        // O servidor pode devolver a lista pura ou um envelope; aceitamos os dois.
        var hist = Array.isArray(d) ? d : (d.historico || d.epocas || d.treino || []);
        if (!Array.isArray(hist)) hist = [];
        var metricas = d.metricas || d.avaliacao || null;

        App.treino.dados = d;
        App.treino.historico = hist;
        App.treino.metricas = metricas;

        var temAlgo = hist.length > 0 || !!metricas;
        mostrar($("treino-vazio"), !temAlgo);
        mostrar($("treino-resumo"), temAlgo);
        if (!temAlgo) return;

        preencherResumoTreino(hist, metricas, d);
        preencherTabelaClasses(metricas);
        desenharGraficoTreino();
        carregarMatrizConfusao(d, metricas);
      })
      .catch(function (e) {
        mostrar($("treino-vazio"), true);
        mostrar($("treino-resumo"), false);
        toast("Sem dados de treino: " + e.message, "aviso");
      });
  }

  function preencherResumoTreino(hist, metricas, bruto) {
    var ultima = hist.length ? hist[hist.length - 1] : {};
    var melhorF1 = 0;
    hist.forEach(function (h) { melhorF1 = Math.max(melhorF1, numero(h.f1_val, 0)); });

    var acc = metricas && metricas.acuracia != null ? metricas.acuracia : ultima.acc_val;
    var f1 = metricas && metricas.macro_f1 != null ? metricas.macro_f1 : (melhorF1 || ultima.f1_val);

    setTexto($("treino-acuracia"), formatarPercentual(acc, 1));
    setTexto($("treino-f1"), formatarPercentual(f1, 1));
    setTexto($("treino-epocas"), hist.length ? hist.length : "--");

    var backbone = (bruto && (bruto.backbone || (bruto.meta && bruto.meta.backbone))) ||
      (App.saude && App.saude.modelo && App.saude.modelo.backbone) || "--";
    setTexto($("treino-backbone"), backbone);
  }

  /** Aceita chaves em portugues (do nosso relatorio) ou em ingles (sklearn). */
  function valorMetrica(obj, nomes) {
    if (!obj) return null;
    for (var i = 0; i < nomes.length; i++) {
      if (obj[nomes[i]] != null) return obj[nomes[i]];
    }
    return null;
  }

  function preencherTabelaClasses(metricas) {
    var tbody = $("tabela-classes");
    if (!tbody) return;
    var porClasse = metricas && (metricas.por_classe || metricas.classes);
    if (!porClasse) {
      setHTML(tbody, '<tr><td colspan="5">Avalie o modelo para ver as metricas por classe.</td></tr>', "tabela-classes");
      return;
    }
    var linhas = [];
    App.classes.forEach(function (c) {
      var m = porClasse[c.key] || porClasse[String(c.index)] || porClasse[c.nome];
      if (!m) return;
      var p = valorMetrica(m, ["precisao", "precision"]);
      var r = valorMetrica(m, ["recall", "revocacao"]);
      var f = valorMetrica(m, ["f1", "f1_score", "f1-score"]);
      var s = valorMetrica(m, ["suporte", "support", "n"]);
      linhas.push(
        "<tr data-classe=\"" + esc(c.key) + "\">" +
        '<th scope="row">' + esc(c.nome) + "</th>" +
        "<td>" + esc(formatarPercentual(p, 1)) + "</td>" +
        "<td>" + esc(formatarPercentual(r, 1)) + "</td>" +
        "<td>" + esc(formatarPercentual(f, 1)) + "</td>" +
        "<td>" + esc(s == null ? "--" : s) + "</td>" +
        "</tr>"
      );
    });
    if (!linhas.length) linhas.push('<tr><td colspan="5">Sem metricas por classe.</td></tr>');
    setHTML(tbody, linhas.join(""), "tabela-classes");
  }

  function carregarMatrizConfusao(bruto, metricas) {
    var img = $("matriz-img");
    if (!img) return;
    var url = (bruto && (bruto.matriz_confusao || bruto.matriz || bruto.matriz_url)) ||
      (metricas && (metricas.matriz_confusao || metricas.matriz_url)) || null;
    if (!url) { img.hidden = true; img.removeAttribute("src"); return; }
    img.onerror = function () { img.hidden = true; };
    img.onload = function () { img.hidden = false; };
    img.src = url;
  }

  /* --- Grafico de treino em Canvas 2D puro ------------------------------ */

  function desenharGraficoTreino() {
    var canvas = $("grafico-treino");
    var hist = App.treino.historico;
    if (!canvas || !canvas.getContext || !hist || !hist.length) return;

    var ctx = canvas.getContext("2d");
    var dpr = window.devicePixelRatio || 1;
    var caixa = canvas.getBoundingClientRect();
    var larguraCss = Math.max(280, Math.round(caixa.width || canvas.clientWidth || 640));
    var alturaCss = Math.max(180, Math.round(caixa.height || canvas.clientHeight || 280));

    // devicePixelRatio correto: buffer em pixels fisicos, desenho em pixels CSS.
    canvas.width = Math.round(larguraCss * dpr);
    canvas.height = Math.round(alturaCss * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, larguraCss, alturaCss);

    var padE = 48, padD = 48, padT = 28, padB = 42;
    var larg = larguraCss - padE - padD;
    var alt = alturaCss - padT - padB;
    if (larg < 40 || alt < 40) return;

    var n = hist.length;
    var perdas = [];
    hist.forEach(function (h) {
      if (h.perda_treino != null) perdas.push(numero(h.perda_treino, 0));
      if (h.perda_val != null) perdas.push(numero(h.perda_val, 0));
    });
    var perdaMax = perdas.length ? Math.max.apply(null, perdas) : 1;
    perdaMax = perdaMax <= 0 ? 1 : perdaMax * 1.12;

    function x(i) { return padE + (n === 1 ? larg / 2 : (i / (n - 1)) * larg); }
    function yPerda(v) { return padT + alt - (limitar(numero(v, 0) / perdaMax, 0, 1) * alt); }
    function yTaxa(v) {
      var f = numero(v, 0);
      if (f > 1.0001) f = f / 100;
      return padT + alt - (limitar(f, 0, 1) * alt);
    }

    // Fundo e grade suave
    ctx.fillStyle = COR.branco;
    ctx.fillRect(0, 0, larguraCss, alturaCss);
    ctx.strokeStyle = COR.linha;
    ctx.lineWidth = 1;
    ctx.font = "11px 'Roboto', 'Segoe UI', Arial, sans-serif";
    ctx.textBaseline = "middle";

    for (var g = 0; g <= 4; g++) {
      var yy = padT + (g / 4) * alt;
      ctx.beginPath();
      ctx.moveTo(padE, Math.round(yy) + 0.5);
      ctx.lineTo(padE + larg, Math.round(yy) + 0.5);
      ctx.stroke();

      // Eixo esquerdo: perda. Eixo direito: acuracia/F1 em porcentagem.
      ctx.fillStyle = COR.grafiteClaro;
      ctx.textAlign = "right";
      ctx.fillText((perdaMax * (1 - g / 4)).toFixed(2).replace(".", ","), padE - 8, yy);
      ctx.textAlign = "left";
      ctx.fillStyle = COR.terracotaClaro;
      ctx.fillText(Math.round((1 - g / 4) * 100) + "%", padE + larg + 8, yy);
    }

    // Eixo X: rotulos de epoca (com passo para nao amontoar)
    var passo = Math.max(1, Math.ceil(n / 10));
    ctx.textAlign = "center";
    ctx.fillStyle = COR.grafite;
    for (var i = 0; i < n; i++) {
      if (i % passo !== 0 && i !== n - 1) continue;
      var ep = hist[i].epoca != null ? hist[i].epoca : (i + 1);
      ctx.fillText(String(ep), x(i), padT + alt + 16);
    }
    ctx.fillStyle = COR.grafiteClaro;
    ctx.fillText("epoca", padE + larg / 2, padT + alt + 32);

    function linhaSerie(campo, fnY, cor, tracejada, raioPonto) {
      var pontos = [];
      for (var i2 = 0; i2 < n; i2++) {
        var v = hist[i2][campo];
        if (v == null) continue;
        pontos.push([x(i2), fnY(v)]);
      }
      if (!pontos.length) return false;
      ctx.save();
      ctx.strokeStyle = cor;
      ctx.lineWidth = 2;
      ctx.lineJoin = "round";
      ctx.lineCap = "round";
      if (tracejada) ctx.setLineDash([5, 4]);
      ctx.beginPath();
      pontos.forEach(function (p, k) { if (k === 0) ctx.moveTo(p[0], p[1]); else ctx.lineTo(p[0], p[1]); });
      ctx.stroke();
      ctx.setLineDash([]);
      if (raioPonto) {
        ctx.fillStyle = COR.branco;
        pontos.forEach(function (p) {
          ctx.beginPath();
          ctx.arc(p[0], p[1], raioPonto, 0, Math.PI * 2);
          ctx.fill();
          ctx.stroke();
        });
      }
      ctx.restore();
      return true;
    }

    var series = [];
    if (linhaSerie("perda_treino", yPerda, COR.grafiteClaro, true, 0)) series.push(["Perda treino", COR.grafiteClaro, true]);
    if (linhaSerie("perda_val", yPerda, COR.grafite, false, 2.5)) series.push(["Perda validacao", COR.grafite, false]);
    if (linhaSerie("f1_val", yTaxa, COR.terracotaClaro, true, 0)) series.push(["F1 validacao", COR.terracotaClaro, true]);
    if (linhaSerie("acc_val", yTaxa, COR.terracota, false, 2.5)) series.push(["Acuracia validacao", COR.terracota, false]);

    // Moldura do grafico
    ctx.strokeStyle = COR.linha;
    ctx.strokeRect(padE + 0.5, padT + 0.5, larg, alt);

    // Legenda
    ctx.font = "12px 'Roboto', 'Segoe UI', Arial, sans-serif";
    ctx.textAlign = "left";
    var lx = padE + 6, ly = padT - 14;
    if (ly < 10) ly = 10;
    series.forEach(function (s) {
      ctx.strokeStyle = s[1];
      ctx.lineWidth = 2.5;
      if (s[2]) ctx.setLineDash([5, 4]);
      ctx.beginPath();
      ctx.moveTo(lx, ly);
      ctx.lineTo(lx + 16, ly);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = COR.tinta;
      ctx.fillText(s[0], lx + 22, ly);
      lx += 22 + ctx.measureText(s[0]).width + 18;
    });
  }

  /* =======================================================================
   * 12. PAGINA RELATORIOS
   * ===================================================================== */

  /** Converte um subconjunto de markdown para HTML - sem biblioteca, tudo escapado. */
  function renderizarMarkdown(md) {
    var linhas = String(md || "").replace(/\r\n/g, "\n").split("\n");
    var saida = [];
    var lista = null;      // "ul" | "ol" | null
    var emCodigo = false;
    var tabela = [];

    function fecharLista() { if (lista) { saida.push("</" + lista + ">"); lista = null; } }
    function fecharTabela() {
      if (!tabela.length) return;
      saida.push(montarTabela(tabela));
      tabela = [];
    }

    for (var i = 0; i < linhas.length; i++) {
      var bruta = linhas[i];
      var linha = bruta.replace(/\s+$/, "");

      if (/^\s*```/.test(linha)) {
        fecharLista(); fecharTabela();
        if (emCodigo) { saida.push("</code></pre>"); emCodigo = false; }
        else { saida.push('<pre class="md-codigo"><code>'); emCodigo = true; }
        continue;
      }
      if (emCodigo) { saida.push(esc(bruta) + "\n"); continue; }

      if (/^\s*\|.*\|\s*$/.test(linha)) { fecharLista(); tabela.push(linha); continue; }
      fecharTabela();

      if (!linha.trim()) { fecharLista(); continue; }

      if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(linha)) {
        fecharLista();
        saida.push('<hr class="md-hr">');
        continue;
      }

      var h = linha.match(/^(#{1,6})\s+(.*)$/);
      if (h) {
        fecharLista();
        var nivel = h[1].length;
        saida.push("<h" + nivel + ' class="md-h' + nivel + '">' + inlineMarkdown(h[2]) + "</h" + nivel + ">");
        continue;
      }

      var ul = linha.match(/^\s*[-*+]\s+(.*)$/);
      if (ul) {
        if (lista !== "ul") { fecharLista(); saida.push('<ul class="md-lista">'); lista = "ul"; }
        saida.push("<li>" + inlineMarkdown(ul[1]) + "</li>");
        continue;
      }

      var ol = linha.match(/^\s*\d+[.)]\s+(.*)$/);
      if (ol) {
        if (lista !== "ol") { fecharLista(); saida.push('<ol class="md-lista">'); lista = "ol"; }
        saida.push("<li>" + inlineMarkdown(ol[1]) + "</li>");
        continue;
      }

      var bq = linha.match(/^\s*>\s?(.*)$/);
      if (bq) {
        fecharLista();
        saida.push('<blockquote class="md-citacao">' + inlineMarkdown(bq[1]) + "</blockquote>");
        continue;
      }

      fecharLista();
      saida.push('<p class="md-p">' + inlineMarkdown(linha) + "</p>");
    }

    if (emCodigo) saida.push("</code></pre>");
    fecharLista();
    fecharTabela();
    return saida.join("\n");
  }

  function montarTabela(linhas) {
    function celulas(l) {
      return l.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(function (c) { return c.trim(); });
    }
    var cabecalho = celulas(linhas[0]);
    var inicio = 1;
    if (linhas.length > 1 && /^[\s|:-]+$/.test(linhas[1])) inicio = 2;

    var html = '<div class="md-tabela-wrap"><table class="md-tabela"><thead><tr>';
    cabecalho.forEach(function (c) { html += "<th>" + inlineMarkdown(c) + "</th>"; });
    html += "</tr></thead><tbody>";
    for (var i = inicio; i < linhas.length; i++) {
      html += "<tr>";
      celulas(linhas[i]).forEach(function (c) { html += "<td>" + inlineMarkdown(c) + "</td>"; });
      html += "</tr>";
    }
    return html + "</tbody></table></div>";
  }

  /** Formatacao em linha. Escapa primeiro, formata depois: nunca o contrario. */
  function inlineMarkdown(texto) {
    var s = esc(texto);
    s = s.replace(/`([^`]+)`/g, '<code class="md-cod">$1</code>');
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/__([^_]+)__/g, "<strong>$1</strong>");
    s = s.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
    // Links apenas http/https; qualquer outro esquema fica como texto puro.
    s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    return s;
  }

  function gerarRelatorio() {
    var btn = $("btn-gerar-relatorio");
    var status = $("relatorio-status");
    botaoCarregando(btn, true, "Gerando...");
    setTexto(status, "Reunindo os eventos da sessao...");
    habilitar($("btn-baixar-relatorio"), false);

    postJSON("/api/relatorio", {}, { timeout: 120000 })
      .then(function (d) {
        botaoCarregando(btn, false);
        if (d && d.erro && !d.markdown) {
          setTexto(status, d.erro);
          toast(d.erro, "erro");
          return;
        }
        App.relatorioMarkdown = (d && d.markdown) || "";
        setHTML($("relatorio-saida"), renderizarMarkdown(App.relatorioMarkdown), "relatorio-saida");
        var onde = d && d.arquivo ? " Salvo em: " + d.arquivo : "";
        setTexto(status, "Relatorio gerado." + onde);
        habilitar($("btn-baixar-relatorio"), !!App.relatorioMarkdown);
        toast("Relatorio pronto.", "ok");
      })
      .catch(function (e) {
        botaoCarregando(btn, false);
        setTexto(status, "Falhou: " + e.message);
        toast("Nao consegui gerar o relatorio: " + e.message, "erro");
      });
  }

  function baixarRelatorio() {
    if (!App.relatorioMarkdown) { toast("Gere o relatorio primeiro.", "aviso"); return; }
    var blob = new Blob([App.relatorioMarkdown], { type: "text/markdown;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    var d = new Date();
    function dois(x) { return x < 10 ? "0" + x : String(x); }
    a.href = url;
    a.download = "relatorio_ponto_certo_" + d.getFullYear() + dois(d.getMonth() + 1) + dois(d.getDate()) +
      "_" + dois(d.getHours()) + dois(d.getMinutes()) + ".md";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
  }

  /* =======================================================================
   * 13. PAGINA AJUSTES
   * ===================================================================== */

  var CAMPOS_AJUSTE = [
    { id: "aj-limiar-alerta", chaves: ["limiar_alerta"], casas: 2 },
    { id: "aj-limiar-incerteza", chaves: ["limiar_incerteza"], casas: 2 },
    { id: "aj-frames", chaves: ["frames_para_confirmar", "frames"], casas: 0 },
    { id: "aj-ema", chaves: ["ema_alpha", "ema"], casas: 2 }
  ];

  /** Acha o <output> que acompanha o range (por for=, por irmao ou dentro do rotulo). */
  function saidaDoRange(input) {
    if (!input) return null;
    var porFor = document.querySelector('output[for="' + input.id + '"]');
    if (porFor) return porFor;
    var irmao = input.nextElementSibling;
    while (irmao) {
      if (irmao.tagName === "OUTPUT") return irmao;
      irmao = irmao.nextElementSibling;
    }
    if (input.parentElement) return input.parentElement.querySelector("output");
    return null;
  }

  function sincronizarSaida(input) {
    var out = saidaDoRange(input);
    if (!out) return;
    var casas = 2;
    CAMPOS_AJUSTE.forEach(function (c) { if (c.id === input.id) casas = c.casas; });
    var v = Number(input.value);
    out.textContent = isFinite(v) ? v.toFixed(casas).replace(".", ",") : input.value;
  }

  function primeiroValor(fonte, chaves) {
    if (!fonte) return null;
    for (var i = 0; i < chaves.length; i++) {
      if (fonte[chaves[i]] != null) return fonte[chaves[i]];
    }
    return null;
  }

  function carregarAjustes() {
    return fetchJSON("/api/ajustes")
      .then(function (d) {
        d = d || {};
        // Aceita tanto o objeto plano quanto o aninhado em "inferencia".
        var inf = d.inferencia || d;
        CAMPOS_AJUSTE.forEach(function (campo) {
          var input = $(campo.id);
          if (!input) return;
          var v = primeiroValor(inf, campo.chaves);
          if (v != null) input.value = String(v);
          sincronizarSaida(input);
        });
        var chk = $("aj-llm");
        if (chk) {
          var llm = d.llm || {};
          var ativo = llm.ativo != null ? llm.ativo : (d.llm_ativo != null ? d.llm_ativo : true);
          chk.checked = !!ativo;
        }
        var modelo = $("aj-modelo");
        if (modelo) {
          var m = (d.llm && (d.llm.modelo_visao || d.llm.modelo)) || d.modelo || d.modelo_visao || "";
          if (m) modelo.value = m;
        }
        setTexto($("ajustes-status"), "");
      })
      .catch(function (e) {
        setTexto($("ajustes-status"), "Nao consegui ler os ajustes: " + e.message);
      });
  }

  function salvarAjustes() {
    var btn = $("btn-salvar-ajustes");
    var corpo = {};
    CAMPOS_AJUSTE.forEach(function (campo) {
      var input = $(campo.id);
      if (!input) return;
      var v = Number(input.value);
      if (isFinite(v)) corpo[campo.chaves[0]] = campo.casas === 0 ? Math.round(v) : v;
    });
    var chk = $("aj-llm");
    if (chk) corpo.llm_ativo = !!chk.checked;
    var modelo = $("aj-modelo");
    if (modelo && modelo.value.trim()) corpo.modelo = modelo.value.trim();

    botaoCarregando(btn, true, "Salvando...");
    setTexto($("ajustes-status"), "");
    postJSON("/api/ajustes", corpo)
      .then(function (d) {
        botaoCarregando(btn, false);
        if (d && d.erro) {
          setTexto($("ajustes-status"), d.erro);
          toast(d.erro, "erro");
          return;
        }
        setTexto($("ajustes-status"), "Ajustes aplicados nesta sessao.");
        toast("Ajustes aplicados.", "ok");
      })
      .catch(function (e) {
        botaoCarregando(btn, false);
        setTexto($("ajustes-status"), "Falhou: " + e.message);
        toast("Nao consegui salvar: " + e.message, "erro");
      });
  }

  function testarLLM() {
    var btn = $("btn-testar-llm");
    var caixa = $("llm-status");
    botaoCarregando(btn, true, "Testando...");
    setHTML(caixa, '<p class="ia-carregando">Falando com o OpenRouter...</p>', "llm-status");
    fetchJSON("/api/llm/status", { timeout: 45000 })
      .then(function (d) {
        botaoCarregando(btn, false);
        d = d || {};
        var ok = !!d.ok;
        var est = d.estatisticas || {};
        var html = '<div class="llm-cartao ' + (ok ? "llm-ok" : "llm-erro") + '">' +
          '<span class="selo-fonte ' + (ok ? "selo-ok" : "selo-nao") + '">' +
          '<span class="selo-icone" aria-hidden="true">' + (ok ? ICONES.check : ICONES.erro) + "</span>" +
          esc(ok ? "Conectado" : "Indisponivel") + "</span>" +
          '<p class="llm-mensagem">' + esc(d.mensagem || (ok ? "Tudo certo." : "Sem detalhes.")) + "</p>";
        if (d.modelo_visao) html += '<p class="llm-modelo">Modelo de visao: <strong>' + esc(d.modelo_visao) + "</strong></p>";
        if (d.creditos) {
          var c = d.creditos;
          var resumo = (c.usados != null || c.limite != null)
            ? "usados " + esc(c.usados) + " de " + esc(c.limite == null ? "sem limite" : c.limite)
            : esc(JSON.stringify(c).slice(0, 180));
          html += '<p class="llm-creditos">Creditos: ' + resumo + "</p>";
        }
        html += '<p class="llm-uso">Chamadas: ' + esc(numero(est.chamadas, 0)) +
          " - tokens entrada: " + esc(numero(est.tokens_entrada, 0)) +
          " - tokens saida: " + esc(numero(est.tokens_saida, 0)) +
          " - erros: " + esc(numero(est.erros, 0)) + "</p></div>";
        setHTML(caixa, html, "llm-status");
      })
      .catch(function (e) {
        botaoCarregando(btn, false);
        setHTML(caixa, '<div class="llm-cartao llm-erro"><p class="llm-mensagem">' +
          esc(e.message) + "</p></div>", "llm-status");
      });
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
      // Stories do historico
      var story = ev.target.closest ? ev.target.closest(".story[data-classe]") : null;
      if (story) {
        filtrarHistorico(story.getAttribute("data-classe"));
        return;
      }
      // Miniaturas do historico
      var celula = ev.target.closest ? ev.target.closest(".celula[data-id]") : null;
      if (celula) {
        abrirModal(celula.getAttribute("data-id"));
        return;
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
    ligar($("btn-capturar"), "click", capturarQuadro);
    ligar($("btn-diagnostico"), "click", pedirDiagnostico);
    ligar($("btn-segunda-opiniao"), "click", pedirSegundaOpiniao);

    var video = $("video-ao-vivo");
    ligar(video, "error", function () {
      if (App.cameraAtiva) toast("O video parou de chegar. Tente religar a camera.", "erro");
    });

    /* --- Testar --------------------------------------------------------- */
    var input = $("input-arquivo");
    ligar($("btn-escolher"), "click", function () { if (input) input.click(); });
    ligar(input, "change", function (e) {
      var f = e.target.files && e.target.files[0];
      tratarArquivoEscolhido(f);
      e.target.value = ""; // permite reescolher o mesmo arquivo
    });

    var drop = $("drop-zone");
    if (drop) {
      ["dragenter", "dragover"].forEach(function (nome) {
        drop.addEventListener(nome, function (e) {
          e.preventDefault();
          e.stopPropagation();
          drop.classList.add("arrastando");
        });
      });
      ["dragleave", "drop"].forEach(function (nome) {
        drop.addEventListener(nome, function (e) {
          e.preventDefault();
          e.stopPropagation();
          if (nome === "dragleave" && drop.contains(e.relatedTarget)) return;
          drop.classList.remove("arrastando");
        });
      });
      drop.addEventListener("drop", function (e) {
        var dt = e.dataTransfer;
        var f = dt && dt.files && dt.files[0];
        tratarArquivoEscolhido(f);
      });
      // A zona tambem abre o seletor no clique e no teclado (acessibilidade).
      drop.addEventListener("click", function (e) {
        if (e.target.closest && e.target.closest("button")) return;
        if (input) input.click();
      });
      drop.addEventListener("keydown", function (e) {
        if ((e.key === "Enter" || e.key === " ") && input) { e.preventDefault(); input.click(); }
      });
    }
    ligar($("btn-teste-diagnostico"), "click", diagnosticoDoTeste);

    /* --- Historico e modal ---------------------------------------------- */
    ligar($("btn-modal-fechar"), "click", fecharModal);
    ligar($("btn-modal-confirmar"), "click", function () {
      // Confirmar = o operador concorda com a classe prevista pela rede.
      var ev = App.eventoAberto;
      if (ev) enviarRotulo(ev.classe_key, $("btn-modal-confirmar"));
    });
    ligar($("btn-modal-corrigir"), "click", function () {
      var sel = $("modal-select-rotulo");
      enviarRotulo(sel ? sel.value : null, $("btn-modal-corrigir"));
    });
    ligar($("btn-modal-diagnostico"), "click", diagnosticoDoModal);

    var modal = $("modal-evento");
    if (modal) {
      modal.addEventListener("click", function (e) {
        // Clique no overlay (fora do conteudo) fecha o post.
        if (e.target === modal || (e.target.classList && e.target.classList.contains("modal-overlay"))) {
          fecharModal();
        }
      });
    }
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") fecharModal();
    });

    /* --- Relatorios ------------------------------------------------------ */
    ligar($("btn-gerar-relatorio"), "click", gerarRelatorio);
    ligar($("btn-baixar-relatorio"), "click", baixarRelatorio);

    /* --- Ajustes --------------------------------------------------------- */
    CAMPOS_AJUSTE.forEach(function (campo) {
      var el = $(campo.id);
      ligar(el, "input", function () { sincronizarSaida(el); });
    });
    ligar($("btn-salvar-ajustes"), "click", salvarAjustes);
    ligar($("btn-testar-llm"), "click", testarLLM);

    /* --- Janela ---------------------------------------------------------- */
    var tempoResize = null;
    window.addEventListener("resize", function () {
      if (tempoResize) clearTimeout(tempoResize);
      tempoResize = setTimeout(function () {
        if (App.pagina === "treinamento") desenharGraficoTreino();
      }, 150);
    });

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
    habilitar($("btn-segunda-opiniao"), false);
    habilitar($("btn-baixar-relatorio"), false);
    habilitar($("btn-teste-diagnostico"), false);
    atualizarChipCamera({ ativa: false });
    renderVeredito({ estado: "aquecendo" }, null);

    // Ordem do bootstrap: taxonomia primeiro (os outros renders dependem dela).
    carregarTaxonomia()
      .then(function () { return carregarSaude(); })
      .then(function () { return carregarDispositivos(); })
      .then(function () {
        var chk = $("toggle-gradcam");
        if (chk) App.gradcamLigado = !!chk.checked;
        irPara(paginaDoHash(), false);
      });
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
    recarregarHistorico: carregarHistorico,
    recarregarTreinamento: carregarTreinamento
  };
})();

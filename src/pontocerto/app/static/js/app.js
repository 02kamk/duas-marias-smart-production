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

  var PAGINAS = ["ao-vivo", "conferir", "historico", "relatorios", "ajustes"];

  // Situacao do banco (chip da barra superior): consulta lenta, o servidor ja
  // guarda o teste de conexao em cache.
  var INTERVALO_BANCO_MS = 15000;
  var PAGINA_PADRAO = "ao-vivo";

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
    if (bruto === "lotes") return "lotes";
    return PAGINAS.indexOf(bruto) >= 0 ? bruto : PAGINA_PADRAO;
  }

  function irPara(pagina, atualizarHash) {
    // Os lotes agora ficam numa tela só, na Gestão.
    if (pagina === "lotes") { location.assign("/gestao#lotes"); return; }
    // Endereços antigos (#testar, #treinamento) caem na inspeção.
    if (pagina === "testar" || pagina === "treinamento") pagina = "ao-vivo";
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
    } else if (pagina === "ajustes") {
      carregarAjustes();
      atualizarBanco(false);
    }
    // A pagina "relatorios" nao precisa buscar nada ao entrar.
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

        if (!modelo.carregado) {
          toast(
            "A IA de inspeção não está disponível neste servidor. Fale com o responsável." +
            (modelo.erro ? " (" + modelo.erro + ")" : ""),
            "aviso"
          );
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
  function capturarQuadro() {
    var img = $("video-ao-vivo");
    if (!App.cameraAtiva || !img || !img.naturalWidth) {
      toast("Ligue a câmera antes de analisar.", "aviso");
      return;
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
    botaoCarregando(btn, true, "Capturando...");
    canvas.toBlob(function (blob) {
      if (!blob) {
        botaoCarregando(btn, false);
        toast("Captura vazia.", "erro");
        return;
      }
      var arquivo = new File([blob], "captura.jpg", { type: "image/jpeg" });
      enviarParaAnalise(arquivo, "camera_servidor")
        .then(function () {
          botaoCarregando(btn, false);
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
      "<details><summary>Ver causas e prevenção</summary>" + resto + "</details>";
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

  function enviarParaAnalise(arquivo, origem) {
    var resultado = $("resultado-teste");
    mostrar(resultado, true);
    // "Próxima peça" repete o caminho que a pessoa acabou de usar.
    var proxima = $("btn-proxima");
    if (proxima) proxima.setAttribute("for", origem === "camera_aparelho" ? "foto-camera" : "input-arquivo");
    setHTML($("teste-ia"), "", "teste-ia");
    setHTML($("conferencia-upload"), "", "conferencia-upload");
    setTexto($("teste-classe"), "Analisando a costura...");
    setTexto($("teste-confianca"), "");
    if (resultado) resultado.classList.remove("resultado-ok", "resultado-falha", "resultado-incerto");
    var fotoAnterior = $("peca-analisada");
    if (fotoAnterior) fotoAnterior.src = PIXEL_VAZIO;

    var fd = new FormData();
    fd.append("arquivo", arquivo, arquivo.name || "imagem.jpg");
    fd.append("origem", origem || "upload");

    return fetchJSON("/api/analisar", { method: "POST", body: fd, timeout: 60000 })
      .then(function (d) {
        if (d && d.erro) {
          setTexto($("teste-classe"), "Não foi possível analisar");
          setTexto($("teste-confianca"), d.erro);
          throw new Error(d.erro);
        }
        App.analiseAtual = d || {};
        renderResultadoTeste(App.analiseAtual);
        atualizarPendentes();
        carregarRecentes();
        // Leva a pessoa direto ao resultado.
        if (resultado && resultado.scrollIntoView) resultado.scrollIntoView({ behavior: "smooth", block: "start" });
        return App.analiseAtual;
      })
      .catch(function (e) {
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
    mostrarMidiaResultado(false);
    setTexto($("resultado-lote"), ev.lote_codigo ? "Lote " + ev.lote_codigo : "Sem lote");
    setTexto($("resultado-ordem"), (NOMES_ORIGEM[ev.origem] || "Foto enviada") + (ev.hora ? " · " + horaCurta(ev) : ""));
    habilitar($("ver-mapa"), !!d.heatmap);

    var incerta = !p.e_falha && !!ev.precisa_revisao;
    setTexto($("teste-classe"), p.e_falha ? (p.nome || nomeDaClasse(p.classe_key))
      : (incerta ? "Leitura incerta: parece normal" : "Costura aprovada"));
    setTexto($("teste-confianca"), "A IA tem " + formatarPercentual(p.confianca, 0) + " de certeza" + (incerta ? ". Confira a peça." : ""));

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

    botaoCarregando(btn, true, "Salvando...");
    setTexto($("ajustes-status"), "");
    postJSON("/api/ajustes", corpo)
      .then(function (d) {
        botaoCarregando(btn, false);
        if (d && d.erro) { setTexto($("ajustes-status"), d.erro); toast(d.erro, "erro"); return; }
        setTexto($("ajustes-status"), "Ajustes salvos.");
        toast("Ajustes salvos.", "ok");
      })
      .catch(function (e) {
        botaoCarregando(btn, false);
        setTexto($("ajustes-status"), "Falhou: " + e.message);
        toast("Não consegui salvar: " + e.message, "erro");
      });
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
          esc(ok ? "Conectado" : "Sem conexão") + "</span>" +
          '<p class="llm-mensagem">' + esc(ok ? "As explicações usam a IA." : (d.mensagem || "As explicações usam a base técnica local.")) + "</p></div>", "llm-status");
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
        "peça a quem instalou o sistema para configurar o banco.</p>", "banco-status");
      return;
    }
    var st = d.storage || {};
    var sinc = d.sincronizacao || {};
    var linhas = [];
    linhas.push("<span><strong>Banco:</strong> " + (d.conectado ? "conectado" : "sem conexão - " + esc(d.erro || "")) + "</span>");
    linhas.push("<span><strong>Fotos:</strong> " + (st.ok ? "sendo enviadas" : esc(st.erro || "não configurado; as inspeções sobem sem foto")) + "</span>");
    linhas.push("<span><strong>Aguardando envio:</strong> " + esc(pend) + "</span>");
    if (sinc.ultimo_erro) linhas.push("<span><strong>Último erro:</strong> " + esc(sinc.ultimo_erro) + "</span>");
    setHTML(caixa, '<div class="banco-linhas">' + linhas.join("") + "</div>", "banco-status");
  }

  /* --- Lote em produção ------------------------------------------------- */

  /** Lote em inspeção: o seletor no topo da tela Inspecionar. */
  function renderChipLote(lote) {
    App.lotes.ativo = lote || null;
    var sel = $("sel-lote");
    if (sel) {
      var id = lote ? String(lote.ordem_id || "") : "";
      // O lote ativo pode não estar na lista ainda (ou ter sido concluído).
      if (id && !sel.querySelector('option[value="' + id.replace(/"/g, "") + '"]')) {
        var opt = criar("option", null, lote.codigo + (lote.modelo_peca ? " · " + lote.modelo_peca : ""));
        opt.value = id;
        sel.appendChild(opt);
      }
      if (document.activeElement !== sel) sel.value = id;
    }
    mostrar($("aviso-sem-lote"), !lote && App.lotes.lista.length > 0);
  }

  function carregarLotes() {
    return fetchJSON("/api/gestao/inspecao")
      .then(function (d) {
        App.lotes.lista = (d && d.lotes) || [];
        App.lotes.ativo = (d && d.ativo) || null;
        renderLotes();
      })
      .catch(function (e) {
        App.lotes.lista = [];
        renderLotes();
      });
  }

  function renderLotes() {
    var sel = $("sel-lote");
    if (!sel) return;
    var html = '<option value="">Sem lote</option>' + App.lotes.lista.map(function (l) {
      return '<option value="' + esc(l.id) + '">' + esc(l.code) + " · " + esc(l.model) + "</option>";
    }).join("");
    setHTML(sel, html, "sel-lote");
    renderChipLote(App.lotes.ativo);
  }

  function usarLote(id) {
    postJSON("/api/gestao/orders/" + encodeURIComponent(id) + "/inspecionar", {})
      .then(function (d) {
        renderChipLote(d.lote);
        toast("As próximas peças vão para o lote " + d.lote.codigo + ".", "ok");
      })
      .catch(function (e) {
        renderChipLote(App.lotes.ativo);
        toast("Não consegui escolher o lote: " + e.message, "erro");
      });
  }

  function pararLote() {
    postJSON("/api/lotes/ativo", { lote_id: null })
      .then(function () {
        renderChipLote(null);
        toast("Nenhum lote em inspeção.", "info");
      })
      .catch(function (e) { toast("Não consegui parar: " + e.message, "erro"); });
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
    ligar($("btn-capturar"), "click", capturarQuadro);
    ligar($("btn-diagnostico"), "click", pedirDiagnostico);
    ligar($("btn-conferir-ultimo"), "click", function () { abrirModalEvento(App.ultimoEvento); });
    // A câmera ao vivo começa recolhida; abre de novo se a pessoa deixou aberta.
    var blocoCamera = $("bloco-camera");
    if (blocoCamera) {
      var salvo = null;
      try { salvo = localStorage.getItem("blocoCameraAberto"); } catch (e) {}
      blocoCamera.open = salvo === "1";
      blocoCamera.addEventListener("toggle", function () {
        try { localStorage.setItem("blocoCameraAberto", blocoCamera.open ? "1" : "0"); } catch (e) {}
      });
    }

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
      if (e.target.value) usarLote(e.target.value);
      else pararLote();
    });

    /* --- Historico e modal ---------------------------------------------- */
    ligar($("btn-modal-fechar"), "click", fecharModal);
    ligar($("btn-modal-diagnostico"), "click", diagnosticoDoModal);
    ligar($("btn-modal-apagar-foto"), "click", apagarFotoDoModal);
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
    ligar($("btn-salvar-ajustes"), "click", salvarAjustes);
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
    recarregarHistorico: carregarHistorico
  };
})();

/* Tela de chat do Riff. Sem dependências: fala com /api/chat por SSE e restaura a conversa pelo session_id. */
(function () {
  "use strict";

  const SUGESTOES = [
    "Quais violões até R$ 1.000?",
    "Quanto custa o Takamine GD20?",
    "Qual o endereço da loja?",
    "Me arrependi da compra, posso devolver?",
  ];
  const BOAS_VINDAS =
    "E aí, tudo bem? Eu sou o Riff, assistente da Empório da Música. Posso te ajudar a escolher instrumento, " +
    "conferir preços e promoções, simular parcelas, acompanhar um pedido ou tirar dúvidas sobre as regras da loja.";
  const CHAVE_SESSAO = "emporio-sessao";
  const CHAVE_BASTIDORES = "emporio-bastidores";

  const el = {
    mensagens: document.getElementById("mensagens"),
    form: document.getElementById("form"),
    texto: document.getElementById("texto"),
    enviar: document.getElementById("enviar"),
    nova: document.getElementById("nova"),
    selo: document.getElementById("selo"),
    aviso: document.getElementById("aviso"),
    bastidores: document.getElementById("bastidores"),
  };
  const reduzir = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let sessao = null;
  let ocupado = false;

  /* Armazenamento pode falhar (janela privada, dados bloqueados): a tela segue funcionando sem ele. */
  function ler(chave) { try { return localStorage.getItem(chave); } catch (e) { return null; } }
  function gravar(chave, valor) { try { localStorage.setItem(chave, valor); } catch (e) { /* sem persistência */ } }

  function novoId() {
    const bytes = new Uint8Array(8);
    (window.crypto || { getRandomValues: (a) => a.map(() => Math.floor(Math.random() * 256)) }).getRandomValues(bytes);
    return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  }

  /* Markdown mínimo e seguro: escapa o HTML antes de qualquer marcação. */
  function esc(t) {
    return t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function inline(t) {
    return esc(t)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[^*])\*([^*\s][^*]*)\*(?!\*)/g, "$1<em>$2</em>");
  }
  function celulas(linha) {
    return linha.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map((c) => c.trim());
  }
  function markdown(texto) {
    const linhas = texto.replace(/\r/g, "").split("\n");
    const saida = [];
    let i = 0;
    while (i < linhas.length) {
      const linha = linhas[i];
      if (!linha.trim()) { i++; continue; }
      if (/^\s*\|.*\|\s*$/.test(linha) && i + 1 < linhas.length && /^\s*\|?\s*:?-{2,}/.test(linhas[i + 1])) {
        const cab = celulas(linha);
        i += 2;
        const corpo = [];
        while (i < linhas.length && /^\s*\|.*\|\s*$/.test(linhas[i])) { corpo.push(celulas(linhas[i])); i++; }
        saida.push(
          '<div class="tabela"><table><thead><tr>' + cab.map((c) => "<th>" + inline(c) + "</th>").join("") +
          "</tr></thead><tbody>" +
          corpo.map((l) => "<tr>" + l.map((c) => "<td>" + inline(c) + "</td>").join("") + "</tr>").join("") +
          "</tbody></table></div>"
        );
        continue;
      }
      const lista = linha.match(/^\s*([-*•]|\d+[.)])\s+/);
      if (lista) {
        const ordenada = /\d/.test(lista[1]);
        const itens = [];
        while (i < linhas.length && /^\s*([-*•]|\d+[.)])\s+/.test(linhas[i])) {
          itens.push(linhas[i].replace(/^\s*([-*•]|\d+[.)])\s+/, ""));
          i++;
        }
        const tag = ordenada ? "ol" : "ul";
        saida.push("<" + tag + ">" + itens.map((x) => "<li>" + inline(x) + "</li>").join("") + "</" + tag + ">");
        continue;
      }
      const bloco = [];
      while (i < linhas.length && linhas[i].trim() && !/^\s*([-*•]|\d+[.)])\s+/.test(linhas[i]) && !/^\s*\|.*\|\s*$/.test(linhas[i])) {
        bloco.push(inline(linhas[i]));
        i++;
      }
      if (bloco.length) saida.push("<p>" + bloco.join("<br>") + "</p>");
      else i++;
    }
    return saida.join("");
  }

  function rolar() {
    el.mensagens.scrollTo({ top: el.mensagens.scrollHeight, behavior: reduzir ? "auto" : "smooth" });
  }
  function mini() {
    const img = document.createElement("img");
    img.className = "mini";
    img.src = "/static/riff.svg";
    img.alt = "";
    return img;
  }
  function linhaRiff(html, extra) {
    const linha = document.createElement("div");
    linha.className = "msg riff" + (extra ? " " + extra : "");
    const balao = document.createElement("div");
    balao.className = "balao";
    balao.innerHTML = html;
    linha.append(mini(), balao);
    el.mensagens.append(linha);
    return { linha, balao };
  }
  function linhaUsuario(texto) {
    const linha = document.createElement("div");
    linha.className = "msg usuario";
    const balao = document.createElement("div");
    balao.className = "balao";
    balao.textContent = texto;
    linha.append(balao);
    el.mensagens.append(linha);
  }
  function bastidores(balao, ferramentas) {
    if (!ferramentas || !ferramentas.length) return;
    const caixa = document.createElement("div");
    caixa.className = "bastidor";
    ferramentas.forEach((f) => {
      const d = document.createElement("div");
      d.textContent = f.nome + "(" + JSON.stringify(f.argumentos) + ")";
      caixa.append(d);
    });
    balao.append(caixa);
  }

  /* Anima a entrada do texto: a resposta já chegou inteira e validada, aqui é só apresentação. */
  function digitar(balao, texto, ferramentas) {
    return new Promise((resolve) => {
      const fim = () => { balao.innerHTML = markdown(texto); bastidores(balao, ferramentas); rolar(); resolve(); };
      if (reduzir || texto.length < 40) { fim(); return; }
      const palavras = texto.split(/(\s+)/);
      const passo = Math.max(1, Math.ceil(palavras.length / 40));
      let n = 0;
      const tick = () => {
        n += passo;
        if (n >= palavras.length) { fim(); return; }
        balao.innerHTML = markdown(palavras.slice(0, n).join(""));
        rolar();
        setTimeout(tick, 28);
      };
      tick();
    });
  }

  function atividade(rotulo) {
    let linha = document.getElementById("atividade");
    if (!linha) {
      linha = document.createElement("div");
      linha.id = "atividade";
      linha.className = "atividade";
      linha.append(mini());
      const t = document.createElement("span");
      t.innerHTML = '<span class="pontos" aria-hidden="true"><span></span><span></span><span></span></span><span class="rotulo"></span>';
      linha.append(t);
      el.mensagens.append(linha);
    }
    linha.querySelector(".rotulo").textContent = rotulo;
    rolar();
  }
  function fimAtividade() {
    const linha = document.getElementById("atividade");
    if (linha) linha.remove();
  }

  function aviso(texto) {
    el.aviso.textContent = texto || "";
    el.aviso.hidden = !texto;
  }
  function travar(sim) {
    ocupado = sim;
    el.texto.disabled = sim;
    el.enviar.disabled = sim;
    if (!sim) el.texto.focus({ preventScroll: true });
  }

  function boasVindas() {
    const { linha } = linhaRiff("<p>" + esc(BOAS_VINDAS) + "</p>");
    linha.classList.add("boas");
    const caixa = document.createElement("div");
    caixa.className = "sugestoes";
    SUGESTOES.forEach((s) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "sugestao";
      b.textContent = s;
      b.addEventListener("click", () => enviar(s));
      caixa.append(b);
    });
    el.mensagens.append(caixa);
  }

  function limparTela() {
    el.mensagens.replaceChildren();
  }

  /* Leitura do corpo SSE: blocos separados por linha em branco, com `event:` e `data:`. */
  async function lerEventos(resposta, aoEvento) {
    const leitor = resposta.body.getReader();
    const decodificador = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await leitor.read();
      if (done) break;
      buffer += decodificador.decode(value, { stream: true });
      let corte;
      while ((corte = buffer.indexOf("\n\n")) >= 0) {
        const bloco = buffer.slice(0, corte);
        buffer = buffer.slice(corte + 2);
        let nome = "message";
        const dados = [];
        bloco.split("\n").forEach((l) => {
          if (l.startsWith("event:")) nome = l.slice(6).trim();
          else if (l.startsWith("data:")) dados.push(l.slice(5).trimStart());
        });
        let json = {};
        try { json = JSON.parse(dados.join("\n") || "{}"); } catch (e) { /* bloco inválido */ }
        await aoEvento(nome, json);
      }
    }
  }

  async function enviar(texto) {
    texto = (texto || "").trim();
    if (!texto || ocupado) return;
    document.querySelectorAll(".sugestoes").forEach((n) => n.remove());
    linhaUsuario(texto);
    el.texto.value = "";
    ajustarAltura();
    rolar();
    travar(true);
    atividade("Pensando");
    let respondeu = false;
    try {
      const resposta = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessao, message: texto }),
      });
      if (!resposta.ok || !resposta.body) throw new Error("http " + resposta.status);
      await lerEventos(resposta, async (nome, dados) => {
        if (nome === "status") atividade(dados.rotulo + "…");
        else if (nome === "message") {
          respondeu = true;
          fimAtividade();
          const { balao, linha } = linhaRiff("");
          if (dados.erro) linha.classList.add("erro");
          await digitar(balao, dados.content || "", dados.ferramentas);
        } else if (nome === "error") {
          respondeu = true;
          fimAtividade();
          linhaRiff("<p>" + esc(dados.mensagem || "Algo deu errado. Tente de novo.") + "</p>", "erro");
        }
      });
    } catch (e) {
      /* falha de rede ou servidor fora do ar */
    }
    fimAtividade();
    if (!respondeu) {
      linhaRiff("<p>Não consegui falar com o servidor agora. Confira se o sistema está de pé e tente de novo.</p>", "erro");
    }
    rolar();
    travar(false);
  }

  async function restaurar() {
    try {
      const r = await fetch("/api/sessions/" + sessao + "/messages");
      if (!r.ok) return false;
      const { messages, em_curso: emCurso } = await r.json();
      if (!messages.length && !emCurso) return false;
      messages.forEach((m) => {
        if (m.role === "user") linhaUsuario(m.content);
        else linhaRiff(markdown(m.content));
      });
      if (emCurso) {
        linhaUsuario(emCurso.mensagem);
        aguardarTurnoEmCurso(messages.length);
      }
      el.mensagens.scrollTop = el.mensagens.scrollHeight;
      return true;
    } catch (e) {
      return false;
    }
  }

  /* Recarregar no meio de um turno: o servidor termina e grava a resposta, então a tela consulta até ela aparecer. */
  async function aguardarTurnoEmCurso(quantidade) {
    travar(true);
    atividade("Pensando");
    let concluido = false;
    for (let tentativa = 0; tentativa < 90 && !concluido; tentativa++) {
      await new Promise((ok) => setTimeout(ok, 1500));
      try {
        const r = await fetch("/api/sessions/" + sessao + "/messages");
        const { messages, em_curso: emCurso } = await r.json();
        if (emCurso) continue;
        concluido = true;
        fimAtividade();
        const { balao, linha } = linhaRiff("");
        if (messages.length > quantidade) {
          balao.innerHTML = markdown(messages[messages.length - 1].content);
        } else {
          linha.classList.add("erro");
          balao.innerHTML = "<p>Não consegui concluir essa resposta. Pode mandar a pergunta de novo?</p>";
        }
        rolar();
      } catch (e) { /* tenta de novo */ }
    }
    fimAtividade();
    travar(false);
  }

  async function atualizarLoja() {
    try {
      const r = await fetch("/api/loja");
      const d = await r.json();
      el.selo.dataset.estado = d.aberta ? "aberta" : "fechada";
      el.selo.textContent = d.aberta ? "Loja aberta" : "Loja fechada";
      el.selo.title = d.texto;
    } catch (e) {
      el.selo.dataset.estado = "carregando";
      el.selo.textContent = "Loja";
    }
  }
  async function conferirModelo() {
    try {
      const r = await fetch("/api/health");
      const d = await r.json();
      aviso(d.llm === "ok" ? "" : "O modelo de linguagem não está respondendo. Inicie o servidor do LM Studio e tente de novo.");
    } catch (e) {
      aviso("Não foi possível falar com o servidor da tela.");
    }
  }

  function ajustarAltura() {
    el.texto.style.height = "auto";
    el.texto.style.height = Math.min(el.texto.scrollHeight, 140) + "px";
  }

  el.form.addEventListener("submit", (ev) => { ev.preventDefault(); enviar(el.texto.value); });
  el.texto.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) { ev.preventDefault(); enviar(el.texto.value); }
  });
  el.texto.addEventListener("input", ajustarAltura);
  el.nova.addEventListener("click", () => {
    if (ocupado) return;
    sessao = novoId();
    gravar(CHAVE_SESSAO, sessao);
    limparTela();
    boasVindas();
    el.texto.focus();
  });
  el.bastidores.addEventListener("click", () => {
    const ligado = document.body.classList.toggle("ver-bastidores");
    el.bastidores.setAttribute("aria-pressed", String(ligado));
    gravar(CHAVE_BASTIDORES, ligado ? "1" : "0");
  });

  async function iniciar() {
    sessao = ler(CHAVE_SESSAO);
    if (!sessao || !/^[A-Za-z0-9_-]{4,64}$/.test(sessao)) {
      sessao = novoId();
      gravar(CHAVE_SESSAO, sessao);
    }
    if (ler(CHAVE_BASTIDORES) === "1") {
      document.body.classList.add("ver-bastidores");
      el.bastidores.setAttribute("aria-pressed", "true");
    }
    atualizarLoja();
    conferirModelo();
    setInterval(atualizarLoja, 60000);
    if (!(await restaurar())) boasVindas();
    el.texto.focus();
  }
  iniciar();
})();

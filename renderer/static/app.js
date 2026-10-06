/* SCIBooster renderer frontend: citation network + BFS/DFS playback */
(() => {
  "use strict";

  const $ = (s) => document.querySelector(s);
  const $$ = (s) => [...document.querySelectorAll(s)];
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const ORIGIN = {
    seed: { name: "种子文献", color: "--o-seed" },
    wos_search: { name: "WoS 检索", color: "--o-search" },
    openalex_search: { name: "OpenAlex 检索", color: "--o-search" },
    backward: { name: "后向扩展（参考文献）", color: "--o-backward" },
    forward: { name: "前向扩展（施引文献）", color: "--o-forward" },
    cocited: { name: "共被引补缺", color: "--o-cocited" },
    agent: { name: "Agent 添加", color: "--o-agent" },
  };
  const RELATION = {
    extends: { name: "扩展/改进", color: "#e0457b" },
    uses_method: { name: "使用方法", color: "#2a9d8f" },
    uses_data: { name: "使用数据", color: "#3a86ff" },
    compares: { name: "对比", color: "#f4a261" },
    critiques: { name: "质疑", color: "#d62828" },
    background: { name: "背景引用", color: null },
  };

  const S = {
    corpus: null, byId: {}, cy: null,
    starts: [], mode: "bfs", visits: [], step: 0, timer: null, selected: null,
  };

  // ---------- Initialization ----------
  async function init() {
    const res = await fetch("/api/corpus");
    S.corpus = await res.json();
    S.corpus.papers.forEach((p) => (S.byId[p.id] = p));
    renderHeader();
    renderLegend();
    renderMeta();
    buildGraph();
    bindUI();
  }

  function renderHeader() {
    const m = S.corpus.meta, st = S.corpus.stats || {};
    $("#corpus-title").textContent = m.prompt || "(未命名语料库)";
    $("#corpus-title").title = m.intent?.topic || "";
    $("#corpus-stats").textContent = `${st.n_papers ?? S.corpus.papers.length} 篇 · ${st.n_edges ?? S.corpus.edges.length} 条引用` +
      (st.year_span ? ` · ${st.year_span[0]}–${st.year_span[1]}` : "");
    const years = S.corpus.papers.map((p) => p.year).filter(Boolean);
    if (years.length) {
      $("#year-from").value = Math.min(...years);
      $("#year-to").value = Math.max(...years);
    }
  }

  function renderLegend() {
    const used = new Set(S.corpus.papers.map((p) => (p.is_seed ? "seed" : p.origin)));
    let h = Object.entries(ORIGIN).filter(([k]) => used.has(k))
      .map(([, o]) => `<div><i style="background:${css(o.color)}"></i>${o.name}</div>`).join("");
    const rels = new Set(S.corpus.edges.map((e) => e.relation?.label).filter(Boolean));
    h += Object.entries(RELATION).filter(([k]) => rels.has(k))
      .map(([, r]) => `<div><i class="line" style="background:${r.color || css("--edge")}"></i>${r.name}</div>`).join("");
    h += `<div class="muted">节点大小 ∝ log(被引次数)；边方向：施引 → 被引</div>`;
    $("#legend").innerHTML = h;
  }

  function renderMeta() {
    const m = S.corpus.meta;
    const u = m.usage || {};
    $("#tab-meta").innerHTML = `
      <div class="detail">
        <h4>研究需求</h4><div>${esc(m.prompt)}</div>
        <h4>解析意图</h4><div>${esc(m.intent?.topic || "")}</div>
        <ul>${(m.intent?.research_questions || []).map((q) => `<li>${esc(q)}</li>`).join("")}</ul>
        <h4>检索式</h4><ul>${(m.queries || []).map((q) => `<li><code>${esc(q)}</code></li>`).join("")}</ul>
        ${m.summary ? `<h4>Agent 总结</h4><div>${esc(m.summary)}</div>` : ""}
        ${m.prisma ? `<h4>筛选流程（PRISMA）</h4>${prismaFlow(m.prisma)}` : ""}
        <h4>用量</h4>
        <div class="muted">DeepSeek ${u.deepseek_calls ?? 0} 次调用 · ${(u.deepseek_prompt_tokens ?? 0) + (u.deepseek_completion_tokens ?? 0)} tokens ·
          WoS ${u.wos_requests ?? 0} 次 · OpenAlex ${u.openalex_requests ?? 0} 次</div>
        <h4>参数</h4><pre class="json">${esc(JSON.stringify(m.params, null, 2))}</pre>
        <div class="muted">${esc(m.created_at)} · ${esc(m.source_file || "")}</div>
      </div>`;
  }

  function prismaFlow(pr) {
    const ident = Object.entries(pr.identified || {})
      .map(([k, n]) => `${esc(ORIGIN[k]?.name || k)} ${n}`).join(" · ");
    const total = Object.values(pr.identified || {}).reduce((a, b) => a + b, 0);
    const seeds = pr.identified?.seed || 0;
    const box = (label, n, side = "") =>
      `<div class="box">${label} <b>${n}</b>${side ? `<div class="side">${side}</div>` : ""}</div>`;
    const arrow = '<div class="arrow">↓</div>';
    const hops = (pr.hops || []).map((h) => `第 ${h.hop} 跳：新增 ${h.candidates}，送筛 ${h.screened}，相关 ${h.relevant}`).join("<br/>");
    return `<div class="flow">
      ${box("识别（去重后）", total, ident + (pr.search_duplicates ? `<br/>检索重复命中 ${pr.search_duplicates}` : ""))}
      ${arrow}
      ${box("LLM 筛选", pr.screened, `BM25 预筛未送审 ${pr.not_screened} · 种子 ${seeds}`)}
      ${arrow}
      ${box("排除", pr.excluded_low_relevance + pr.excluded_retracted + pr.excluded_over_cap,
        `相关度不足 ${pr.excluded_low_relevance} · 已撤稿 ${pr.excluded_retracted} · 超出规模上限 ${pr.excluded_over_cap}`)}
      ${arrow}
      ${box("纳入", pr.included, pr.agent_added ? `含 Agent 新增 ${pr.agent_added}` : "")}
      ${hops ? `<div class="side">${hops}${pr.stop_reason ? `<br/>提前停止：${esc(pr.stop_reason)}` : ""}</div>` : ""}
    </div>`;
  }

  // ---------- Graph ----------
  function nodeLabel(p) {
    const a = (p.authors?.[0] || "").split(/[ ,]/).filter(Boolean);
    const last = a.length ? a[a.length - 1] : "?";
    return `${last} ${p.year ?? ""}`;
  }

  function buildGraph() {
    const els = [];
    for (const p of S.corpus.papers) {
      const cited = p.cited_by_count ?? p.wos_times_cited ?? 0;
      els.push({
        data: {
          id: p.id, label: nodeLabel(p),
          size: 16 + 9 * Math.log10(cited + 1),
          color: css(ORIGIN[p.is_seed ? "seed" : p.origin]?.color || "--o-search"),
          score: p.relevance?.score ?? 0, year: p.year ?? 0,
        },
        classes: p.is_seed ? "seed" : "",
      });
    }
    for (const e of S.corpus.edges) {
      const r = RELATION[e.relation?.label];
      els.push({
        data: { id: `${e.source}->${e.target}`, source: e.source, target: e.target, color: r?.color || css("--edge") },
        classes: e.relation ? "labeled" : "",
      });
    }
    S.cy = cytoscape({
      container: $("#cy"),
      elements: els,
      minZoom: 0.05,
      maxZoom: 3,
      layout: { name: "preset" },
      style: [
        { selector: "node", style: {
          width: "data(size)", height: "data(size)", "background-color": "data(color)",
          "background-opacity": "mapData(score, 0, 10, 0.35, 1)",
          label: "data(label)", "font-size": 12, color: css("--text"), "text-valign": "bottom", "text-margin-y": 5,
          "text-outline-color": css("--bg"), "text-outline-width": 2, "border-width": 0,
        } },
        { selector: "node.seed", style: { shape: "star", "border-width": 2, "border-color": css("--seed") } },
        { selector: "edge", style: {
          width: 1, "line-color": "data(color)", "target-arrow-color": "data(color)", "target-arrow-shape": "triangle",
          "arrow-scale": 0.7, "curve-style": "bezier", opacity: 0.25,
        } },
        { selector: "edge.labeled", style: { width: 1.4, opacity: 0.45 } },
        { selector: ".context-muted", style: { opacity: 0.07 } },
        { selector: "node.context", style: { opacity: 1, "font-weight": 600 } },
        { selector: "edge.context", style: { opacity: 0.95, width: 2.2, "z-index": 10 } },
        { selector: "node:selected", style: { "border-width": 3, "border-color": css("--accent") } },
        { selector: "node.start", style: { "border-width": 4, "border-color": css("--visit"), "border-style": "double" } },
        { selector: ".faded", style: { opacity: 0.12 } },
        { selector: "node.visited", style: { opacity: 1, label: "data(vlabel)", "font-weight": 600, color: css("--visit") } },
        { selector: "node.current", style: { "overlay-color": css("--visit"), "overlay-opacity": 0.25, "overlay-padding": 8 } },
        { selector: "edge.tree", style: { opacity: 1, width: 3, "line-color": css("--visit"), "target-arrow-color": css("--visit") } },
        { selector: "node.hl", style: { "overlay-color": css("--accent"), "overlay-opacity": 0.3, "overlay-padding": 6 } },
        { selector: ".hidden", style: { display: "none" } },
      ],
    });
    S.cy.on("tap", "node", (ev) => showDetail(ev.target.id()));
    S.cy.on("dbltap", "node", (ev) => addStart(ev.target.id()));
    S.cy.on("mouseover", "node", (ev) => highlightNeighborhood(ev.target.id()));
    S.cy.on("mouseout", "node", () => highlightNeighborhood(S.selected));
    S.cy.on("tap", (ev) => { if (ev.target === S.cy) clearFocus(); });
    runLayout();
  }

  const paperNodes = () => S.cy.nodes();

  function fitGraph() {
    const visible = NetworkLayout.visibleGraph(S.cy);
    if (!visible.nodes().length) return;
    S.cy.fit(visible, 55);
    if (S.cy.zoom() > 1.25) { S.cy.zoom(1.25); S.cy.center(visible); }
  }

  function updateGraphStatus() {
    const visible = NetworkLayout.visibleGraph(S.cy);
    $("#cy-empty").hidden = visible.nodes().length > 0;
    $("#graph-status").textContent = `${visible.nodes().length} 篇 · ${visible.edges().length} 条引用`;
  }

  function runLayout() {
    NetworkLayout.run(S.cy, $("#spacing").value, !!cytoscape("layout", "fcose"));
    fitGraph();
    updateGraphStatus();
    highlightNeighborhood(S.selected);
  }

  function highlightNeighborhood(id) {
    S.cy.batch(() => {
      S.cy.elements().removeClass("context context-muted");
      // Playback already has its own emphasis; never obscure its tree edges.
      if (!id || S.visits.length) return;
      const n = S.cy.$id(id);
      if (!n.length || n.hasClass("hidden")) return;
      const visible = NetworkLayout.visibleGraph(S.cy);
      const neighborhood = n.closedNeighborhood().intersection(visible);
      visible.difference(neighborhood).addClass("context-muted");
      neighborhood.addClass("context");
    });
  }

  function clearFocus() {
    S.selected = null;
    S.cy.$(":selected").unselect();
    $("#clear-focus").hidden = true;
    highlightNeighborhood(null);
  }

  function applyFilters() {
    const q = $("#search").value.trim().toLowerCase();
    const min = +$("#minscore").value;
    const y0 = +$("#year-from").value || -Infinity, y1 = +$("#year-to").value || Infinity;
    $("#minscore-val").textContent = min;
    S.cy.batch(() => {
      paperNodes().forEach((n) => {
        const p = S.byId[n.id()];
        const hay = `${p.title} ${(p.authors || []).join(" ")} ${(p.keywords || []).join(" ")}`.toLowerCase();
        const ok = (p.is_seed || (p.relevance?.score ?? 10) >= min) && (!p.year || (p.year >= y0 && p.year <= y1));
        n.toggleClass("hidden", !ok);
        n.toggleClass("hl", !!q && ok && hay.includes(q));
      });
    });
    updateGraphStatus();
    highlightNeighborhood(S.selected);
  }

  // ---------- Details ----------
  function paperLink(id, extra = "") {
    const p = S.byId[id];
    return p ? `<span class="link" data-goto="${id}">${esc(p.title)}</span> <span class="muted">(${p.year ?? "n.d."})</span>${extra}` : esc(id);
  }

  function showDetail(id) {
    const p = S.byId[id];
    if (!p) return;
    S.selected = id;
    S.cy.$(":selected").unselect();
    S.cy.$id(id).select();
    $("#clear-focus").hidden = false;
    highlightNeighborhood(id);
    const refs = S.corpus.edges.filter((e) => e.source === id);
    const citedBy = S.corpus.edges.filter((e) => e.target === id);
    const relTag = (e) => (e.relation ? ` <span class="rel">[${RELATION[e.relation.label]?.name || e.relation.label}] ${esc(e.relation.rationale)}</span>` : "");
    const origin = ORIGIN[p.origin]?.name || p.origin;
    $("#tab-detail").innerHTML = `
      <div class="detail">
        <h2>${esc(p.title)}</h2>
        <div class="meta">${esc((p.authors || []).slice(0, 8).join(", "))}${p.authors?.length > 8 ? " 等" : ""}<br/>
          ${esc(p.venue || "")} · ${p.year ?? "n.d."}</div>
        <div class="badges">
          ${p.retracted ? '<span class="badge danger">已撤稿</span>' : ""}
          ${p.is_seed ? '<span class="badge seed">种子</span>' : ""}
          <span class="badge">${esc(origin)}${p.hop ? ` · hop ${p.hop}` : ""}</span>
          ${p.relevance ? `<span class="badge">相关度 ${p.relevance.score}</span>` : ""}
          ${p.relevance?.flag === "no_abstract" ? '<span class="badge">仅凭标题评分</span>' : ""}
          ${p.cited_by_count != null ? `<span class="badge">OpenAlex 被引 ${p.cited_by_count}</span>` : ""}
          ${p.wos_times_cited != null ? `<span class="badge">WoS 被引 ${p.wos_times_cited}</span>` : ""}
        </div>
        <div>
          ${p.doi ? `<a href="https://doi.org/${esc(p.doi)}" target="_blank" rel="noopener">DOI</a> · ` : ""}
          ${/^W\d+$/.test(p.id) ? `<a href="https://openalex.org/${esc(p.id)}" target="_blank" rel="noopener">OpenAlex</a> · ` : ""}
          <span class="link" data-addstart="${p.id}">添加为起点</span>
        </div>
        ${p.relevance?.reason ? `<h4>相关性理由</h4><div>${esc(p.relevance.reason)}</div>` : ""}
        <h4>摘要</h4><p class="abs">${esc(p.abstract || "（无摘要）")}</p>
        ${p.keywords?.length ? `<h4>关键词</h4><div class="muted">${esc(p.keywords.join("; "))}</div>` : ""}
        <h4>引用了语料库内 ${refs.length} 篇（外部另有 ${p.external_refs_count ?? 0} 篇）</h4>
        <ul>${refs.map((e) => `<li>${paperLink(e.target, relTag(e))}</li>`).join("")}</ul>
        <h4>被语料库内 ${citedBy.length} 篇引用（外部另有 ${p.external_cited_by ?? 0} 次）</h4>
        <ul>${citedBy.map((e) => `<li>${paperLink(e.source, relTag(e))}</li>`).join("")}</ul>
        ${p.notes?.length ? `<h4>备注</h4><ul>${p.notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>` : ""}
      </div>`;
    switchTab("detail");
  }

  function focusNode(id) {
    const n = S.cy.$id(id);
    if (!n.length) return;
    // A detail link may point outside the current year/score filter.
    if (n.hasClass("hidden")) { showDetail(id); return; }
    S.cy.animate({ center: { eles: n }, zoom: Math.max(S.cy.zoom(), 1.1) }, { duration: 300 });
    showDetail(id);
  }

  // ---------- Start points ----------
  function addStart(id) {
    if (!S.starts.includes(id)) S.starts.push(id);
    renderStarts();
  }
  function renderStarts() {
    S.cy.nodes().removeClass("start");
    S.starts.forEach((id) => S.cy.$id(id).addClass("start"));
    $("#starts").innerHTML = S.starts.length
      ? S.starts.map((id) => `<span class="chip" data-rmstart="${id}" title="${esc(S.byId[id]?.title)}">${esc(nodeLabel(S.byId[id]))}</span>`).join("")
      : '<span class="muted">尚未选择起点</span>';
  }

  // ---------- Traversal and playback ----------
  async function runTraversal() {
    if (!S.starts.length) {
      if (S.selected) addStart(S.selected);
      else return alert("请先双击节点设置遍历起点");
    }
    const qs = new URLSearchParams({ mode: S.mode, direction: $("#direction").value, depth: $("#depth").value });
    S.starts.forEach((s) => qs.append("start", s));
    const res = await fetch(`/api/traverse?${qs}`);
    if (!res.ok) return alert((await res.json()).detail || "遍历失败");
    S.visits = (await res.json()).visits;
    resetPlayback();
    renderVisitList();
    play();
  }

  function resetPlayback() {
    stop();
    S.step = 0;
    S.cy.batch(() => {
      S.cy.elements().removeClass("visited current tree context context-muted");
      S.cy.elements().addClass("faded");
      S.cy.nodes().forEach((n) => n.removeData("vlabel"));
    });
    updatePos();
  }

  function clearTraversal() {
    stop();
    S.visits = [];
    S.step = 0;
    S.cy.elements().removeClass("visited current tree faded");
    $("#visit-list").innerHTML = "";
    updatePos();
    highlightNeighborhood(S.selected);
  }

  function treeEdge(v) {
    if (!v.parent) return S.cy.collection();
    // via=refs: parent -> v (parent cites v); via=cited_by: v -> parent
    return v.via === "refs" ? S.cy.$id(`${v.parent}->${v.id}`) : S.cy.$id(`${v.id}->${v.parent}`);
  }

  function stepOnce() {
    if (S.step >= S.visits.length) return false;
    const v = S.visits[S.step];
    S.cy.nodes(".current").removeClass("current");
    const n = S.cy.$id(v.id);
    n.data("vlabel", `#${v.order + 1} ${nodeLabel(S.byId[v.id])}`);
    n.removeClass("faded").addClass("visited current");
    treeEdge(v).removeClass("faded").addClass("tree");
    S.step++;
    updatePos();
    return true;
  }

  function play() {
    if (S.timer) return stop();
    $("#p-play").textContent = "⏸";
    const tick = () => {
      if (!stepOnce()) return stop();
      S.timer = setTimeout(tick, 1250 - +$("#p-speed").value);
    };
    tick();
  }
  function stop() {
    clearTimeout(S.timer);
    S.timer = null;
    $("#p-play").textContent = "▶";
  }
  function showAll() {
    stop();
    S.cy.batch(() => { while (stepOnce()); });
  }

  function renderVisitList() {
    $("#visit-list").innerHTML = S.visits.map((v) => {
      const p = S.byId[v.id];
      const arrow = v.via === "refs" ? "↑" : v.via === "cited_by" ? "↓" : "●";
      return `<li data-goto="${v.id}" data-i="${v.order}"><span class="ord">${v.order + 1}</span>` +
        `<span class="dep" title="深度">${arrow}${v.depth}</span><span class="t" title="${esc(p.title)}">${esc(p.year ?? "")} ${esc(p.title)}</span></li>`;
    }).join("");
  }

  function updatePos() {
    $("#p-pos").textContent = S.visits.length ? `${S.step}/${S.visits.length}` : "";
    $$("#visit-list li").forEach((li) => {
      const i = +li.dataset.i;
      li.classList.toggle("done", i < S.step);
      li.classList.toggle("cur", i === S.step - 1);
    });
    const cur = $("#visit-list li.cur");
    if (cur) cur.scrollIntoView({ block: "nearest" });
  }

  // ---------- Event binding ----------
  function switchTab(t) {
    $$(".tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === t));
    $$(".tab").forEach((d) => d.classList.toggle("on", d.id === `tab-${t}`));
  }

  function bindUI() {
    renderStarts();
    ["#search", "#minscore", "#year-from", "#year-to"].forEach((s) => $(s).addEventListener("input", applyFilters));
    ["#minscore", "#year-from", "#year-to"].forEach((s) => $(s).addEventListener("change", runLayout));
    $("#spacing").addEventListener("change", runLayout);
    $("#relayout").addEventListener("click", runLayout);
    $("#fit").addEventListener("click", fitGraph);
    $("#clear-focus").addEventListener("click", clearFocus);
    $("#expand-graph").addEventListener("click", () => {
      const expanded = $("main").classList.toggle("graph-expanded");
      $("#expand-graph").textContent = expanded ? "收起画布" : "展开画布";
      $("#expand-graph").setAttribute("aria-pressed", String(expanded));
      S.cy.resize();
      fitGraph();
    });
    $$("#mode button").forEach((b) => b.addEventListener("click", () => {
      S.mode = b.dataset.v;
      $$("#mode button").forEach((x) => x.classList.toggle("on", x === b));
    }));
    $("#run").addEventListener("click", runTraversal);
    $("#clear-trav").addEventListener("click", clearTraversal);
    $("#p-play").addEventListener("click", play);
    $("#p-step").addEventListener("click", () => { stop(); stepOnce(); });
    $("#p-all").addEventListener("click", showAll);
    $$(".tabs button").forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.tab)));
    document.body.addEventListener("click", (e) => {
      const t = e.target.closest("[data-goto],[data-addstart],[data-rmstart]");
      if (!t) return;
      if (t.dataset.goto) focusNode(t.dataset.goto);
      else if (t.dataset.addstart) addStart(t.dataset.addstart);
      else if (t.dataset.rmstart) { S.starts = S.starts.filter((x) => x !== t.dataset.rmstart); renderStarts(); }
    });
  }

  init().catch((e) => { document.body.innerHTML = `<pre class="err">加载失败：${esc(e.stack || e)}</pre>`; });
})();

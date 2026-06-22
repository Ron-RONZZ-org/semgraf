/* semgraf frontend — single-page application */

(function () {
  'use strict';

  // ── State ────────────────────────────────────────────
  const state = {
    graph: null,          // vis.Network instance
    nodes: null,          // vis.DataSet
    edges: null,          // vis.DataSet
    nodeMap: new Map(),   // uri → vis node id
    edgeMap: new Map(),   // pred+target → vis edge id
    selectedUri: null,
    predicates: [],       // from /api/stats
    loadedUris: new Set(),
    searchTimeout: null,
  };

  // DOM refs
  const $ = (id) => document.getElementById(id);
  const searchInput = $('search-input');
  const searchDropdown = $('search-dropdown');
  const graphContainer = $('graph-container');
  const graphEmpty = $('graph-empty');
  const entityPanel = $('entity-panel');
  const entityTitle = $('entity-title');
  const entityContent = $('entity-content');
  const entityClose = $('entity-close');
  const sparqlToggle = $('sparql-toggle');
  const sparqlPanel = $('sparql-panel');
  const sparqlInput = $('sparql-input');
  const sparqlRun = $('sparql-run');
  const sparqlGraph = $('sparql-graph');
  const sparqlResults = $('sparql-results');
  const statusText = $('status-text');
  const filterDisplay = $('filter-display');
  const statsDisplay = $('stats-display');
  const toastContainer = $('toast-container');
  const loadingSpinner = $('loading-spinner');
  const spinnerClass = 'loading-spinner';

  // ── Utilities ────────────────────────────────────────
  function showToast(msg, type) {
    const el = document.createElement('div');
    el.className = 'toast ' + (type || 'info');
    el.textContent = msg;
    toastContainer.appendChild(el);
    setTimeout(() => { el.remove(); }, 4000);
  }

  function showLoading() { loadingSpinner.classList.remove('hidden'); }
  function hideLoading() { loadingSpinner.classList.add('hidden'); }

  async function apiFetch(path) {
    const resp = await fetch(path);
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      throw new Error(body.error || `HTTP ${resp.status}`);
    }
    return resp.json();
  }

  // ── Graph Initialization ─────────────────────────────
  async function initGraph() {
    showLoading();
    try {
      const stats = await apiFetch('/api/stats');
      renderStats(stats);

      if (stats.triple_count === 0) {
        graphEmpty.classList.remove('hidden');
        statusText.textContent = 'No triples loaded.';
        hideLoading();
        return;
      }

      graphEmpty.classList.add('hidden');
      state.predicates = stats.predicates || [];

      // Initial load: SPARQL CONSTRUCT to get a connected subgraph
      await loadInitialGraph(stats);
      statusText.textContent = `${stats.subject_count} nodes · ${stats.triple_count} triples`;
    } catch (err) {
      showToast('Failed to load graph: ' + err.message, 'error');
      statusText.textContent = 'Error loading data';
    } finally {
      hideLoading();
    }
  }

  async function loadInitialGraph(stats) {
    // SPARQL query: get all triples with a LIMIT for initial view
    // We fetch a manageable subset and expand on demand.
    const query = 'SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 2000';
    const data = await apiFetch('/api/sparql?query=' + encodeURIComponent(query));
    const bindings = data.results && data.results.bindings;

    if (!bindings || bindings.length === 0) {
      graphEmpty.classList.remove('hidden');
      return;
    }

    buildGraphFromBindings(bindings);
  }

  function buildGraphFromBindings(bindings) {
    state.nodes = new vis.DataSet([]);
    state.edges = new vis.DataSet([]);
    state.nodeMap.clear();
    state.edgeMap.clear();
    state.loadedUris.clear();

    const nodeSet = new Map();  // uri → {id, label, group}

    function ensureNode(uri, label, group) {
      if (!nodeSet.has(uri)) {
        const id = uri;
        const nodeLabel = label || uri.split('/').pop() || uri;
        nodeSet.set(uri, { id, label: nodeLabel, group: group || 0, title: uri });
        state.nodeMap.set(uri, id);
      }
      return nodeSet.get(uri);
    }

    bindings.forEach((b, i) => {
      const s = b.s.value;
      const p = b.p.value;
      const o = b.o;

      const sNode = ensureNode(s, null, 0);
      let oNode;
      if (o.type === 'uri') {
        oNode = ensureNode(o.value, null, 1);
      } else {
        // Literal — create a small literal node
        const litId = '_:lit-' + i;
        const litLabel = o.value.substring(0, 40) + (o.value.length > 40 ? '…' : '');
        oNode = { id: litId, label: litLabel, group: 2, shape: 'box', title: o.value };
        nodeSet.set(litId, oNode);
      }

      const edgeId = p + '-' + sNode.id + '-' + oNode.id;
      if (!state.edgeMap.has(edgeId)) {
        state.edgeMap.set(edgeId, edgeId);
        state.edges.add({ id: edgeId, from: sNode.id, to: oNode.id, label: prefixLabel(p), title: p, arrows: 'to', font: { size: 10 }, color: { opacity: 0.6 } });
      }
    });

    // Add all nodes
    const nodesArray = Array.from(nodeSet.values());
    state.nodes.add(nodesArray);
    nodesArray.forEach(n => state.loadedUris.add(n.id));

    renderGraph();
  }

  function prefixLabel(uri) {
    // Simple prefix compression using known prefixes
    const prefixes = [
      ['rdf:', 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'],
      ['rdfs:', 'http://www.w3.org/2000/01/rdf-schema#'],
      ['owl:', 'http://www.w3.org/2002/07/owl#'],
      ['xsd:', 'http://www.w3.org/2001/XMLSchema#'],
      ['skos:', 'http://www.w3.org/2004/02/skos/core#'],
      ['foaf:', 'http://xmlns.com/foaf/0.1/'],
      ['dc:', 'http://purl.org/dc/elements/1.1/'],
      ['dct:', 'http://purl.org/dc/terms/'],
    ];
    for (const [pfx, ns] of prefixes) {
      if (uri.startsWith(ns)) return pfx + uri.slice(ns.length);
    }
    // Fallback: last segment
    const last = uri.split('/').pop() || uri.split(':').pop() || uri;
    return last.length < 30 ? last : last.slice(0, 27) + '…';
  }

  function renderGraph() {
    const container = graphContainer;
    // Remove empty message if nodes exist
    if (state.nodes.length > 0) {
      graphEmpty.classList.add('hidden');
    }

    const data = { nodes: state.nodes, edges: state.edges };
    const options = {
      physics: {
        solver: 'barnesHut',
        barnesHut: { gravitationalConstant: -3000, centralGravity: 0.3, springLength: 200 },
        stabilization: { iterations: 100 },
      },
      interaction: { hover: true, tooltipDelay: 200 },
      edges: {
        smooth: { type: 'continuous' },
        font: { size: 10, color: '#666' },
      },
      nodes: {
        font: { size: 14, face: 'system-ui' },
        borderWidth: 2,
        shape: 'dot',
        size: 20,
        color: {
          background: '#4361ee',
          border: '#3a56d4',
          highlight: { background: '#e63946', border: '#c1121f' },
        },
        groupColors: {
          0: { background: '#4361ee', border: '#3a56d4' },
          1: { background: '#2ec4b6', border: '#25a99d' },
          2: { background: '#ff9f1c', border: '#e08a16' },
        },
      },
      groups: {
        0: { color: { background: '#4361ee', border: '#3a56d4' }, font: { size: 14 } },
        1: { color: { background: '#2ec4b6', border: '#25a99d' }, font: { size: 14 } },
        2: { color: { background: '#ff9f1c', border: '#e08a16' }, font: { size: 12, color: '#333' }, shape: 'box' },
      },
    };

    state.graph = new vis.Network(container, data, options);

    // Click → entity panel
    state.graph.on('click', function (params) {
      if (params.nodes.length > 0) {
        const nodeId = params.nodes[0];
        selectNode(nodeId);
      } else {
        deselectNode();
      }
    });

    // Double-click → expand node neighborhood
    state.graph.on('doubleClick', function (params) {
      if (params.nodes.length > 0) {
        expandNode(params.nodes[0]);
      }
    });

    // Stabilization done → disable physics for performance
    state.graph.once('stabilizationIterationsDone', function () {
      state.graph.setOptions({ physics: false });
    });
  }

  // ── Node Selection ───────────────────────────────
  async function selectNode(nodeId) {
    if (nodeId.startsWith('_:lit-')) return; // literal nodes aren't real resources
    state.selectedUri = nodeId;
    showLoading();

    try {
      const data = await apiFetch('/api/node?uri=' + encodeURIComponent(nodeId));
      renderEntityPanel(data);

      // Highlight in graph
      state.graph.selectNodes([nodeId]);
      state.graph.focus(nodeId, { scale: 1.5, animation: true });
    } catch (err) {
      showToast('Error loading node: ' + err.message, 'error');
    } finally {
      hideLoading();
    }
  }

  function deselectNode() {
    state.selectedUri = null;
    entityPanel.classList.add('hidden');
    state.graph && state.graph.unselectAll();
  }

  function renderEntityPanel(data) {
    entityTitle.textContent = data.label || data.uri;
    entityPanel.classList.remove('hidden');
    let html = '';

    // Labels
    if (data.labels && data.labels.length > 0) {
      html += '<div class="entity-section"><h4>Labels</h4><ul>';
      data.labels.forEach(l => { html += `<li>${escHtml(l)}</li>`; });
      html += '</ul></div>';
    }

    // Types
    if (data.types && data.types.length > 0) {
      html += '<div class="entity-section"><h4>Types</h4><ul>';
      data.types.forEach(t => {
        html += `<li><span class="badge">${escHtml(t)}</span></li>`;
      });
      html += '</ul></div>';
    }

    // URI
    html += `<div class="entity-section"><h4>URI</h4><div style="font-size:12px;word-break:break-all;color:var(--text-muted)">${escHtml(data.uri)}</div></div>`;

    // Properties
    if (data.properties && data.properties.length > 0) {
      html += '<div class="entity-section"><h4>Properties</h4><ul>';
      data.properties.forEach(prop => {
        const predLabel = prop.predicate.label || prop.predicate.uri;
        html += `<li><span class="pred" title="${escHtml(prop.predicate.uri)}">${escHtml(predLabel)}</span>: `;
        prop.objects.forEach((obj, i) => {
          if (i > 0) html += ', ';
          if (obj.type === 'uri') {
            html += `<a class="node-link" data-uri="${escHtml(obj.uri)}">${escHtml(obj.label || obj.uri)}</a>`;
          } else {
            html += escHtml(obj.value);
            if (obj.lang) html += ` <span class="badge">${escHtml(obj.lang)}</span>`;
          }
        });
        html += '</li>';
      });
      html += '</ul></div>';
    }

    // Outgoing
    if (data.outgoing) {
      html += '<div class="entity-section"><h4>Outgoing</h4>';
      html += renderTripleList(data.outgoing, 'object');
      html += '</div>';
    }

    // Incoming
    if (data.incoming) {
      html += '<div class="entity-section"><h4>Incoming</h4>';
      html += renderTripleList(data.incoming, 'subject');
      html += '</div>';
    }

    entityContent.innerHTML = html;

    // Bind click handlers for node links
    entityContent.querySelectorAll('.node-link').forEach(el => {
      el.addEventListener('click', function () {
        const uri = this.dataset.uri;
        if (uri) selectNode(uri);
      });
    });
  }

  function renderTripleList(section, key) {
    const items = section.items || [];
    if (items.length === 0) return '<div style="color:var(--text-muted)">None</div>';

    let html = '<ul>';
    items.forEach(item => {
      const pred = item.predicate;
      const predLabel = pred.label || pred.uri;
      if (key === 'object') {
        const obj = item.object;
        if (obj.type === 'uri') {
          html += `<li><span class="pred" title="${escHtml(pred.uri)}">${escHtml(predLabel)}</span> → <a class="node-link" data-uri="${escHtml(obj.uri)}">${escHtml(obj.label || obj.uri)}</a></li>`;
        } else {
          html += `<li><span class="pred" title="${escHtml(pred.uri)}">${escHtml(predLabel)}</span> → <span class="badge">${escHtml(obj.value)}</span></li>`;
        }
      } else {
        const sub = item.subject;
        html += `<li><a class="node-link" data-uri="${escHtml(sub.uri)}">${escHtml(sub.label || sub.uri)}</a> — <span class="pred" title="${escHtml(pred.uri)}">${escHtml(predLabel)}</span></li>`;
      }
    });
    html += '</ul>';

    if (section.total > section.limit) {
      html += `<div style="font-size:12px;color:var(--text-muted)">… and ${section.total - section.limit} more</div>`;
    }
    return html;
  }

  // ── Expand Node (double-click) ──────────────────
  async function expandNode(nodeId) {
    if (nodeId.startsWith('_:lit-')) return;
    showLoading();
    try {
      const query = 'CONSTRUCT { <' + nodeId + '> ?p ?o . ?s ?p <' + nodeId + '> } WHERE { { <' + nodeId + '> ?p ?o } UNION { ?s ?p <' + nodeId + '> } }';
      // Use SPARQL SELECT instead of CONSTRUCT for simpler parsing
      const selectQuery = encodeURIComponent('SELECT ?s ?p ?o WHERE { { <' + nodeId + '> ?p ?o } UNION { ?s ?p <' + nodeId + '> } }');
      const data = await apiFetch('/api/sparql?query=' + selectQuery);
      const bindings = data.results && data.results.bindings;
      if (!bindings || bindings.length === 0) return;

      // Add new nodes and edges
      const newNodes = [];
      const newEdges = [];

      bindings.forEach((b, i) => {
        const s = b.s.value;
        const p = b.p.value;
        const o = b.o;

        if (!state.loadedUris.has(s)) {
          state.loadedUris.add(s);
          newNodes.push({ id: s, label: s.split('/').pop() || s, group: 0, title: s });
        }
        if (o.type === 'uri' && !state.loadedUris.has(o.value)) {
          state.loadedUris.add(o.value);
          newNodes.push({ id: o.value, label: o.value.split('/').pop() || o.value, group: 1, title: o.value });
        }

        const edgeId = p + '-' + s + '-' + (o.type === 'uri' ? o.value : '_:lit-' + i);
        if (!state.edgeMap.has(edgeId)) {
          state.edgeMap.set(edgeId, edgeId);
          const to = o.type === 'uri' ? o.value : '_:lit-' + i;
          newEdges.push({ id: edgeId, from: s, to, label: prefixLabel(p), title: p, arrows: 'to', font: { size: 10 }, color: { opacity: 0.6 } });
        }
      });

      if (newNodes.length > 0) state.nodes.add(newNodes);
      if (newEdges.length > 0) state.edges.add(newEdges);

      // Re-enable physics momentarily for the new nodes to settle
      state.graph.setOptions({ physics: true });
      setTimeout(() => { state.graph.setOptions({ physics: false }); }, 2000);
    } catch (err) {
      showToast('Error expanding node: ' + err.message, 'error');
    } finally {
      hideLoading();
    }
  }

  // ── Search ───────────────────────────────────────────
  searchInput.addEventListener('input', function () {
    clearTimeout(state.searchTimeout);
    const q = this.value.trim();
    if (q.length < 2) {
      searchDropdown.classList.add('hidden');
      return;
    }

    state.searchTimeout = setTimeout(async () => {
      try {
        const data = await apiFetch('/api/search?q=' + encodeURIComponent(q) + '&limit=20');
        renderSearchDropdown(data.results || []);
      } catch (err) {
        // silently ignore search errors
      }
    }, 300);
  });

  function renderSearchDropdown(results) {
    if (results.length === 0) {
      searchDropdown.classList.add('hidden');
      return;
    }

    let html = '';
    results.forEach(r => {
      const uri = r.uri;
      const label = r.label || prefixLabel(uri);
      const types = (r.types || []).join(', ');
      html += `<div class="dropdown-item" data-uri="${escHtml(uri)}">
        <div class="label">${escHtml(label)}</div>
        <div class="sub">${escHtml(uri)}${types ? ' · ' + escHtml(types) : ''}</div>
      </div>`;
    });
    searchDropdown.innerHTML = html;
    searchDropdown.classList.remove('hidden');

    // Click handler
    searchDropdown.querySelectorAll('.dropdown-item').forEach(el => {
      el.addEventListener('click', function () {
        const uri = this.dataset.uri;
        searchDropdown.classList.add('hidden');
        searchInput.value = this.querySelector('.label').textContent;
        if (uri) selectNode(uri);
      });
    });
  }

  // Hide dropdown on click outside
  document.addEventListener('click', function (e) {
    if (!e.target.closest('#search-container')) {
      searchDropdown.classList.add('hidden');
    }
  });

  // Keyboard navigation in search
  searchInput.addEventListener('keydown', function (e) {
    const items = searchDropdown.querySelectorAll('.dropdown-item');
    if (items.length === 0) return;

    let idx = Array.from(items).findIndex(el => el.classList.contains('active'));

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (idx >= 0) items[idx].classList.remove('active');
      idx = Math.min(idx + 1, items.length - 1);
      items[idx].classList.add('active');
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (idx >= 0) items[idx].classList.remove('active');
      idx = Math.max(idx - 1, 0);
      items[idx].classList.add('active');
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (idx >= 0) items[idx].click();
    }
  });

  // ── SPARQL Panel ────────────────────────────────────
  sparqlToggle.addEventListener('click', function () {
    sparqlPanel.classList.toggle('hidden');
  });

  sparqlRun.addEventListener('click', async function () {
    const query = sparqlInput.value.trim();
    if (!query) return;

    showLoading();
    try {
      const data = await apiFetch('/api/sparql?query=' + encodeURIComponent(query));
      renderSparqlResults(data);
    } catch (err) {
      sparqlResults.innerHTML = `<div class="toast error">${escHtml(err.message)}</div>`;
    } finally {
      hideLoading();
    }
  });

  function renderSparqlResults(data) {
    if (!data.results || !data.results.bindings || data.results.bindings.length === 0) {
      sparqlResults.innerHTML = '<div style="color:var(--text-muted)">No results.</div>';
      return;
    }

    const vars = data.head && data.head.vars ? data.head.vars : Object.keys(data.results.bindings[0]);
    let html = '<table><thead><tr>';
    vars.forEach(v => { html += `<th>${escHtml(v)}</th>`; });
    html += '</tr></thead><tbody>';

    data.results.bindings.forEach(b => {
      html += '<tr>';
      vars.forEach(v => {
        const cell = b[v];
        if (cell) {
          const val = cell.value || '';
          const type = cell.type || '';
          const datatype = cell.datatype || '';
          let display = val;
          if (type === 'uri') {
            display = `<a class="node-link" data-uri="${escHtml(val)}">${escHtml(prefixLabel(val))}</a>`;
          } else {
            display = escHtml(val);
            if (datatype) display += ` <span class="badge">${escHtml(datatype.split('/').pop())}</span>`;
          }
          html += `<td>${display}</td>`;
        } else {
          html += '<td></td>';
        }
      });
      html += '</tr>';
    });
    html += '</tbody></table>';
    sparqlResults.innerHTML = html;

    // Bind node link clicks in SPARQL results
    sparqlResults.querySelectorAll('.node-link').forEach(el => {
      el.addEventListener('click', function () {
        const uri = this.dataset.uri;
        if (uri) selectNode(uri);
      });
    });
  }

  sparqlGraph.addEventListener('click', async function () {
    const query = sparqlInput.value.trim();
    if (!query) return;

    // Ensure it's a SELECT query that returns s, p, o
    const upper = query.toUpperCase().trim();
    if (!upper.startsWith('SELECT') || !query.toLowerCase().includes('?s') || !query.toLowerCase().includes('?p') || !query.toLowerCase().includes('?o')) {
      showToast('Load as Graph requires a SELECT query with ?s ?p ?o variables', 'error');
      return;
    }

    showLoading();
    try {
      const data = await apiFetch('/api/sparql?query=' + encodeURIComponent(query));
      const bindings = data.results && data.results.bindings;
      if (!bindings || bindings.length === 0) {
        showToast('No results to display', 'info');
        return;
      }

      // Add to existing graph
      const newNodes = [];
      const newEdges = [];
      const tempMap = new Map();

      bindings.forEach((b, i) => {
        const s = b.s.value;
        const p = b.p.value;
        const o = b.o;

        if (!state.loadedUris.has(s) && !tempMap.has(s)) {
          tempMap.set(s, true);
          newNodes.push({ id: s, label: s.split('/').pop() || s, group: 0, title: s });
        }
        if (o.type === 'uri') {
          if (!state.loadedUris.has(o.value) && !tempMap.has(o.value)) {
            tempMap.set(o.value, true);
            newNodes.push({ id: o.value, label: o.value.split('/').pop() || o.value, group: 1, title: o.value });
          }
        }

        const toId = o.type === 'uri' ? o.value : '_:lit-' + i;
        const edgeId = p + '-' + s + '-' + toId;
        if (!state.edgeMap.has(edgeId)) {
          state.edgeMap.set(edgeId, edgeId);
          newEdges.push({ id: edgeId, from: s, to: toId, label: prefixLabel(p), title: p, arrows: 'to', font: { size: 10 }, color: { opacity: 0.6 } });
        }
      });

      if (newNodes.length > 0) {
        state.nodes.add(newNodes);
        newNodes.forEach(n => state.loadedUris.add(n.id));
      }
      if (newEdges.length > 0) state.edges.add(newEdges);

      state.graph.setOptions({ physics: true });
      setTimeout(() => { state.graph.setOptions({ physics: false }); }, 2000);
      showToast(`Added ${bindings.length} triples to graph`, 'info');
    } catch (err) {
      showToast('Error: ' + err.message, 'error');
    } finally {
      hideLoading();
    }
  });

  // ── Entity Panel Close ──────────────────────────────
  entityClose.addEventListener('click', deselectNode);

  // ── Stats Display ───────────────────────────────────
  function renderStats(stats) {
    statsDisplay.textContent = `${stats.triple_count} triples · ${stats.subject_count} subjects · ${stats.predicate_count} predicates`;
  }

  // ── HTML Escaping ───────────────────────────────────
  function escHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // ── Boot ────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', initGraph);

})();

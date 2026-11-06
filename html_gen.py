"""
html_gen.py -- builds the interactive HTML reference from an analyzed
project. Imported by app.py. The CSS and interaction shell (tabs, search,
filter, accordions) are fixed chrome; only the data feeding them is
generated per-project.
"""
import json
import re

from app import (
    summarize_formula, detect_calc_type, detect_status, page_content_visuals,
    CONTENT_CATEGORIES, classify_dim_fact,
)

CSS = r"""
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;font-family:'Segoe UI',sans-serif;font-size:12px;background:#F5F6F7;color:#1A1A2E;overflow:hidden}
#shell{display:flex;flex-direction:column;height:100vh;width:100vw;overflow:hidden}
#topbar{background:#1a2f4a;color:#fff;padding:10px 20px;display:flex;align-items:center;justify-content:space-between;flex-shrink:0;border-bottom:3px solid #2E75B6}
#topbar h1{font-size:15px;font-weight:700;letter-spacing:.04em}
#topbar .sub{font-size:10px;color:rgba(255,255,255,.5);margin-top:2px}
#toolbar{background:#fff;border-bottom:1px solid #E3E5E8;padding:8px 18px;display:flex;align-items:center;gap:10px;flex-shrink:0;flex-wrap:wrap}
#toolbar input[type=text]{padding:6px 10px;border:1.5px solid #E3E5E8;border-radius:5px;font-size:12px;width:300px;outline:none}
#toolbar input[type=text]:focus{border-color:#2E75B6}
#toolbar select{padding:6px 8px;border:1.5px solid #E3E5E8;border-radius:5px;font-size:12px;background:#fff;outline:none}
#toolbar label{font-size:11px;color:#5A6A85;font-weight:600}
#resultBadge{font-size:11px;background:#F5F6F7;border-radius:10px;padding:3px 10px;color:#5A6A85}
#clearBtn{padding:5px 12px;background:#F5F6F7;border:1px solid #E3E5E8;border-radius:5px;cursor:pointer;font-size:11px;color:#5A6A85}
#clearBtn:hover{background:#E3E5E8}
#tabs{background:#fff;border-bottom:1px solid #E3E5E8;display:flex;flex-shrink:0;padding:0 18px}
.tab{padding:9px 16px 8px;border:none;background:none;cursor:pointer;font-size:12px;font-weight:600;color:#5A6A85;border-bottom:2.5px solid transparent}
.tab.active{color:#1a2f4a;border-bottom-color:#2E75B6}
.tab-ct{background:#EAF1FB;color:#2E75B6;font-size:10px;font-weight:700;border-radius:8px;padding:1px 5px;margin-left:4px}
.tab.active .tab-ct{background:#1a2f4a;color:#fff}
#body-area{flex:1;overflow:hidden;position:relative}
.panel{display:none;position:absolute;inset:0;overflow:hidden}
.panel.active{display:block}
.panel-scroll{width:100%;height:100%;overflow:auto;padding:14px 18px 20px}
.page-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(560px,1fr));gap:16px;padding-bottom:20px}
.page-card{background:#fff;border:1px solid #E3E5E8;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,.06);overflow:hidden}
.page-card-header{padding:10px 14px;display:flex;align-items:center;gap:10px;border-bottom:1px solid #E3E5E8;cursor:pointer;user-select:none}
.page-card-header:hover{background:#F8FAFF}
.page-icon{width:32px;height:32px;border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:13px;flex-shrink:0;color:#fff;font-weight:700}
.page-title{font-weight:700;font-size:12px;color:#1a2f4a;flex:1}
.page-meta{font-size:10px;color:#5A6A85}
.vis-badge{font-size:10px;font-weight:700;padding:2px 7px;border-radius:8px;margin-right:4px}
.vb-green{background:#E6F4EA;color:#14532D}
.vb-blue{background:#EAF1FB;color:#1e3a5f}
.vb-amber{background:#FEF3CD;color:#92400E}
.vb-purple{background:#EDE9FE;color:#4C1D95}
.vb-grey{background:#F1F5F9;color:#475569}
.page-body{display:none;padding:12px 14px 14px}
.page-body.open{display:block}
.vis-table{width:100%;border-collapse:collapse;font-size:11px}
.vis-table th{background:#F5F6F7;color:#5A6A85;font-weight:700;text-transform:uppercase;font-size:9.5px;letter-spacing:.05em;padding:5px 8px;text-align:left;border-bottom:1px solid #E3E5E8}
.vis-table td{padding:6px 8px;border-bottom:1px solid #F0F2F5;vertical-align:top;line-height:1.5}
.vis-table tr:last-child td{border-bottom:none}
.vis-table tr:hover td{background:#F8FAFF}
.chip{display:inline-block;border-radius:3px;font-size:10px;padding:1px 5px;margin:1px;font-family:Consolas,monospace}
.chip-m{background:#EDE9FE;color:#4C1D95}
.chip-c{background:#EEF2FF;color:#3730A3}
.chip-f{background:#ECFDF5;color:#065F46}
.vtype{display:inline-block;padding:2px 7px;border-radius:8px;font-size:10px;font-weight:700;white-space:nowrap}
.vt-html{background:#FFF7ED;color:#C2410C}
.vt-tbl{background:#EAF1FB;color:#1e3a5f}
.vt-slicer{background:#E6F4EA;color:#14532D}
.vt-card{background:#FDF4FF;color:#6B21A8}
.vt-chart{background:#FDECEA;color:#9B1C1C}
.vt-nav{background:#F1F5F9;color:#64748B}
.vt-other{background:#F1F5F9;color:#475569}
mark{background:#FFF176;border-radius:2px;padding:0 1px}
.empty-state{text-align:center;padding:60px 20px;color:#5A6A85}
.empty-state h3{font-size:15px;color:#1a2f4a;margin-bottom:6px}
.tbl-wrap{background:#fff;border-radius:7px;border:1px solid #E3E5E8;box-shadow:0 1px 4px rgba(0,0,0,.07);display:table;min-width:100%}
table.main-tbl{border-collapse:collapse;white-space:nowrap;font-size:11.5px}
table.main-tbl th{background:#1a2f4a;color:#fff;padding:8px 12px;font-size:10px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;text-align:left;position:sticky;top:0;z-index:10;white-space:nowrap;box-shadow:0 3px 0 #1a2f4a,0 4px 6px rgba(0,0,0,.2)}
table.main-tbl td{padding:8px 12px;border-bottom:1px solid #F0F2F5;border-right:1px solid #F0F2F5;vertical-align:top;white-space:normal;line-height:1.5}
table.main-tbl td:last-child{border-right:none}
table.main-tbl tr:last-child td{border-bottom:none}
table.main-tbl tr:hover td{background:#F8FAFF}
.domain-row td{background:#1a2f4a!important;color:#7EB3D8;font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;padding:5px 12px!important}
.badge{display:inline-block;padding:2px 7px;border-radius:8px;font-size:10px;font-weight:700;white-space:nowrap}
.b-ALL{background:#F1F5F9;color:#334155}
.s-live{background:#E6F4EA;color:#14532D;display:inline-flex;align-items:center;gap:3px;padding:2px 7px;border-radius:8px;font-size:10px;font-weight:700}
.s-tbc{background:#FEF3CD;color:#92400E;display:inline-flex;align-items:center;gap:3px;padding:2px 7px;border-radius:8px;font-size:10px;font-weight:700}
.formula{font-family:Consolas,monospace;font-size:10px;background:#F8FAFF;border:1px solid #E0E8F4;border-radius:4px;padding:4px 6px;white-space:pre-wrap;word-break:break-word;display:block;line-height:1.5;color:#1a2f4a}
.panel-scroll::-webkit-scrollbar,.panel-hscroll::-webkit-scrollbar{width:10px;height:10px}
.panel-scroll::-webkit-scrollbar-track,.panel-hscroll::-webkit-scrollbar-track{background:#E3E5E8;border-radius:5px}
.panel-scroll::-webkit-scrollbar-thumb,.panel-hscroll::-webkit-scrollbar-thumb{background:#1a2f4a;border-radius:5px;border:2px solid #E3E5E8}
.panel-hscroll{width:100%;height:100%;overflow-x:auto;overflow-y:hidden;padding:14px 18px 0 18px}
.panel-vscroll{height:100%;overflow-x:visible;overflow-y:auto;padding-bottom:20px}
.stat-bar{display:flex;gap:12px;margin-bottom:14px;flex-wrap:wrap}
.stat-pill{background:#fff;border:1px solid #E3E5E8;border-radius:8px;padding:8px 16px;text-align:center;min-width:100px}
.stat-pill .n{font-size:22px;font-weight:700;color:#1a2f4a}
.stat-pill .l{font-size:10px;color:#5A6A85;text-transform:uppercase;letter-spacing:.05em;margin-top:2px}
.flag-nonprod{background:#FDECEA;color:#9B1C1C;font-size:9px;font-weight:700;border-radius:6px;padding:1px 6px;margin-left:6px}
"""

RENDER_JS = r"""
function getVtClass(t){
  if(t==='HTML Content (custom visual)') return 'vt-html';
  if(t==='Table') return 'vt-tbl';
  if(t==='Slicer') return 'vt-slicer';
  if(t==='KPI Card') return 'vt-card';
  if(t==='Chart') return 'vt-chart';
  if(t==='Navigation/Decorative'||t==='Layout group') return 'vt-nav';
  return 'vt-other';
}
function esc(s){
  if (typeof s !== 'string') return s;
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function hl(text,term){
  if(typeof text!=='string') return text;
  const escaped = esc(text);
  if(!term) return escaped;
  const escTerm = term.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  return escaped.replace(new RegExp(`(${escTerm})`,'gi'),'<mark>$1</mark>');
}
function badge(d){
  const st = DOMAIN_STYLE[d] || {fg:'334155',bg:'F1F5F9'};
  return `<span class="badge" style="background:#${st.bg};color:#${st.fg}">${esc(DOMAIN_LABELS[d]||d)}</span>`;
}
function status(s){return `<span class="${s==='Live'?'s-live':'s-tbc'}">\u25CF ${esc(s)}</span>`;}
function tbls(arr){return (arr||[]).map(t=>`<span class="chip chip-f">${esc(t)}</span>`).join(' ')||'\u2014';}
function cols_html(arr){return (arr||[]).map(c=>`<span class="chip chip-c">${esc(c)}</span>`).join('')||'\u2014';}

function renderPages(term, domain) {
  const grid = document.getElementById('pageGrid');
  grid.innerHTML = '';
  let shown = 0;
  const termLow = (term||'').toLowerCase();

  PAGES.forEach((pg) => {
    if (domain && pg.domain !== domain) return;
    const filteredVis = pg.visuals.filter(v => {
      if (!termLow) return true;
      return v.title.toLowerCase().includes(termLow)
        || v.type.toLowerCase().includes(termLow)
        || v.purpose.toLowerCase().includes(termLow)
        || v.measures.some(m => m.toLowerCase().includes(termLow))
        || v.cols.some(c => c.toLowerCase().includes(termLow));
    });
    const pageMatch = !termLow || pg.name.toLowerCase().includes(termLow)
      || pg.desc.toLowerCase().includes(termLow) || filteredVis.length > 0;
    if (!pageMatch) return;
    shown++;

    const st = DOMAIN_STYLE[pg.domain] || {fg:'334155',bg:'1a2f4a'};
    const visList = termLow ? filteredVis : pg.visuals;
    const htmlVis = visList.filter(v=>v.type==='HTML Content (custom visual)').length;
    const tblVis = visList.filter(v=>v.type==='Table').length;
    const slicerVis = visList.filter(v=>v.type==='Slicer').length;
    const chartVis = visList.filter(v=>v.type==='Chart'||v.type==='KPI Card').length;

    const card = document.createElement('div');
    card.className = 'page-card';
    card.innerHTML = `
      <div class="page-card-header" onclick="toggleCard(this)">
        <div class="page-icon" style="background:#1a2f4a">${esc(pg.name.substring(0,2).toUpperCase())}</div>
        <div style="flex:1">
          <div class="page-title">${hl(pg.name, term)} ${pg.nonprod?`<span class="flag-nonprod">${esc(pg.nonprod)}</span>`:''}${pg.hidden?`<span class="flag-nonprod" style="background:#EAF1FB;color:#1e3a5f">hidden from nav</span>`:''}</div>
          <div class="page-meta" style="margin-top:3px">${hl(pg.desc.substring(0,110), term)}${pg.desc.length>110?'\u2026':''}</div>
        </div>
        <div>
          ${htmlVis?`<span class="vis-badge vb-amber">${htmlVis} HTML</span>`:''}
          ${tblVis?`<span class="vis-badge vb-blue">${tblVis} Table</span>`:''}
          ${slicerVis?`<span class="vis-badge vb-green">${slicerVis} Slicer</span>`:''}
          ${chartVis?`<span class="vis-badge vb-purple">${chartVis} Card/Chart</span>`:''}
          <span style="color:#9CA3AF;margin-left:6px;font-size:14px" class="toggle-icon">\u25BC</span>
        </div>
      </div>
      <div class="page-body ${term?'open':''}">
        <p style="font-size:11px;color:#5A6A85;margin-bottom:8px">${hl(pg.desc, term)}</p>
        ${pg.slicers.length ? `<div style="margin-bottom:8px;font-size:10px;color:#5A6A85">\u{1F4CC} <b>Filters on this page:</b> ${pg.slicers.map(s=>`<span class="chip chip-c">${esc(s)}</span>`).join('')}</div>` : ''}
        <table class="vis-table">
          <thead><tr>
            <th>#</th><th>Visual Type</th><th>Title / What it shows</th>
            <th style="min-width:180px">Measures Used</th>
            <th style="min-width:140px">Columns Used</th>
          </tr></thead>
          <tbody>
            ${visList.map((v,i) => `
            <tr>
              <td style="color:#9CA3AF;width:24px">${i+1}</td>
              <td><span class="vtype ${getVtClass(v.type)}">${hl(v.type,term)}</span></td>
              <td style="min-width:180px">
                <div style="font-weight:600;color:#1a2f4a;margin-bottom:2px">${hl(v.title||'\u2014',term)}</div>
                <div style="color:#5A6A85;font-size:10px">${hl(v.purpose,term)}</div>
              </td>
              <td>${v.measures.map(m=>`<span class="chip chip-m">${hl(m,term)}</span>`).join(' ')||'\u2014'}</td>
              <td>${v.cols.map(c=>`<span class="chip chip-c">${hl(c,term)}</span>`).join(' ')||'\u2014'}</td>
            </tr>`).join('')}
          </tbody>
        </table>
      </div>`;
    grid.appendChild(card);
  });

  document.getElementById('pagesEmpty').style.display = shown === 0 ? 'block' : 'none';
  document.getElementById('resultBadge').textContent = `${shown} page${shown!==1?'s':''}`;
  document.getElementById('ct-pages').textContent = shown;

  const totalVis = PAGES.reduce((s,p)=>s+p.visuals.length,0);
  const totalMeasures = [...new Set(PAGES.flatMap(p=>p.visuals.flatMap(v=>v.measures)))].length;
  document.getElementById('statBar').innerHTML = `
    <div class="stat-pill"><div class="n">${PAGES.length}</div><div class="l">Report Pages</div></div>
    <div class="stat-pill"><div class="n">${totalVis}</div><div class="l">Data Visuals</div></div>
    <div class="stat-pill"><div class="n">${totalMeasures}</div><div class="l">Unique Measures Used</div></div>
    <div class="stat-pill"><div class="n">${RAW.length}</div><div class="l">Total Measures</div></div>
    <div class="stat-pill"><div class="n">${HTML_M.length}</div><div class="l">HTML/Display Measures</div></div>
    <div class="stat-pill"><div class="n">${SCHEMA.length}</div><div class="l">Tables / Views</div></div>
  `;
}

function toggleCard(header) {
  const body = header.nextElementSibling;
  const icon = header.querySelector('.toggle-icon');
  body.classList.toggle('open');
  icon.textContent = body.classList.contains('open') ? '\u25B2' : '\u25BC';
}

function renderVisMap(term, domain) {
  const tbody = document.getElementById('vismapBody');
  tbody.innerHTML = '';
  let row = 0;
  const termLow = (term||'').toLowerCase();
  PAGES.forEach(pg => {
    if (domain && pg.domain !== domain) return;
    pg.visuals.forEach((v, i) => {
      if (v.type === 'Slicer') return;
      const blob = [pg.name, v.type, v.title, v.purpose, ...v.measures, ...v.cols].join(' ').toLowerCase();
      if (termLow && !blob.includes(termLow)) return;
      const tr = document.createElement('tr');
      const h = t => hl(t||'', term);
      tr.innerHTML = `
        <td style="font-weight:600;white-space:nowrap"><span style="display:inline-block;padding:2px 7px;border-radius:4px;background:#1a2f4a;color:#fff;font-size:10px">${h(pg.name)}</span></td>
        <td style="color:#9CA3AF;text-align:center">${i+1}</td>
        <td><span class="vtype ${getVtClass(v.type)}">${h(v.type)}</span></td>
        <td>
          <div style="font-weight:600;font-size:11px;color:#1a2f4a">${h(v.title||'\u2014')}</div>
          <div style="font-size:10px;color:#5A6A85;margin-top:2px">${h(v.purpose)}</div>
        </td>
        <td>${v.measures.map(m=>`<span class="chip chip-m">${h(m)}</span>`).join(' ')||'\u2014'}</td>
        <td>${v.cols.map(c=>`<span class="chip chip-c">${h(c)}</span>`).join(' ')||'\u2014'}</td>
        <td>${badge(pg.domain)}</td>`;
      tbody.appendChild(tr);
      row++;
    });
  });
  document.getElementById('ct-vismap').textContent = row;
  document.getElementById('resultBadge').textContent = `${row} visual${row!==1?'s':''}`;
}

function renderKPI(term, domain) {
  const tbody = document.getElementById('kpiBody');
  tbody.innerHTML = '';
  let lastD = null;
  const tl = (term||'').toLowerCase();
  const data = RAW.filter(r => {
    const blob = [r.name,r.domain,r.tables.join(' '),r.formula,r.formulaSummary,r.calcType,r.status].join(' ').toLowerCase();
    return (!tl || blob.includes(tl)) && (!domain || r.domain===domain);
  }).sort((a,b)=> DOMAIN_ORDER.indexOf(a.domain)-DOMAIN_ORDER.indexOf(b.domain) || a.name.localeCompare(b.name));

  data.forEach(r => {
    if (r.domain !== lastD) {
      const dr = document.createElement('tr');
      dr.className = 'domain-row';
      dr.innerHTML = `<td colspan="8">\u25CF ${esc(DOMAIN_LABELS[r.domain]||r.domain)}</td>`;
      tbody.appendChild(dr); lastD = r.domain;
    }
    const tr = document.createElement('tr');
    const h = t => hl(t||'', term);
    tr.innerHTML = `
      <td style="font-weight:600;color:#1a2f4a;min-width:160px">${h(r.name)}</td>
      <td>${badge(r.domain)}</td>
      <td>${tbls(r.tables)}</td>
      <td style="min-width:200px">${cols_html(r.cols)}</td>
      <td><code class="formula" style="width:320px;display:block">${h(r.formula)}</code></td>
      <td style="min-width:260px;color:#374151">${h(r.formulaSummary)} <span style="color:#B0B8C4;font-size:9px">(auto)</span></td>
      <td style="color:#5A6A85">${h(r.calcType)}</td>
      <td>${status(r.status)}</td>`;
    tbody.appendChild(tr);
  });
  document.getElementById('kpiEmpty').style.display = data.length===0?'block':'none';
  document.getElementById('ct-kpi').textContent = data.length;
  document.getElementById('resultBadge').textContent = `${data.length} KPI${data.length!==1?'s':''}`;
}

function renderHTML(term, domain) {
  const tbody = document.getElementById('htmlBody');
  tbody.innerHTML = '';
  let lastD = null;
  const tl = (term||'').toLowerCase();
  const data = HTML_M.filter(r => {
    const blob = [r.name,r.domain,r.renders,(r.tables||[]).join(' '),r.status].join(' ').toLowerCase();
    return (!tl||blob.includes(tl)) && (!domain||r.domain===domain);
  }).sort((a,b)=>DOMAIN_ORDER.indexOf(a.domain)-DOMAIN_ORDER.indexOf(b.domain) || a.name.localeCompare(b.name));

  data.forEach(r => {
    if (r.domain !== lastD) {
      const dr = document.createElement('tr');
      dr.className = 'domain-row';
      dr.innerHTML = `<td colspan="7">\u25CF ${esc(DOMAIN_LABELS[r.domain]||r.domain)}</td>`;
      tbody.appendChild(dr); lastD = r.domain;
    }
    const tr = document.createElement('tr');
    const h = t => hl(t||'', term);
    tr.innerHTML = `
      <td style="font-weight:600;color:#1a2f4a;min-width:200px">${h(r.name)}</td>
      <td>${badge(r.domain)}</td>
      <td style="min-width:220px;color:#5A6A85">${h(r.renders)}</td>
      <td>${tbls(r.tables||[])}</td>
      <td style="min-width:280px;font-size:11px;line-height:1.7;padding:10px 12px">${r.varBreakdown||'\u2014'}</td>
      <td>${status(r.status)}</td>`;
    tbody.appendChild(tr);
  });
  document.getElementById('ct-html').textContent = data.length;
  document.getElementById('resultBadge').textContent = `${data.length} measure${data.length!==1?'s':''}`;
}

function renderRels(term) {
  const tbody = document.getElementById('relsBody');
  tbody.innerHTML = '';
  const tl = (term||'').toLowerCase();
  let n = 0;
  RELS.forEach(r => {
    const blob = [r.fromTable,r.fromColumn,r.toTable,r.toColumn,r.measures.join(' ')].join(' ').toLowerCase();
    if (tl && !blob.includes(tl)) return;
    n++;
    const tr = document.createElement('tr');
    const h = t => hl(t||'', term);
    tr.innerHTML = `
      <td><code style="font-size:10px">${h(r.fromTable)}.${h(r.fromColumn)}</code></td>
      <td style="text-align:center;color:#9CA3AF">\u2192</td>
      <td><code style="font-size:10px">${h(r.toTable)}.${h(r.toColumn)}</code></td>
      <td style="text-align:center">${h(r.fromCardinality)}:${h(r.toCardinality)}</td>
      <td style="text-align:center">${r.isActive?'<span class="s-live">\u25CF active</span>':'<span class="s-tbc">\u25CF inactive</span>'}</td>
      <td>${h(r.crossFilteringBehavior)}</td>
      <td style="min-width:220px">${(r.measures||[]).map(m=>`<span class="chip chip-m">${h(m)}</span>`).join(' ')||'\u2014'}</td>`;
    tbody.appendChild(tr);
  });
  document.getElementById('ct-rels').textContent = n;
  document.getElementById('resultBadge').textContent = `${n} relationship${n!==1?'s':''}`;
}

function renderSchema(term) {
  const tbody = document.getElementById('schemaBody');
  tbody.innerHTML = '';
  const data = SCHEMA.filter(r => {
    const blob = [r.table,r.type,r.source,r.joinCols,r.measureCols,r.domains.join(' '),r.notes].join(' ').toLowerCase();
    return !(term||'').toLowerCase() || blob.includes((term||'').toLowerCase());
  });
  data.forEach(r => {
    const tr = document.createElement('tr');
    const h = t => hl(t||'', term);
    const domBadges = r.domains.map(d=>badge(d)).join(' ');
    tr.innerHTML = `
      <td style="font-weight:700;min-width:200px"><span class="chip chip-f" style="font-size:11px">${h(r.table)}</span></td>
      <td><span style="background:#EEF2FF;color:#334155;font-size:10px;font-weight:700;border-radius:4px;padding:2px 6px">${h(r.type)}</span></td>
      <td><code style="font-size:10px;color:#065F46;background:#ECFDF5;padding:2px 5px;border-radius:3px">${h(r.source)}</code></td>
      <td style="min-width:220px"><code style="font-size:10px;font-family:Consolas;color:#3730A3;white-space:pre-wrap">${h(r.joinCols)}</code></td>
      <td style="min-width:260px"><code style="font-size:10px;font-family:Consolas;color:#6B21A8;white-space:pre-wrap;word-break:break-word">${h(r.measureCols)}</code></td>
      <td>${domBadges}</td>
      <td style="min-width:260px;color:#5A6A85;font-style:italic;font-size:11px">${h(r.notes)}</td>`;
    tbody.appendChild(tr);
  });
  document.getElementById('ct-schema').textContent = data.length;
  document.getElementById('resultBadge').textContent = `${data.length} table${data.length!==1?'s':''}`;
}

let activeTab = 'pages';
function applyFilter() {
  const term = document.getElementById('searchInput').value.trim();
  const domain = document.getElementById('domainSel').value;
  if (activeTab === 'pages')   renderPages(term, domain);
  else if (activeTab === 'vismap') renderVisMap(term, domain);
  else if (activeTab === 'kpi')    renderKPI(term, domain);
  else if (activeTab === 'html')   renderHTML(term, domain);
  else if (activeTab === 'rels')   renderRels(term);
  else if (activeTab === 'schema') renderSchema(term);
}
function switchTab(tab, btn) {
  activeTab = tab;
  document.querySelectorAll('.tab').forEach(b=>b.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('panel-'+tab).classList.add('active');
  applyFilter();
}
document.getElementById('searchInput').addEventListener('input', applyFilter);
document.getElementById('domainSel').addEventListener('change', applyFilter);
document.getElementById('clearBtn').addEventListener('click', () => {
  document.getElementById('searchInput').value = '';
  document.getElementById('domainSel').value = '';
  applyFilter();
});
renderPages('', ''); renderVisMap('', ''); renderKPI('', ''); renderHTML('', ''); renderRels(''); renderSchema('');
"""


# ============================================================================
# Data builders -- turn analyzed project data into the JS arrays above
# ============================================================================

def _page_primary_domain(page, measure_domain_by_name):
    counts = {}
    for v in page_content_visuals(page):
        for r in v["refs"]:
            if r["kind"] == "measure":
                d = measure_domain_by_name.get(r["property"])
                if d:
                    counts[d] = counts.get(d, 0) + 1
    if not counts:
        return "(ungrouped)"
    return max(counts, key=counts.get)


def _visual_purpose(v):
    n_measures = sum(1 for r in v["refs"] if r["kind"] == "measure")
    n_cols = sum(1 for r in v["refs"] if r["kind"] == "column")
    names = [r["property"] for r in v["refs"] if r["kind"] == "measure"]
    cols = [f"{r['entity']}.{r['property']}" for r in v["refs"] if r["kind"] == "column"]
    if v["category"] == "Slicer":
        return f"Filters the page by {', '.join(cols) or 'a field'}."
    if n_measures == 1 and n_cols == 0:
        return f"Displays the {names[0]} measure."
    if n_measures > 1:
        return f"Displays: {', '.join(names[:4])}" + (" \u2026" if n_measures > 4 else "") + "."
    if n_cols:
        return f"Displays: {', '.join(cols[:4])}" + (" \u2026" if n_cols > 4 else "") + "."
    return "No field bindings detected."


def build_pages_data(pages, measure_domain_by_name):
    out = []
    for p in pages:
        content_vis = page_content_visuals(p)
        slicers = []
        for v in p["visuals"]:
            if v["category"] == "Slicer":
                for r in v["refs"]:
                    slicers.append(f"{r['entity']}.{r['property']}")
        visuals = []
        for v in content_vis:
            measures = sorted({r["property"] for r in v["refs"] if r["kind"] == "measure"})
            cols = sorted({f"{r['entity']}.{r['property']}" for r in v["refs"] if r["kind"] == "column"})
            visuals.append({
                "type": v["category"], "title": v["title"] or "",
                "measures": measures, "cols": cols, "purpose": _visual_purpose(v),
            })
        domain = _page_primary_domain(p, measure_domain_by_name)
        desc_bits = []
        if visuals:
            n_html = sum(1 for v in visuals if v["type"] == "HTML Content (custom visual)")
            n_tbl = sum(1 for v in visuals if v["type"] == "Table")
            n_card = sum(1 for v in visuals if v["type"] == "KPI Card")
            n_chart = sum(1 for v in visuals if v["type"] == "Chart")
            parts = []
            if n_html: parts.append(f"{n_html} HTML content card(s)")
            if n_card: parts.append(f"{n_card} KPI card(s)")
            if n_tbl: parts.append(f"{n_tbl} table(s)")
            if n_chart: parts.append(f"{n_chart} chart(s)")
            desc_bits.append("Contains " + ", ".join(parts) + "." if parts else "No content visuals detected.")
        out.append({
            "name": p["displayName"], "domain": domain,
            "desc": " ".join(desc_bits) or "No content visuals detected.",
            "slicers": slicers, "visuals": visuals,
            "hidden": p["visibility"] != "visible",
            "nonprod": p["nonprodFlag"],
        })
    return out


def _clean_ref_tuple(t):
    tbl = t[0] or t[1]
    return tbl, t[2]


def build_kpi_data(all_measures, real_table_names_set):
    out = []
    for m in all_measures:
        tables = sorted(set(m["_tablesReferenced"]))
        cols = sorted({
            f"{_clean_ref_tuple(c)[0]}.{_clean_ref_tuple(c)[1]}"
            for c in m["_columnsReferenced"] if _clean_ref_tuple(c)[0] in real_table_names_set
        })
        expr_display = re.sub(r"\n\t+", "\n", m["expression"]).strip()
        out.append({
            "name": m["name"], "domain": m["displayFolder"],
            "tables": tables, "cols": cols,
            "formula": expr_display,
            "formulaSummary": summarize_formula(m["expression"]),
            "calcType": detect_calc_type(m["expression"]),
            "status": detect_status(m["expression"]),
        })
    return out


_MEASURE_BRACKET_RE = re.compile(r"\[([^\]\[]+)\]")



def _js(obj, **kw):
    """JSON for embedding inside a <script> block: a literal '</script>' (or '<!--')
    in the data -- e.g. DAX that builds HTML -- would otherwise end the script early."""
    return json.dumps(obj, **kw).replace("</", "<\\/").replace("<!--", "<\\!--")


def build_html_measures_data(all_measures, measure_names_set):
    out = []
    for m in all_measures:
        calc_type = detect_calc_type(m["expression"])
        if calc_type != "HTML/Display string":
            continue
        refs = sorted({
            b for b in _MEASURE_BRACKET_RE.findall(m["expression"])
            if b in measure_names_set and b != m["name"]
        })
        var_names = re.findall(r"\bVAR\s+(\w+)\s*=", m["expression"])
        var_breakdown = ", ".join(f"<b>{v}</b>" for v in var_names[:12]) or "(no named variables)"
        out.append({
            "name": m["name"], "domain": m["displayFolder"],
            "renders": ", ".join(refs) or "(computed inline, no sub-measure references)",
            "tables": sorted(set(m["_tablesReferenced"])),
            "varBreakdown": f"Variables (in order): {var_breakdown}",
            "status": detect_status(m["expression"]),
        })
    return out


def build_rels_data(relationships, all_measures):
    out = []
    for r in relationships:
        if re.match(r"^(LocalDateTable_|DateTableTemplate_)", r["toTable"]) or \
           re.match(r"^(LocalDateTable_|DateTableTemplate_)", r["fromTable"]):
            continue
        refs = []
        for m in all_measures:
            tset = set(m["_tablesReferenced"])
            if r["fromTable"] in tset and r["toTable"] in tset:
                refs.append(m["name"])
        out.append({
            "fromTable": r["fromTable"], "fromColumn": r["fromColumn"],
            "toTable": r["toTable"], "toColumn": r["toColumn"],
            "fromCardinality": r["fromCardinality"], "toCardinality": r["toCardinality"],
            "isActive": r["isActive"], "crossFilteringBehavior": r["crossFilteringBehavior"],
            "measures": sorted(set(refs))[:8],
        })
    return out


def build_schema_data(real_tables, relationships, all_measures):
    out = []
    date_table_re = re.compile(r"^(LocalDateTable_|DateTableTemplate_)")
    for t in real_tables:
        join_cols = []
        for r in relationships:
            if r["fromTable"] != t["name"]:
                continue
            target = "(auto date table)" if date_table_re.match(r["toTable"]) else f"{r['toTable']}.{r['toColumn']}"
            suffix = "" if r["isActive"] else "  [inactive]"
            join_cols.append(f"{r['fromColumn']} \u2192 {target}{suffix}")
        domains = sorted({m["displayFolder"] for m in all_measures if t["name"] in m["_tablesReferenced"]})
        visible_cols = [c["name"] for c in t["columns"] if not c["isHidden"]]
        src = t["source"]
        src_str = ".".join(x for x in [src.get("database"), src.get("schema"), src.get("object")] if x) \
            or (src.get("connector") or "n/a")
        notes = []
        if not join_cols and not any(r["toTable"] == t["name"] for r in relationships):
            notes.append("No relationships reference this table.")
        if not any(m["description"] for m in t["measures"]) and t["measures"]:
            pass
        if not t["columns"]:
            notes.append("No columns parsed (may be a calculated/hidden table).")
        out.append({
            "table": t["name"], "type": classify_dim_fact(t["name"], relationships),
            "source": src_str,
            "joinCols": "\n".join(join_cols) or "(none found)",
            "measureCols": ", ".join(visible_cols[:20]) + (" \u2026" if len(visible_cols) > 20 else ""),
            "domains": domains or ["(none)"],
            "notes": " ".join(notes),
        })
    return out


DOMAIN_LABELS_FALLBACK = "(ungrouped)"


def build_html(project_name, analysis):
    pages = analysis["pages"]
    all_measures = analysis["allMeasures"]
    real_tables = analysis["realTables"]
    relationships = analysis["relationships"]
    domain_style = analysis["domainStyle"]
    domains_sorted = analysis["domainsSorted"]

    measure_domain_by_name = {m["name"]: m["displayFolder"] for m in all_measures}
    real_table_names_set = {t["name"] for t in real_tables}
    measure_names_set = set(measure_domain_by_name)

    pages_data = build_pages_data(pages, measure_domain_by_name)
    kpi_data = build_kpi_data(all_measures, real_table_names_set)
    html_m_data = build_html_measures_data(all_measures, measure_names_set)
    rels_data = build_rels_data(relationships, all_measures)
    schema_data = build_schema_data(real_tables, relationships, all_measures)

    domain_labels = {d: d for d in domains_sorted}
    domain_options = "".join(
        f'<option value="{d}">{d}</option>' for d in domains_sorted
    )

    n_real_pages = sum(1 for p in pages if not p["nonprodFlag"])
    cf = analysis["commonFilters"]
    common_filter_names = [f for f, n, total in cf if n == total] if cf else []

    subtitle_bits = [f"{len(pages)} pages ({n_real_pages} flagged production)", f"{len(real_tables)} tables", f"{len(all_measures)} measures"]
    subtitle = " | ".join(subtitle_bits)

    data_block = f"""
const DOMAIN_LABELS = {_js(domain_labels)};
const DOMAIN_ORDER = {_js(domains_sorted)};
const DOMAIN_STYLE = {_js(domain_style)};
const PAGES = {_js(pages_data, indent=0)};
const RAW = {_js(kpi_data, indent=0)};
const HTML_M = {_js(html_m_data, indent=0)};
const RELS = {_js(rels_data, indent=0)};
const SCHEMA = {_js(schema_data, indent=0)};
"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{project_name} KPI Documentation</title>
<style>{CSS}</style>
</head>
<body>
<div id="shell">
<div id="topbar">
  <div>
    <h1>\u2b21 {project_name.upper()} KPI DOCUMENTATION</h1>
    <div class="sub">{subtitle} &nbsp;|&nbsp; Auto-generated from PBIP source \u2014 Tier 1 (static analysis only, no fabricated business narrative)</div>
  </div>
  <div style="text-align:right;font-size:10px;color:rgba(255,255,255,.45)">Generated {json.dumps(__import__('datetime').datetime.now().strftime('%d %b %Y'))[1:-1]}</div>
</div>
<div id="toolbar">
  <input type="text" id="searchInput" placeholder="\U0001F50D  Search pages, visuals, measures, columns\u2026" />
  <label>Domain</label>
  <select id="domainSel"><option value="">All Domains</option>{domain_options}</select>
  <button id="clearBtn">\u2715 Clear</button>
  <div id="resultBadge">\u2014</div>
</div>
<div id="tabs">
  <button class="tab active" onclick="switchTab('pages',this)">\U0001F4CB Report Pages <span class="tab-ct" id="ct-pages">{len(pages_data)}</span></button>
  <button class="tab" onclick="switchTab('vismap',this)">\U0001F5FA Visual Map <span class="tab-ct" id="ct-vismap">\u2014</span></button>
  <button class="tab" onclick="switchTab('kpi',this)">\U0001F4CA KPI Reference <span class="tab-ct" id="ct-kpi">{len(kpi_data)}</span></button>
  <button class="tab" onclick="switchTab('html',this)">\U0001F5BC HTML/Display Measures <span class="tab-ct" id="ct-html">{len(html_m_data)}</span></button>
  <button class="tab" onclick="switchTab('rels',this)">\U0001F517 Relationships <span class="tab-ct" id="ct-rels">{len(rels_data)}</span></button>
  <button class="tab" onclick="switchTab('schema',this)">\U0001F5C2 Data Model <span class="tab-ct" id="ct-schema">{len(schema_data)}</span></button>
</div>
<div id="body-area">

<div class="panel active" id="panel-pages">
<div class="panel-scroll">
<div class="stat-bar" id="statBar"></div>
<div class="page-grid" id="pageGrid"></div>
<div class="empty-state" id="pagesEmpty" style="display:none"><h3>No matching pages or visuals</h3><p>Try a different keyword</p></div>
</div>
</div>

<div class="panel" id="panel-vismap">
<div class="panel-hscroll"><div class="panel-vscroll">
<div class="tbl-wrap"><table class="main-tbl" id="vismapTbl">
  <thead><tr>
    <th>Page</th><th>Visual #</th><th>Visual Type</th><th>Title</th>
    <th style="min-width:220px">Measures Used</th>
    <th style="min-width:180px">Columns Used</th>
    <th>Domain</th>
  </tr></thead>
  <tbody id="vismapBody"></tbody>
</table></div>
</div></div>
</div>

<div class="panel" id="panel-kpi">
<div class="panel-hscroll"><div class="panel-vscroll">
<div class="tbl-wrap"><table class="main-tbl" id="kpiTbl">
  <thead><tr>
    <th>Measure Name</th><th>Domain</th><th>Table(s)</th><th>Key Columns</th>
    <th style="min-width:320px">DAX Formula</th>
    <th style="min-width:280px">Formula Summary (auto-generated)</th>
    <th>Calc Type</th><th>Status</th>
  </tr></thead>
  <tbody id="kpiBody"></tbody>
</table>
<div class="empty-state" id="kpiEmpty" style="display:none"><h3>No matching KPIs</h3></div>
</div></div></div>
</div>

<div class="panel" id="panel-html">
<div class="panel-hscroll"><div class="panel-vscroll">
<div class="tbl-wrap"><table class="main-tbl" id="htmlTbl">
  <thead><tr>
    <th>Measure Name</th><th>Domain</th><th>Sub-Measures Rendered</th>
    <th>Table(s)</th><th style="min-width:340px">Variables (auto-extracted, unordered meaning not inferred)</th><th>Status</th>
  </tr></thead>
  <tbody id="htmlBody"></tbody>
</table></div></div></div>
</div>

<div class="panel" id="panel-rels">
<div class="panel-hscroll"><div class="panel-vscroll">
<div class="tbl-wrap"><table class="main-tbl" id="relsTbl">
  <thead><tr>
    <th>From</th><th></th><th>To</th><th>Cardinality</th><th>Active</th><th>Cross-filter</th>
    <th style="min-width:220px">Measures referencing both tables (heuristic)</th>
  </tr></thead>
  <tbody id="relsBody"></tbody>
</table></div></div></div>
</div>

<div class="panel" id="panel-schema">
<div class="panel-hscroll"><div class="panel-vscroll">
<div class="tbl-wrap"><table class="main-tbl" id="schemaTbl">
  <thead><tr>
    <th>Table / View</th><th>Type</th><th>Source</th>
    <th>Outgoing Joins</th>
    <th style="min-width:260px">Columns (visible)</th><th>Domains</th><th>Notes / QA flags</th>
  </tr></thead>
  <tbody id="schemaBody"></tbody>
</table></div></div></div>
</div>

</div>
</div>
<script>
{data_block}
{RENDER_JS}
</script>
</body>
</html>"""
    return html

/* Tooltip & Filter Toggle handlers */
var tipEl=document.getElementById('tip');
document.querySelectorAll('th[data-tip]').forEach(function(th){
  function showTip(e){
    tipEl.textContent=th.dataset.tip;
    tipEl.style.display='block';
    var r=th.getBoundingClientRect();
    var tipW=Math.min(280, window.innerWidth - 16);
    tipEl.style.width=tipW+'px';
    var left=Math.max(8, Math.min(r.left + r.width/2 - tipW/2, window.innerWidth - tipW - 8));
    tipEl.style.left=left+'px';
    var top=r.top - tipEl.offsetHeight - 8;
    if (top < 8) top = r.bottom + 8;
    tipEl.style.top=top+'px';
  }
  th.addEventListener('mouseenter', showTip);
  th.addEventListener('mouseleave', function(){tipEl.style.display='none'});
  th.addEventListener('click', showTip);
});

document.addEventListener('touchstart', function(e){
  if (tipEl && !e.target.closest('th[data-tip]')) {
    tipEl.style.display='none';
  }
}, {passive: true});

var filtersSidebar=document.getElementById('filters-sidebar');
var filtersToggle=document.getElementById('filters-toggle');
var filtersHeader=document.querySelector('.filters-header');
if (filtersSidebar && (filtersHeader || filtersToggle)) {
  var targetEl = filtersHeader || filtersToggle;
  function toggleFilters() {
    var isOpen = filtersSidebar.classList.toggle('open');
    if (filtersToggle) filtersToggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
  }
  targetEl.addEventListener('click', function(e){
    if (e.target.closest('#reset')) return;
    toggleFilters();
  });
}

const tbody=document.querySelector('#t tbody');
const q=document.getElementById('q'),
      fromI=document.getElementById('from');
const filterCountBadge=document.getElementById('filter-count-badge');
const filterRows=document.querySelectorAll('.filter-row[data-stat]');

/* Multi-select Creator Dropdown */
var creatorBtn = document.getElementById('creator-btn'),
    creatorMenu = document.getElementById('creator-menu'),
    creatorBtnLabel = document.getElementById('creator-btn-label'),
    creatorAllCb = document.getElementById('creator-all'),
    creatorCbs = document.querySelectorAll('.creator-cb');

if (creatorBtn && creatorMenu) {
  creatorBtn.addEventListener('click', function (e) {
    e.stopPropagation();
    var isOpen = !creatorMenu.hidden;
    creatorMenu.hidden = isOpen;
    creatorBtn.parentElement.classList.toggle('open', !isOpen);
  });

  document.addEventListener('click', function (e) {
    if (!creatorMenu.contains(e.target) && !creatorBtn.contains(e.target)) {
      creatorMenu.hidden = true;
      creatorBtn.parentElement.classList.remove('open');
    }
  });

  if (creatorAllCb) {
    creatorAllCb.addEventListener('change', function () {
      if (creatorAllCb.checked) {
        creatorCbs.forEach(function (cb) { cb.checked = false; });
      } else {
        var anyChecked = Array.from(creatorCbs).some(function (cb) { return cb.checked; });
        if (!anyChecked) creatorAllCb.checked = true;
      }
      updateCreatorBtnLabel();
      applyFilter();
    });
  }

  creatorCbs.forEach(function (cb) {
    cb.addEventListener('change', function () {
      var checkedCount = Array.from(creatorCbs).filter(function (c) { return c.checked; }).length;
      if (checkedCount > 0) {
        if (creatorAllCb) creatorAllCb.checked = false;
      } else {
        if (creatorAllCb) creatorAllCb.checked = true;
      }
      updateCreatorBtnLabel();
      applyFilter();
    });
  });
}

function getSelectedCreators() {
  if (creatorAllCb && creatorAllCb.checked) return new Set();
  var selected = new Set();
  creatorCbs.forEach(function (cb) {
    if (cb.checked) selected.add(cb.value);
  });
  return selected;
}

function updateCreatorBtnLabel() {
  var selected = getSelectedCreators();
  if (selected.size === 0) {
    creatorBtnLabel.textContent = 'All Creators';
  } else if (selected.size === 1) {
    creatorBtnLabel.textContent = Array.from(selected)[0];
  } else if (selected.size <= 2) {
    creatorBtnLabel.textContent = Array.from(selected).join(', ');
  } else {
    creatorBtnLabel.textContent = selected.size + ' Creators';
  }
}

let sortI=null, sortAsc=true;

/* Compare mode */
var cmpBar=document.getElementById('compare-bar'),
    cmpCount=document.getElementById('cmp-count'),
    cmpGo=document.getElementById('cmp-go'),
    cmpCopyMd=document.getElementById('cmp-copy-md'),
    cmpSaveCsv=document.getElementById('cmp-save-csv'),
    cmpClear=document.getElementById('cmp-clear'),
    checkAll=document.getElementById('check-all');
var cmpActive=false;

function updateCmpCount(){
  var n=tbody.querySelectorAll('input.compare-cb:checked').length;
  cmpCount.textContent=n;
  cmpBar.classList.toggle('visible',n>0);
}

function getRanges(){
  const r={};
  document.querySelectorAll('.num-filter').forEach(inp=>{
    if(inp.value==='') return;
    const s=inp.dataset.stat, b=inp.dataset.bound;
    (r[s]=r[s]||{})[b]=parseFloat(inp.value);
  });
  return r;
}

function updateActiveFilterUI(){
  var ranges=getRanges();
  var activeStats=Object.keys(ranges);
  filterRows.forEach(function(fr){
    fr.classList.toggle('has-filter', activeStats.indexOf(fr.dataset.stat)!==-1);
  });
  filterCountBadge.textContent=activeStats.length;
  filterCountBadge.classList.toggle('visible',activeStats.length>0);
}

function applyFilter(){
  const Q=q.value.toLowerCase(), from=fromI ? fromI.value : '';
  const selectedCreators=getSelectedCreators();
  const ranges=getRanges();
  let n=0;

  tbody.querySelectorAll('tr').forEach(r=>{
    if(cmpActive){
      var cb=r.querySelector('input.compare-cb');
      r.style.display=(cb&&cb.checked)?'':'none';
      if(r.style.display!=='none') n++;
      return;
    }

    const txt=r.innerText.toLowerCase();
    const d=r.dataset.release||'';
    let show=txt.includes(Q) && (!from||(d&&d>=from));

    /* Multi-select Creator filter */
    if(show && selectedCreators.size>0){
      var creatorCell=r.querySelector('td[data-creator]');
      if(!creatorCell || !selectedCreators.has(creatorCell.dataset.creator)) show=false;
    }

    if(show){
      for(const[stat,bounds]of Object.entries(ranges)){
        const cell=r.querySelector(`td[data-stat="${stat}"]`);
        if(!cell){show=false;break;}
        const raw=cell.dataset.val;
        if(raw==='' || raw==='—' || raw===undefined){show=false;break;}
        const v=parseFloat(raw);
        if(isNaN(v)){show=false;break;}
        if(bounds.min!==undefined && v<bounds.min){show=false;break;}
        if(bounds.max!==undefined && v>bounds.max){show=false;break;}
      }
    }
    r.style.display=show?'':'none';
    if(show) n++;
  });

  var tableCountN=document.getElementById('table-count-n');
  if(tableCountN) tableCountN.textContent=n;
  updateActiveFilterUI();
  updateHash();
}

[q,fromI].forEach(el=>{
  if(!el) return;
  el.addEventListener('input',applyFilter);
});
document.querySelectorAll('.num-filter').forEach(el=>el.addEventListener('input',applyFilter));

document.getElementById('reset').addEventListener('click',()=>{
  document.querySelectorAll('.num-filter').forEach(i=>i.value='');
  if(q) q.value='';
  if(fromI) fromI.value='';
  if(creatorAllCb) creatorAllCb.checked=true;
  if(creatorCbs) creatorCbs.forEach(function(c){c.checked=false});
  updateCreatorBtnLabel();
  document.querySelectorAll('.preset-btn').forEach(function(b){b.classList.remove('active')});
  applyFilter();
});

/* Presets */
var presetConfigs=[
  {id:'best-overall',filters:{'blend_3to1_$/M':{min:0.1},intelligence:{min:58.89}},sortStat:'intelligence',sortLabel:'Intelligence',sortAsc:false},
  {id:'best-value',filters:{'blend_3to1_$/M':{min:0.1,max:1},intelligence:{min:41.2}},sortStat:'intelligence',sortLabel:'Intelligence',sortAsc:false},
  {id:'coding',filters:{'blend_3to1_$/M':{min:0.1},coding:{min:77}},sortStat:'coding',sortLabel:'Coding',sortAsc:false},
  {id:'coding-value',filters:{'blend_3to1_$/M':{min:0.1,max:1},coding:{min:58.8},'non_halluc_%':{min:0}},sortStat:'coding',sortLabel:'Coding',sortAsc:false},
  {id:'reasoning',filters:{'blend_3to1_$/M':{min:0.1},intelligence:{max:59},'gpqa_%':{min:93.5}},sortStat:'gpqa_%',sortLabel:'GPQA %',sortAsc:false},
  {id:'life-advice',filters:{'blend_3to1_$/M':{min:0.1},intelligence:{min:40},'non_halluc_%':{min:70}},sortStat:'non_halluc_%',sortLabel:'Non-halluc %',sortAsc:false},
  {id:'cheapest',filters:{'blend_3to1_$/M':{min:0.15,max:0.25},intelligence:{min:30}},sortStat:'blend_3to1_$/M',sortLabel:'Blended',sortAsc:true},
  {id:'agentic',filters:{'blend_3to1_$/M':{min:0.1},agentic:{min:47.38}},sortStat:'agentic',sortLabel:'Agentic',sortAsc:false}
];

function sortForPreset(cfg){
  var rows=Array.from(tbody.rows);
  rows.sort(function(a,b){
    var ac=a.querySelector('td[data-stat="'+cfg.sortStat+'"]');
    var bc=b.querySelector('td[data-stat="'+cfg.sortStat+'"]');
    var av=ac ? parseFloat(ac.dataset.val) : NaN;
    var bv=bc ? parseFloat(bc.dataset.val) : NaN;
    var result=(isNaN(av)?-Infinity:av)-(isNaN(bv)?-Infinity:bv);
    return cfg.sortAsc ? result : -result;
  });
  rows.forEach(function(r){tbody.appendChild(r)});
  document.querySelectorAll('th').forEach(function(h){h.classList.remove('sorted');var a=h.querySelector('.sort-arrow');if(a)a.remove()});
  var metricCell=tbody.querySelector('td[data-stat="'+cfg.sortStat+'"]');
  var metricIndex=metricCell ? metricCell.cellIndex : -1;
  var th=metricIndex>=0 ? document.querySelector('#t thead th:nth-child('+(metricIndex+1)+')') : null;
  if(th){th.classList.add('sorted');var a=document.createElement('span');a.className='sort-arrow';a.textContent=cfg.sortAsc?' ↑':' ↓';th.appendChild(a)}
  var state=document.getElementById('table-sort-state');
  if(state){
    state.textContent='';
    state.appendChild(document.createTextNode('Sorted: '));
    var label=document.createElement('b');
    label.textContent=cfg.sortLabel;
    state.appendChild(label);
    state.appendChild(document.createTextNode(' '+(cfg.sortAsc?'↑':'↓')));
  }
}

document.querySelectorAll('.preset-btn').forEach(function(btn){
  btn.addEventListener('click',function(){
    var pid=btn.dataset.preset;

    // Clear all inputs first
    document.querySelectorAll('.num-filter').forEach(function(i){i.value=''});
    q.value='';

    if(btn.classList.contains('active')){
      btn.classList.remove('active');
      btn.setAttribute('aria-pressed','false');
      applyFilter();
      return;
    }

    document.querySelectorAll('.preset-btn').forEach(function(b){b.classList.remove('active');b.setAttribute('aria-pressed','false')});
    btn.classList.add('active');
    btn.setAttribute('aria-pressed','true');

    var cfg=presetConfigs.find(function(p){return p.id===pid});
    if(cfg){
      Object.keys(cfg.filters).forEach(function(stat){
        var bounds=cfg.filters[stat];
        document.querySelectorAll('.num-filter[data-stat="'+stat+'"]').forEach(function(inp){
          if(bounds.min!==undefined && inp.dataset.bound==='min') inp.value=bounds.min;
          if(bounds.max!==undefined && inp.dataset.bound==='max') inp.value=bounds.max;
        });
      });
      sortForPreset(cfg);
    }
    applyFilter();
  });
});

/* Compare actions */
cmpGo.addEventListener('click',function(){
  cmpActive=true;
  applyFilter();
});

if(cmpCopyMd){
  cmpCopyMd.addEventListener('click',function(){
    var checkedRows=Array.from(tbody.querySelectorAll('tr')).filter(function(r){
      var cb=r.querySelector('input.compare-cb');
      return (cb&&cb.checked)||(cmpActive&&r.style.display!=='none');
    });
    if(checkedRows.length===0){
      checkedRows=Array.from(tbody.querySelectorAll('tr')).filter(function(r){
        return r.style.display!=='none';
      });
    }
    if(checkedRows.length===0) return;

    var headerThs=Array.from(document.querySelectorAll('#t thead th')).slice(1); // Skip checkbox
    var headers=headerThs.map(function(th){
      return th.textContent.replace(/[\u2191\u2193]/g,'').trim();
    });

    var mdLines=[];
    mdLines.push('| ' + headers.join(' | ') + ' |');
    mdLines.push('| ' + headers.map(function(h, idx){
      return (idx > 1 && idx < headers.length - 1) ? '---:' : '---';
    }).join(' | ') + ' |');

    checkedRows.forEach(function(r){
      var cells=Array.from(r.children).slice(1);
      var vals=cells.map(function(c){
        var txt=c.textContent.trim();
        if(txt==='—'||txt==='-'||txt==='–') txt='';
        return txt;
      });
      mdLines.push('| ' + vals.join(' | ') + ' |');
    });

    var mdText=mdLines.join('\n');
    navigator.clipboard.writeText(mdText).then(function(){
      var origText=cmpCopyMd.textContent;
      cmpCopyMd.textContent='✓ Copied!';
      setTimeout(function(){ cmpCopyMd.textContent=origText; }, 2000);
    }).catch(function(err){
      console.error('Failed to copy markdown:', err);
    });
  });
}

if(cmpSaveCsv){
  cmpSaveCsv.addEventListener('click',function(){
    var checkedRows=Array.from(tbody.querySelectorAll('tr')).filter(function(r){
      var cb=r.querySelector('input.compare-cb');
      return (cb&&cb.checked)||(cmpActive&&r.style.display!=='none');
    });
    if(checkedRows.length===0){
      checkedRows=Array.from(tbody.querySelectorAll('tr')).filter(function(r){
        return r.style.display!=='none';
      });
    }
    if(checkedRows.length===0) return;

    var headerThs=Array.from(document.querySelectorAll('#t thead th')).slice(1); // Skip checkbox
    var headers=headerThs.map(function(th){
      return th.textContent.replace(/[\u2191\u2193]/g,'').trim();
    });

    function escapeCsvCell(val){
      if(val===null||val===undefined) return '';
      var str=String(val).trim();
      if(str==='—'||str==='-'||str==='–') return '';
      if(/^[=+\-@\t\r]/.test(str)){
        str="'"+str;
      }
      if(/[",\n\r]/.test(str)){
        str='"'+str.replace(/"/g,'""')+'"';
      }
      return str;
    }

    var csvRows=[];
    csvRows.push(headers.map(escapeCsvCell).join(','));

    checkedRows.forEach(function(r){
      var cells=Array.from(r.children).slice(1);
      var vals=cells.map(function(c){
        return escapeCsvCell(c.textContent);
      });
      csvRows.push(vals.join(','));
    });

    var csvText=csvRows.join('\r\n');
    var blob=new Blob([csvText],{type:'text/csv;charset=utf-8;'});
    var url=URL.createObjectURL(blob);
    var dateStr=new Date().toISOString().split('T')[0];
    var fileName='model-benchmarks-'+dateStr+'.csv';

    var a=document.createElement('a');
    a.href=url;
    a.download=fileName;
    document.body.appendChild(a);
    a.click();
    setTimeout(function(){ document.body.removeChild(a); URL.revokeObjectURL(url); }, 1000);

    var origText=cmpSaveCsv.textContent;
    cmpSaveCsv.textContent='✓ Saved!';
    setTimeout(function(){ cmpSaveCsv.textContent=origText; }, 2000);
  });
}

cmpClear.addEventListener('click',function(){
  cmpActive=false;
  tbody.querySelectorAll('input.compare-cb').forEach(function(c){c.checked=false});
  if(checkAll) checkAll.checked=false;
  updateCmpCount();
  applyFilter();
});

/* Sorting */
document.querySelectorAll('th').forEach(th=>{
  if(th.dataset.i === undefined || th.dataset.i === null) return;
  th.addEventListener('click',()=>{
    document.querySelectorAll('.preset-btn').forEach(function(b){b.classList.remove('active');b.setAttribute('aria-pressed','false')});
    const i=+th.dataset.i, t=th.dataset.t; // data index includes the checkbox column
    if(sortI===i) sortAsc=!sortAsc; else {sortI=i;sortAsc=(t==='s'); if(t==='d') sortAsc=false;}
    const rows=Array.from(tbody.rows);
    rows.sort((a,b)=>{
      let av=a.cells[i].dataset.val||a.cells[i].textContent||'',
          bv=b.cells[i].dataset.val||b.cells[i].textContent||'';
      if(t==='n') {av=parseFloat(av); bv=parseFloat(bv);
        return (isNaN(av)?-Infinity:av)-(isNaN(bv)?-Infinity:bv);}
      if(t==='d'){
        var ad=Date.parse(av), bd=Date.parse(bv);
        if(!isNaN(ad)&&!isNaN(bd)) return ad-bd;
        return av<bv?-1:av>bv?1:0;
      }
      return av.localeCompare(bv);
    });
    if(!sortAsc) rows.reverse();
    rows.forEach(r=>tbody.appendChild(r));

    document.querySelectorAll('th').forEach(function(h){
      h.classList.remove('sorted');
      var arrow=h.querySelector('.sort-arrow');
      if(arrow) arrow.remove();
    });
    th.classList.add('sorted');
    var sortStateEl=document.getElementById('table-sort-state');
    if(sortStateEl){
      sortStateEl.textContent='';
      sortStateEl.appendChild(document.createTextNode('Sorted: '));
      var b=document.createElement('b');
      b.textContent=th.textContent.trim();
      sortStateEl.appendChild(b);
      sortStateEl.appendChild(document.createTextNode(' '+(sortAsc?'↑':'↓')));
    }
    var arrow=document.createElement('span');
    arrow.className='sort-arrow';
    arrow.textContent=sortAsc?' ↑':' ↓';
    th.appendChild(arrow);
    applyFilter();
  });
});

/* Hash state */
function encodeHashState(){
  var parts=[];
  var activePresetBtn=document.querySelector('.preset-btn.active');
  if(activePresetBtn) parts.push('preset='+encodeURIComponent(activePresetBtn.dataset.preset));
  var selected=getSelectedCreators();
  if(selected.size>0) parts.push('creator='+encodeURIComponent(Array.from(selected).join(',')));
  document.querySelectorAll('.num-filter').forEach(function(inp){
    if(inp.value==='') return;
    parts.push(inp.dataset.stat+'.'+inp.dataset.bound+'='+encodeURIComponent(inp.value));
  });
  return parts.join('&');
}

function updateHash(){
  var h=encodeHashState();
  history.replaceState(null,'',h?('#'+h):(location.pathname+location.search));
}

function parseHash(){
  var hash=location.hash.slice(1);
  if(!hash) return {};
  var params=Object.create(null);
  new URLSearchParams(hash).forEach(function(value,key){
    params[key]=value;
  });
  return params;
}

function applyHashState(){
  var params=parseHash();
  if(Object.keys(params).length===0){ resetAllFilterInputs(); applyFilter(); return; }

  if(params.preset){
    var btn=Array.from(document.querySelectorAll('.preset-btn')).find(function(candidate){
      return candidate.dataset.preset===params.preset;
    });
    if(btn) btn.click();
  }
  if(params.creator){
    var list=params.creator.split(',');
    var setList=new Set(list);
    creatorCbs.forEach(function(cb){ cb.checked=setList.has(cb.value); });
    if(creatorAllCb) creatorAllCb.checked = (list.length===0);
    updateCreatorBtnLabel();
  }
  Object.keys(params).forEach(function(k){
    if(k==='scope'||k==='creator'||k==='preset') return;
    var dot=k.lastIndexOf('.');
    if(dot<0) return;
    var stat=k.slice(0,dot), bound=k.slice(dot+1);
    document.querySelectorAll('.num-filter').forEach(function(inp){
      if(inp.dataset.stat===stat && inp.dataset.bound===bound) inp.value=params[k];
    });
  });
  applyFilter();
}


function fmt(v){ return (v===null||v===undefined) ? '' : v; }
function esc(v){
  return (window.ModelCompassNav && ModelCompassNav.escapeHtml)
    ? ModelCompassNav.escapeHtml(v)
    : String(v==null?'':v).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
function safeHref(v, fallback){
  return (window.ModelCompassNav && ModelCompassNav.safeUrl)
    ? ModelCompassNav.safeUrl(v, fallback||'#')
    : (fallback||'#');
}

function shortName(name){
  if(!name) return '';
  function _repl(match){
    if(/max/i.test(match)) return '(Max)';
    if(/xhigh/i.test(match)) return '(Xhigh)';
    if(/high/i.test(match)) return '(High)';
    if(/medium/i.test(match)) return '(Medium)';
    if(/low/i.test(match)) return '(Low)';
    return match;
  }
  var n = String(name).replace(/\((?:Adaptive\s+)?Reasoning,\s*(?:Max|High|Medium|Low|Xhigh)\s*Effort(?:,\s*Opus\s*[\d.]+\s*Fallback)?\)/gi, _repl);
  n = n.replace(/\(Non-reasoning,\s*(High|Low|Medium|Max)\s*Effort\)/gi, '($1)');
  return n.trim();
}

function buildRow(m, rank){
  const b=m.benchmarks||{}, c=m.composite||{}, p=m.pricing_per_m_tokens||{}, perf=m.performance||{};
  const aaUrl=safeHref(m.aa_url, `https://artificialanalysis.ai/models/${encodeURIComponent(m.slug||'')}`);
  const rowClass = m.openrouter_slug ? ' class="free"' : '';
  const displayName = shortName(m.name || '');

  function cell(stat, val, isPrice){
    const raw=(val===null||val===undefined)?'':val;
    if(raw==='') return `<td class="num" data-stat="${esc(stat)}" data-val=""></td>`;
    let disp=raw;
    if(typeof raw==='number' || (!isNaN(parseFloat(raw)) && isFinite(raw))){
      const num=parseFloat(raw);
      if(isPrice){
        disp=(num<1)?num.toFixed(2):(num%1===0?num.toFixed(0):num.toFixed(2));
      } else {
        disp=Math.round(num);
      }
    }
    return `<td class="num" data-stat="${esc(stat)}" data-val="${esc(raw)}">${esc(disp)}</td>`;
  }
  return `<tr${rowClass} data-release="${esc(m.released||'')}" data-slug="${esc(m.slug||'')}">`+
    `<td class="cb-col"><input type="checkbox" class="compare-cb" data-model-row id="cmp-${esc(m.slug||rank)}" name="compare-model-${esc(m.slug||rank)}" aria-label="Select ${esc(displayName)} for comparison"></td>`+
    `<td class="l name-col" title="${esc(displayName)}" data-val="${esc(displayName.toLowerCase())}"><span class="cell-title">${esc(displayName)}</span></td>`+
    `<td class="l creator-col" data-creator="${esc(m.creator||'')}" data-val="${esc((m.creator||'').toLowerCase())}"><span class="creator-name">${esc(m.creator||'')}</span></td>`+
    `<td class="num" data-t="d" data-val="${esc(m.released||'')}">${esc(m.released||'')}</td>`+
    cell('in_$/M', p.input, true)+
    cell('out_$/M', p.output, true)+
    cell('blend_3to1_$/M', p.blended_3_1, true)+
    cell('intelligence', c.intelligence_index_v4_1)+
    cell('coding', c.coding_index)+
    cell('agentic', c.agentic_index)+
    cell('omniscience', c.omniscience_index)+
    cell('gpqa_%', b.gpqa_diamond)+
    cell('hle_%', b.hle)+
    cell('critpt_%', b.critpt)+
    cell('non_halluc_%', b.omniscience_non_halluc)+
    cell('ifbench_%', b.ifbench)+
    cell('lcr_%', b.lcr)+
    cell('tau2_%', b.tau2_bench)+
    cell('tau_banking_%', b.tau3_banking)+
    cell('gdpval_%', b.gdpval_v2)+
    cell('terminalbench_hard_%', b.terminalbench_hard)+
    cell('terminalbench_v2_1_%', b.terminalbench_v2_1)+
    cell('scicode_%', b.scicode)+
    cell('mmmu_pro_%', b.mmmu_pro)+
    cell('speed_tps', perf.output_speed_tps)+
    cell('ttft_s', perf.ttft_seconds_total, true)+
    cell('ttfa_s', perf.ttft_seconds_answer, true)+
    `<td class="l" data-val="${esc(m.slug||'')}"><a class="model-link" href="${esc(aaUrl)}" target="_blank" rel="noopener noreferrer">${esc(m.slug||'')}</a></td>`+
    `</tr>`;
}

function bindCheckboxEvents(){
  tbody.querySelectorAll('input.compare-cb').forEach(function(cb){
    cb.addEventListener('change',function(){
      updateCmpCount();
    });
  });
}

if(checkAll){
  checkAll.addEventListener('change',function(){
    tbody.querySelectorAll('input.compare-cb').forEach(function(c){c.checked=checkAll.checked});
    updateCmpCount();
  });
}

async function loadModels(){
  try{
    const res=await fetch('data/models.json', {credentials:'same-origin'});
    if(!res.ok) throw new Error(`HTTP ${res.status}`);
    const data=await res.json();
    if(!data || !Array.isArray(data.models)) throw new Error('Invalid models payload');
    if(data.models.length>5000) throw new Error('Models payload exceeds safe display limit');
    const models=data.models.slice().sort((a,b)=>
      ((b.composite||{}).intelligence_index_v4_1||0)-((a.composite||{}).intelligence_index_v4_1||0));
    tbody.innerHTML=models.map((m, i)=>buildRow(m, i+1)).join('\n');

    if(data.scraped_at && window.ModelCompassNav){
      ModelCompassNav.checkStaleness(data.scraped_at);
    }
    bindCheckboxEvents();

    sortI = 7;
    sortAsc = false;
    var intelTh = document.querySelector('th[data-i="7"]');
    if(intelTh){
      document.querySelectorAll('th').forEach(function(h){
        h.classList.remove('sorted');
        var arrow=h.querySelector('.sort-arrow');
        if(arrow) arrow.remove();
      });
      intelTh.classList.add('sorted');
      var arrow=document.createElement('span');
      arrow.className='sort-arrow';
      arrow.textContent=' ↓';
      intelTh.appendChild(arrow);
    }
    var sortStateEl=document.getElementById('table-sort-state');
    if(sortStateEl){
      sortStateEl.textContent='';
      sortStateEl.appendChild(document.createTextNode('Sorted: '));
      var b=document.createElement('b');
      b.textContent='Intelligence';
      sortStateEl.appendChild(b);
      sortStateEl.appendChild(document.createTextNode(' ↓'));
    }
  }catch(e){
    console.error('Could not load data/models.json:', e);
  }
}

function resetAllFilterInputs(){
  if(q) q.value='';
  if(fromI) fromI.value='';
  if(creatorAllCb) creatorAllCb.checked=true;
  if(creatorCbs) creatorCbs.forEach(function(c){c.checked=false;});
  updateCreatorBtnLabel();
  document.querySelectorAll('.num-filter').forEach(function(i){i.value='';});
  document.querySelectorAll('.preset-btn').forEach(function(b){b.classList.remove('active');});
}

loadModels().then(()=>{
  if(location.hash) applyHashState(); else { resetAllFilterInputs(); applyFilter(); }
});

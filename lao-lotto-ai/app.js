// ── Sample data (real data extracted from local SQLite DB) ──────────────
const DATA = {
  lao: {
    meta: { total: 120, latest: "2026-05-22", earliest: "2025-09-05" },
    latest: { date: "วันศุกร์ที่ 22 พฤษภาคม 2569", six_digit: "743763", last_4: "3763", top_3: "743", last_2: "63" },
    recent: [
      { draw_date:"22 พ.ค.", six_digit:"743763", last_4:"3763", top_3:"743", last_2:"63" },
      { draw_date:"21 พ.ค.", six_digit:"938769", last_4:"8769", top_3:"938", last_2:"69" },
      { draw_date:"20 พ.ค.", six_digit:"962377", last_4:"2377", top_3:"962", last_2:"77" },
      { draw_date:"19 พ.ค.", six_digit:"050470", last_4:"0470", top_3:"050", last_2:"70" },
      { draw_date:"18 พ.ค.", six_digit:"563369", last_4:"3369", top_3:"563", last_2:"69" },
      { draw_date:"15 พ.ค.", six_digit:"807095", last_4:"7095", top_3:"807", last_2:"95" },
      { draw_date:"14 พ.ค.", six_digit:"979996", last_4:"9996", top_3:"979", last_2:"96" },
      { draw_date:"13 พ.ค.", six_digit:"220572", last_4:"0572", top_3:"220", last_2:"72" },
      { draw_date:"12 พ.ค.", six_digit:"344931", last_4:"4931", top_3:"344", last_2:"31" },
      { draw_date:"11 พ.ค.", six_digit:"457509", last_4:"7509", top_3:"457", last_2:"09" },
    ],
    hot2:  ["77","09","79","69","26","89","52","39"],
    cold2: ["29","86","13","55","02","30","73","75"],
    freq2: [
      {number:"77",count:5,pct:4.17},{number:"09",count:5,pct:4.17},{number:"79",count:5,pct:4.17},
      {number:"69",count:4,pct:3.33},{number:"26",count:4,pct:3.33},{number:"89",count:3,pct:2.5},
      {number:"52",count:3,pct:2.5}, {number:"39",count:3,pct:2.5}, {number:"85",count:3,pct:2.5},
      {number:"98",count:3,pct:2.5}, {number:"68",count:3,pct:2.5}, {number:"01",count:2,pct:1.67},
      {number:"49",count:2,pct:1.67},{number:"43",count:2,pct:1.67},{number:"71",count:2,pct:1.67},
    ],
    preds: {
      "bottom_2": [{number:"15",probability:35.69},{number:"18",probability:8.13},{number:"41",probability:7.2},{number:"25",probability:2.4},{number:"68",probability:2.35}],
      "top_2":    [{number:"07",probability:28.53},{number:"10",probability:13.6},{number:"74",probability:10.0},{number:"62",probability:10.0},{number:"51",probability:7.5}],
      "last_3":   [{number:"500",probability:36.3},{number:"506",probability:5.2},{number:"932",probability:3.2},{number:"133",probability:3.2},{number:"188",probability:2.0}],
      "top_3":    [{number:"097",probability:9.92},{number:"917",probability:7.06},{number:"606",probability:5.1},{number:"367",probability:5.04},{number:"440",probability:4.8}],
      "last_4":   [{number:"4488",probability:19.15},{number:"0643",probability:6.08},{number:"6238",probability:6.0},{number:"2926",probability:5.7},{number:"0389",probability:5.07}],
    },
  },
  hanoi: {
    total: 120,
    latest: { date: "วันอาทิตย์ที่ 24 พฤษภาคม 2569", five_digit: "20104", last_3: "104", last_2: "70" },
    recent: [
      { draw_date:"24 พ.ค.", five_digit:"20104", last_3:"104", last_2:"70" },
      { draw_date:"23 พ.ค.", five_digit:"38021", last_3:"021", last_2:"05" },
      { draw_date:"22 พ.ค.", five_digit:"72939", last_3:"939", last_2:"97" },
      { draw_date:"21 พ.ค.", five_digit:"72685", last_3:"685", last_2:"60" },
      { draw_date:"20 พ.ค.", five_digit:"88568", last_3:"568", last_2:"76" },
      { draw_date:"19 พ.ค.", five_digit:"81754", last_3:"754", last_2:"06" },
      { draw_date:"18 พ.ค.", five_digit:"55361", last_3:"361", last_2:"89" },
      { draw_date:"17 พ.ค.", five_digit:"96684", last_3:"684", last_2:"06" },
      { draw_date:"16 พ.ค.", five_digit:"19404", last_3:"404", last_2:"78" },
      { draw_date:"15 พ.ค.", five_digit:"67294", last_3:"294", last_2:"92" },
    ],
    hot2:  ["16","50","57","91","41","45","96","78"],
    cold2: ["32","04","82","65","95","43","31","81"],
    freq2: [
      {number:"16",count:4,pct:3.33},{number:"50",count:4,pct:3.33},{number:"57",count:3,pct:2.5},
      {number:"91",count:3,pct:2.5}, {number:"41",count:3,pct:2.5}, {number:"45",count:3,pct:2.5},
      {number:"96",count:3,pct:2.5}, {number:"78",count:3,pct:2.5}, {number:"14",count:3,pct:2.5},
      {number:"94",count:3,pct:2.5}, {number:"05",count:2,pct:1.67},{number:"13",count:2,pct:1.67},
      {number:"33",count:2,pct:1.67},{number:"09",count:2,pct:1.67},{number:"70",count:2,pct:1.67},
    ],
  },
  stock: {
    total: 14362,
    latest_close: 1553.32,
    latest_last2: "53",
    latest_date: "25 พ.ค. 2569",
    hot2:  ["91","70","14","33","82","77","08","24"],
    cold2: ["50","48","06","11","51","99","04","55"],
    freq2: [
      {number:"91",count:101,pct:1.41},{number:"70",count:93,pct:1.3},{number:"14",count:89,pct:1.24},
      {number:"33",count:89,pct:1.24},{number:"82",count:88,pct:1.23},{number:"77",count:87,pct:1.21},
      {number:"08",count:85,pct:1.18},{number:"24",count:85,pct:1.18},{number:"74",count:85,pct:1.18},
      {number:"90",count:85,pct:1.18},{number:"84",count:84,pct:1.17},{number:"76",count:84,pct:1.17},
      {number:"64",count:84,pct:1.17},{number:"94",count:84,pct:1.17},{number:"95",count:84,pct:1.17},
    ],
    recent: [
      { draw_date:"25 พ.ค.", set_value:"1,553.32", last_2:"53", top_2:"15" },
      { draw_date:"22 พ.ค.", set_value:"1,538.67", last_2:"39", top_2:"15" },
      { draw_date:"21 พ.ค.", set_value:"1,532.67", last_2:"33", top_2:"15" },
      { draw_date:"20 พ.ค.", set_value:"1,528.43", last_2:"28", top_2:"15" },
      { draw_date:"19 พ.ค.", set_value:"1,516.69", last_2:"17", top_2:"15" },
      { draw_date:"18 พ.ค.", set_value:"1,517.74", last_2:"18", top_2:"15" },
      { draw_date:"15 พ.ค.", set_value:"1,517.95", last_2:"18", top_2:"15" },
      { draw_date:"14 พ.ค.", set_value:"1,539.12", last_2:"39", top_2:"15" },
      { draw_date:"13 พ.ค.", set_value:"1,517.26", last_2:"17", top_2:"15" },
      { draw_date:"12 พ.ค.", set_value:"1,483.56", last_2:"84", top_2:"14" },
    ],
  },
};

const PRED_LABELS = {
  bottom_2:"2 ตัวล่าง", top_2:"2 ตัวบน",
  last_3:"3 ตัวล่าง", top_3:"3 ตัวบน", last_4:"4 ตัวท้าย",
};

// ── Chart.js defaults ────────────────────────────────────────────────────
Chart.defaults.color = "#8B949E";
Chart.defaults.borderColor = "#30363D";
Chart.defaults.font.family = "'Sarabun', sans-serif";

const _charts = {};

function mkChart(id, labels, values, opts = {}) {
  if (_charts[id]) { _charts[id].destroy(); }
  const ctx = document.getElementById(id);
  if (!ctx) return;
  _charts[id] = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: opts.color || 'rgba(230,57,70,0.75)',
        borderColor:     opts.border || '#E63946',
        borderWidth: 1,
        borderRadius: 4,
      }],
    },
    options: {
      indexAxis: opts.horizontal !== false ? 'y' : 'x',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => ` ${ctx.formattedValue}${opts.suffix || ''}`,
          },
        },
      },
      scales: {
        x: { grid: { color: '#30363D' }, ticks: { color: '#8B949E' } },
        y: { grid: { color: 'transparent' }, ticks: { color: '#F0F6FC', font: { weight: '700', size: 11 } } },
      },
    },
  });
}

// ── Render lottery balls ─────────────────────────────────────────────────
function renderBalls(targetId, numbers, scores) {
  const el = document.getElementById(targetId);
  if (!el) return;
  el.innerHTML = numbers.map((n, i) => {
    const pctHtml = scores ? `<div class="ball-pct">${scores[i].toFixed(1)}%</div>` : '';
    const topCls  = i === 0 ? ' top' : '';
    return `<div class="ball-item">
      <div class="lao-ball ball-${i % 7}${topCls}">${n}</div>
      ${pctHtml}
    </div>`;
  }).join('');
}

// ── Render prediction block ──────────────────────────────────────────────
function renderPredBlock(targetId, preds, title = '🎯 ผลการทำนายล่าสุด') {
  const el = document.getElementById(targetId);
  if (!el) return;
  const typesHtml = Object.entries(preds).map(([dtype, items]) => {
    const label = PRED_LABELS[dtype] || dtype;
    const maxP  = Math.max(...items.map(p => p.probability), 1);
    const rows  = items.slice(0, 5).map((p, i) => {
      const barW = Math.min(100, Math.round(p.probability / maxP * 100));
      return `<div class="pred-item">
        <span class="pi-rank">#${i+1}</span>
        <span class="pi-num">${p.number}</span>
        <div class="pi-bar-wrap"><div class="pi-bar" style="width:${barW}%"></div></div>
        <span class="pi-pct">${p.probability.toFixed(1)}%</span>
      </div>`;
    }).join('');
    return `<div class="pred-type"><div class="pt-label">${label}</div>${rows}</div>`;
  }).join('');
  el.innerHTML = `<div class="pred-block">
    <div class="pb-title">${title}</div>
    <div class="pred-row">${typesHtml}</div>
  </div>`;
}

// ── Render table ─────────────────────────────────────────────────────────
function renderTable(targetId, rows, keys, headers) {
  const el = document.getElementById(targetId);
  if (!el) return;
  const thead = `<tr>${headers.map(h => `<th>${h}</th>`).join('')}</tr>`;
  const tbody = rows.map(r =>
    `<tr>${keys.map(k => `<td>${r[k] ?? ''}</td>`).join('')}</tr>`
  ).join('');
  el.innerHTML = `<table class="data-table"><thead>${thead}</thead><tbody>${tbody}</tbody></table>`;
}

// ── Navigation ────────────────────────────────────────────────────────────
function showSection(name) {
  document.querySelectorAll('.sec').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));

  const sec = document.getElementById('sec-' + name);
  if (sec) sec.classList.add('active');
  document.querySelectorAll(`[data-section="${name}"]`).forEach(b => b.classList.add('active'));

  // Init charts lazily on first visit
  if (name === 'analysis' && !_charts['lao-freq-chart']) initAnalysisCharts();
  if (name === 'predict')  renderPredBlock('pred-full', DATA.lao.preds, '🎯 ผลการทำนายล่าสุด (ทุกประเภท)');
  if (name === 'hanoi'   && !_charts['hanoi-freq-chart']) initHanoiCharts();
  if (name === 'stock'   && !_charts['stock-freq-chart']) initStockCharts();

  closeSidebar();
  window.scrollTo(0, 0);
}

// ── Mobile sidebar ────────────────────────────────────────────────────────
function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('open');
  document.getElementById('overlay').classList.toggle('active');
}
function closeSidebar() {
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('overlay').classList.remove('active');
}

// ── Chart init functions ──────────────────────────────────────────────────
function initAnalysisCharts() {
  const d = DATA.lao.freq2;
  mkChart('lao-freq-chart', d.map(x=>x.number), d.map(x=>x.count), {
    color: 'rgba(230,57,70,0.75)', suffix: ' ครั้ง',
  });
}

function initHanoiCharts() {
  const d = DATA.hanoi.freq2;
  mkChart('hanoi-freq-chart', d.map(x=>x.number), d.map(x=>x.count), {
    color: 'rgba(167,139,250,0.75)', border: '#A78BFA', suffix: ' ครั้ง',
  });
}

function initStockCharts() {
  const d = DATA.stock.freq2.slice(0,12);
  mkChart('stock-freq-chart', d.map(x=>x.number), d.map(x=>x.count), {
    color: 'rgba(46,204,113,0.75)', border: '#2ECC71', suffix: ' วัน',
  });
}

// ── Init ──────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // ── Home ──
  renderBalls('home-hot-balls', DATA.lao.hot2.slice(0,6), null);
  renderPredBlock('pred-block-home', DATA.lao.preds);
  renderTable('lao-recent-table',
    DATA.lao.recent,
    ['draw_date','six_digit','last_4','top_3','last_2'],
    ['งวด','6 หลัก','4 ตัวท้าย','3 ตัวบน','2 ตัวล่าง']
  );

  // ── Analysis (lazy init on first visit, pre-render balls here) ──
  renderBalls('analysis-hot-balls',  DATA.lao.hot2,  null);
  renderBalls('analysis-cold-balls', DATA.lao.cold2, null);

  // ── Hanoi ──
  renderBalls('hanoi-hot-balls',  DATA.hanoi.hot2,  null);
  renderBalls('hanoi-cold-balls', DATA.hanoi.cold2, null);
  renderTable('hanoi-recent-table',
    DATA.hanoi.recent,
    ['draw_date','five_digit','last_3','last_2'],
    ['งวด','5 หลัก','3 ตัวล่าง','2 ตัวล่าง']
  );

  // ── Stock ──
  renderBalls('stock-hot-balls',  DATA.stock.hot2,  null);
  renderBalls('stock-cold-balls', DATA.stock.cold2, null);
  renderTable('stock-recent-table',
    DATA.stock.recent,
    ['draw_date','set_value','last_2','top_2'],
    ['วันที่','ดัชนี SET','2 ตัวล่าง','2 ตัวบน']
  );

  // Nav click handlers
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.addEventListener('click', e => {
      e.preventDefault();
      showSection(btn.dataset.section);
    });
  });
});

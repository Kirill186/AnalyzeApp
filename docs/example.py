# modern_webview_demo.py
# Красивый современный JS-графический демо-экран внутри PySide6 QWebEngineView:
# - анимированный фон "particle network" (Canvas + requestAnimationFrame)
# - интерактивный мини-граф (узлы двигаются, соединяются, реагируют на мышь)
#
# Запуск:
#   pip install PySide6 PySide6-QtWebEngine
#   python modern_webview_demo.py

import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtWebEngineWidgets import QWebEngineView


HTML = r"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Modern JS Demo in Qt WebEngine</title>
  <style>
    :root{
      --bg1:#0b1020;
      --bg2:#070a14;
      --card: rgba(255,255,255,.06);
      --stroke: rgba(255,255,255,.12);
      --text: rgba(255,255,255,.88);
      --muted: rgba(255,255,255,.62);
    }
    html,body{
      height:100%;
      margin:0;
      background: radial-gradient(1200px 900px at 20% 15%, #17224a, var(--bg1) 45%, var(--bg2));
      color: var(--text);
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial;
      overflow:hidden;
    }
    #bg{
      position:fixed;
      inset:0;
      width:100%;
      height:100%;
      display:block;
    }
    .wrap{
      position:relative;
      height:100%;
      display:grid;
      place-items:center;
      padding:28px;
    }
    .card{
      width:min(980px, 96vw);
      border:1px solid var(--stroke);
      background: linear-gradient(180deg, rgba(255,255,255,.08), rgba(255,255,255,.04));
      border-radius:22px;
      box-shadow: 0 20px 80px rgba(0,0,0,.45);
      backdrop-filter: blur(10px);
      overflow:hidden;
    }
    .top{
      padding:18px 18px 0 18px;
      display:flex;
      align-items:flex-start;
      justify-content:space-between;
      gap:14px;
    }
    .title{
      font-size:18px;
      font-weight:700;
      letter-spacing:.2px;
      margin:0;
    }
    .sub{
      margin:6px 0 0 0;
      color: var(--muted);
      font-size:13px;
      line-height:1.4;
    }
    .pill{
      user-select:none;
      display:flex;
      align-items:center;
      gap:8px;
      padding:10px 12px;
      border-radius:999px;
      border:1px solid var(--stroke);
      background: rgba(0,0,0,.18);
      color: var(--muted);
      font-size:12px;
      white-space:nowrap;
    }
    .dot{
      width:8px;height:8px;border-radius:50%;
      background: #7cf7a8;
      box-shadow: 0 0 0 6px rgba(124,247,168,.12);
    }
    .main{
      padding:16px 18px 18px 18px;
      display:grid;
      grid-template-columns: 1.2fr .8fr;
      gap:14px;
    }
    .panel{
      border:1px solid var(--stroke);
      background: rgba(0,0,0,.18);
      border-radius:18px;
      overflow:hidden;
    }
    .panel h3{
      margin:0;
      padding:12px 14px;
      font-size:13px;
      color: var(--muted);
      border-bottom:1px solid rgba(255,255,255,.08);
      display:flex;
      justify-content:space-between;
      align-items:center;
      gap:10px;
    }
    .panel h3 span{
      font-variant-numeric: tabular-nums;
    }
    #graph{
      width:100%;
      height:420px;
      display:block;
    }
    .list{
      padding:12px 14px;
      display:grid;
      gap:10px;
    }
    .item{
      border:1px solid rgba(255,255,255,.10);
      background: rgba(255,255,255,.06);
      border-radius:14px;
      padding:10px 12px;
    }
    .item b{ font-size:13px; }
    .item p{
      margin:6px 0 0 0;
      color: var(--muted);
      font-size:12px;
      line-height:1.45;
    }
    .kbd{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
      font-size:11px;
      padding:2px 6px;
      border-radius:8px;
      border:1px solid rgba(255,255,255,.14);
      background: rgba(0,0,0,.25);
      color: rgba(255,255,255,.75);
    }
    @media (max-width: 860px){
      .main{ grid-template-columns:1fr; }
      #graph{ height:360px; }
    }
  </style>
</head>
<body>
  <canvas id="bg"></canvas>

  <div class="wrap">
    <div class="card">
      <div class="top">
        <div>
          <h1 class="title">Демо: современная JS-графика внутри встроенного окна</h1>
          <p class="sub">
            Слева — интерактивный мини-граф (узлы двигаются, можно “толкать” мышью).<br/>
            Фон — анимированная сеть частиц. Это обычный JavaScript/Canvas, работает в Qt WebEngine.
          </p>
        </div>
        <div class="pill" title="Работает оффлайн, без CDN">
          <span class="dot"></span>
          <span>WebEngine: OK</span>
          <span class="kbd">move</span> мышь
        </div>
      </div>

      <div class="main">
        <div class="panel">
          <h3>
            <span>Интерактивный “Project Map” (demo)</span>
            <span id="stats">nodes: 0 · edges: 0</span>
          </h3>
          <canvas id="graph"></canvas>
        </div>

        <div class="panel">
          <h3>
            <span>События</span>
            <span class="kbd">click</span>
          </h3>
          <div class="list" id="log">
            <div class="item">
              <b>Подсказка</b>
              <p>Кликни по узлу — справа появится “переход” (как к файлу/коммитам в твоём дипломе).</p>
            </div>
          </div>
        </div>
      </div>

    </div>
  </div>

<script>
/* ---------- Utils ---------- */
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const rand = (a, b) => a + Math.random() * (b - a);

/* ---------- Background particle network ---------- */
(() => {
  const c = document.getElementById('bg');
  const ctx = c.getContext('2d');
  let w=0,h=0,dpr=1;
  const N = 140;
  const pts = [];
  let mouse = {x:-9999,y:-9999};

  function resize(){
    dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
    w = c.clientWidth = window.innerWidth;
    h = c.clientHeight = window.innerHeight;
    c.width = Math.floor(w * dpr);
    c.height = Math.floor(h * dpr);
    ctx.setTransform(dpr,0,0,dpr,0,0);
  }
  window.addEventListener('resize', resize, {passive:true});
  window.addEventListener('mousemove', (e)=>{ mouse.x=e.clientX; mouse.y=e.clientY; }, {passive:true});
  window.addEventListener('mouseleave', ()=>{ mouse.x=-9999; mouse.y=-9999; }, {passive:true});

  function init(){
    pts.length = 0;
    for(let i=0;i<N;i++){
      pts.push({
        x: rand(0,w), y: rand(0,h),
        vx: rand(-0.35,0.35), vy: rand(-0.35,0.35),
        r: rand(0.8, 2.2)
      });
    }
  }

  function tick(){
    ctx.clearRect(0,0,w,h);

    // subtle vignette
    const g = ctx.createRadialGradient(w*0.2,h*0.15, 0, w*0.2,h*0.15, Math.max(w,h));
    g.addColorStop(0, 'rgba(60,120,255,0.08)');
    g.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = g;
    ctx.fillRect(0,0,w,h);

    for(const p of pts){
      p.x += p.vx; p.y += p.vy;
      if(p.x< -20) p.x = w+20;
      if(p.x> w+20) p.x = -20;
      if(p.y< -20) p.y = h+20;
      if(p.y> h+20) p.y = -20;

      // mouse repulsion (soft)
      const dx = p.x - mouse.x, dy = p.y - mouse.y;
      const d2 = dx*dx + dy*dy;
      if(d2 < 140*140){
        const d = Math.sqrt(d2) + 0.001;
        const f = (140 - d) / 140 * 0.04;
        p.vx += (dx/d) * f;
        p.vy += (dy/d) * f;
      }
      // damp
      p.vx *= 0.985;
      p.vy *= 0.985;
      // tiny random drift
      p.vx += rand(-0.012,0.012);
      p.vy += rand(-0.012,0.012);
    }

    // connections
    for(let i=0;i<pts.length;i++){
      for(let j=i+1;j<pts.length;j++){
        const a=pts[i], b=pts[j];
        const dx=a.x-b.x, dy=a.y-b.y;
        const d2=dx*dx+dy*dy;
        if(d2 < 140*140){
          const d = Math.sqrt(d2);
          const alpha = (1 - d/140) * 0.14;
          ctx.strokeStyle = `rgba(180,210,255,${alpha})`;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(a.x,a.y);
          ctx.lineTo(b.x,b.y);
          ctx.stroke();
        }
      }
    }

    // points
    for(const p of pts){
      ctx.fillStyle = 'rgba(255,255,255,0.55)';
      ctx.beginPath();
      ctx.arc(p.x,p.y,p.r,0,Math.PI*2);
      ctx.fill();
    }

    requestAnimationFrame(tick);
  }

  resize(); init(); tick();
})();

/* ---------- Interactive graph canvas (mini force simulation) ---------- */
(() => {
  const canvas = document.getElementById('graph');
  const ctx = canvas.getContext('2d');

  let w=0,h=0,dpr=1;
  let mouse = {x:-9999,y:-9999, down:false};
  let grabbed = null;

  // Demo nodes/edges (в твоём проекте это будут файлы/модули)
  const nodes = [
    {id:'ui/menu.py', label:'ui/menu.py', hot:false},
    {id:'core/game.py', label:'core/game.py', hot:true},
    {id:'core/player.py', label:'core/player.py', hot:false},
    {id:'core/state.py', label:'core/state.py', hot:true},
    {id:'infra/git.py', label:'infra/git.py', hot:false},
    {id:'analysis/ruff.py', label:'analysis/ruff.py', hot:false},
    {id:'analysis/radon.py', label:'analysis/radon.py', hot:false},
    {id:'llm/service.py', label:'llm/service.py', hot:false},
  ].map((n,i)=>({
    ...n,
    x: rand(80, 520),
    y: rand(60, 360),
    vx: rand(-0.8, 0.8),
    vy: rand(-0.8, 0.8),
    r: n.hot ? 16 : 12
  }));

  const edges = [
    ['ui/menu.py','core/game.py'],
    ['core/game.py','core/player.py'],
    ['core/game.py','core/state.py'],
    ['infra/git.py','analysis/ruff.py'],
    ['infra/git.py','analysis/radon.py'],
    ['analysis/ruff.py','llm/service.py'],
    ['analysis/radon.py','llm/service.py'],
    ['core/game.py','llm/service.py'],
  ].map(([a,b])=>({a,b}));

  const stats = document.getElementById('stats');
  stats.textContent = `nodes: ${nodes.length} · edges: ${edges.length}`;

  const byId = new Map(nodes.map(n=>[n.id,n]));

  function resize(){
    const rect = canvas.getBoundingClientRect();
    dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
    w = Math.max(1, Math.floor(rect.width));
    h = Math.max(1, Math.floor(rect.height));
    canvas.width = Math.floor(w*dpr);
    canvas.height = Math.floor(h*dpr);
    canvas.style.width = w+'px';
    canvas.style.height = h+'px';
    ctx.setTransform(dpr,0,0,dpr,0,0);
  }
  window.addEventListener('resize', resize, {passive:true});

  function getMouse(e){
    const r = canvas.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  }

  canvas.addEventListener('mousemove', (e)=>{
    const m = getMouse(e);
    mouse.x = m.x; mouse.y = m.y;
    if(mouse.down && grabbed){
      grabbed.x = m.x;
      grabbed.y = m.y;
      grabbed.vx *= 0.2;
      grabbed.vy *= 0.2;
    }
  }, {passive:true});

  canvas.addEventListener('mousedown', (e)=>{
    mouse.down = true;
    const m = getMouse(e);
    const n = hitTest(m.x, m.y);
    if(n){
      grabbed = n;
    }
  });

  window.addEventListener('mouseup', ()=>{
    mouse.down = false;
    grabbed = null;
  });

  canvas.addEventListener('click', (e)=>{
    const m = getMouse(e);
    const n = hitTest(m.x, m.y);
    if(n){
      logEvent(n);
    }
  });

  function hitTest(x,y){
    for(let i=nodes.length-1;i>=0;i--){
      const n = nodes[i];
      const dx = x-n.x, dy = y-n.y;
      if(dx*dx + dy*dy <= (n.r+6)*(n.r+6)) return n;
    }
    return null;
  }

  function logEvent(node){
    const log = document.getElementById('log');
    const el = document.createElement('div');
    el.className = 'item';
    el.innerHTML = `<b>Выбран узел</b>
      <p><span class="kbd">${escapeHtml(node.id)}</span><br/>
      Здесь в реальном приложении: открыть страницу файла или список коммитов этого файла.</p>`;
    log.prepend(el);
  }

  function escapeHtml(s){
    return (s||'').replace(/[&<>"']/g, c => ({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
    }[c]));
  }

  // Force-like simulation
  function step(){
    // spring edges
    for(const e of edges){
      const a = byId.get(e.a);
      const b = byId.get(e.b);
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dist = Math.sqrt(dx*dx + dy*dy) + 0.001;
      const target = 150;
      const k = 0.004;
      const f = (dist - target) * k;
      const fx = (dx / dist) * f;
      const fy = (dy / dist) * f;
      if(a !== grabbed){ a.vx += fx; a.vy += fy; }
      if(b !== grabbed){ b.vx -= fx; b.vy -= fy; }
    }

    // repulsion
    for(let i=0;i<nodes.length;i++){
      for(let j=i+1;j<nodes.length;j++){
        const a=nodes[i], b=nodes[j];
        const dx=b.x-a.x, dy=b.y-a.y;
        const d2=dx*dx+dy*dy + 0.01;
        const rep = 2600 / d2; // stronger near
        const fx = dx * rep * 0.0012;
        const fy = dy * rep * 0.0012;
        if(a !== grabbed){ a.vx -= fx; a.vy -= fy; }
        if(b !== grabbed){ b.vx += fx; b.vy += fy; }
      }
    }

    // gentle attraction to center
    const cx=w/2, cy=h/2;
    for(const n of nodes){
      if(n === grabbed) continue;
      n.vx += (cx - n.x) * 0.0008;
      n.vy += (cy - n.y) * 0.0008;
    }

    // mouse "gravity" hover
    const hover = hitTest(mouse.x, mouse.y);
    if(hover && hover !== grabbed){
      hover.vx += (mouse.x - hover.x) * 0.002;
      hover.vy += (mouse.y - hover.y) * 0.002;
    }

    // integrate
    for(const n of nodes){
      if(n === grabbed) continue;
      n.x += n.vx;
      n.y += n.vy;
      n.vx *= 0.90;
      n.vy *= 0.90;

      // bounds
      n.x = clamp(n.x, 22, w-22);
      n.y = clamp(n.y, 22, h-22);
    }
  }

  function draw(){
    ctx.clearRect(0,0,w,h);

    // edges
    for(const e of edges){
      const a = byId.get(e.a);
      const b = byId.get(e.b);
      const dx=b.x-a.x, dy=b.y-a.y;
      const dist = Math.sqrt(dx*dx+dy*dy);
      const alpha = clamp(1 - dist/340, 0.10, 0.55);
      ctx.strokeStyle = `rgba(180,210,255,${alpha})`;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(a.x,a.y);
      ctx.lineTo(b.x,b.y);
      ctx.stroke();
    }

    // nodes
    const hover = hitTest(mouse.x, mouse.y);
    for(const n of nodes){
      const isHover = hover && hover.id === n.id;
      const glow = n.hot ? 0.22 : 0.14;
      const r = n.r + (isHover ? 3 : 0);

      // glow
      ctx.fillStyle = `rgba(124,247,168,${n.hot?0.10:0.0})`;
      if(n.hot){
        ctx.beginPath();
        ctx.arc(n.x,n.y,r+10,0,Math.PI*2);
        ctx.fill();
      }

      // body
      ctx.fillStyle = 'rgba(255,255,255,0.08)';
      ctx.beginPath();
      ctx.arc(n.x,n.y,r+6,0,Math.PI*2);
      ctx.fill();

      ctx.fillStyle = n.hot ? 'rgba(124,247,168,0.92)' : 'rgba(255,255,255,0.82)';
      ctx.beginPath();
      ctx.arc(n.x,n.y,r,0,Math.PI*2);
      ctx.fill();

      // ring
      ctx.strokeStyle = `rgba(255,255,255,${isHover?0.30:0.18})`;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(n.x,n.y,r+6,0,Math.PI*2);
      ctx.stroke();

      // label
      ctx.font = '12px ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillStyle = `rgba(255,255,255,${isHover?0.95:0.72})`;
      ctx.fillText(n.label, n.x, n.y + r + 10);
    }
  }

  function loop(){
    step();
    draw();
    requestAnimationFrame(loop);
  }

  // init sizes after layout
  const ro = new ResizeObserver(()=>resize());
  ro.observe(canvas);
  resize();
  loop();
})();
</script>
</body>
</html>
"""

class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PySide6 встроенный браузер — Modern JS Demo")
        self.resize(1200, 760)

        view = QWebEngineView()
        # setHtml работает оффлайн: весь JS/CSS встроен в строку
        view.setHtml(HTML)
        self.setCentralWidget(view)


def main():
    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    w = Window()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

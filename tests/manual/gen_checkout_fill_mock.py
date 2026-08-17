"""Regenerate the checkout-fill mock page from the current module.

The page embeds the real injected script and self-checks its own outcome, so it
is the only thing that proves the observer fires on late-rendered fields.
"""
import io
import os
import sys

sys.path.insert(0, "src")
import checkout_fill

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

script = checkout_fill._build_install_script(
    attendees=[{"name": "王小明", "id_number": "A123456789"},
               {"name": "李小美", "id_number": "B234567890"}],
    card_prefix="41234567",
    allow_card=True,
)

PAGE = """<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<title>結帳自動填入器 — 本機模擬頁</title>
<style>
 body{font-family:system-ui,"Noto Sans TC",sans-serif;max-width:860px;margin:2rem auto;padding:0 1rem}
 .v-input{margin:.5rem 0;padding:.55rem;border:1px solid #ddd;border-radius:6px}
 .v-label{display:block;font-size:.78rem;color:#666;margin-bottom:.25rem}
 input{width:100%;padding:.4rem;border:1px solid #bbb;border-radius:4px;box-sizing:border-box}
 h2{font-size:.95rem;margin:1.3rem 0 .3rem;padding-bottom:.2rem;border-bottom:2px solid #333}
 button{padding:.6rem 1.1rem;font-size:1rem;cursor:pointer;margin-right:.5rem}
 .box{background:#f4f4f4;padding:.7rem;border-radius:6px;font-size:.85rem;font-family:monospace;margin:.6rem 0}
 .note{color:#666;font-size:.85rem}
 .ok{color:#0a0;font-weight:bold} .bad{color:#c00;font-weight:bold}
</style></head><body>
<h1>結帳自動填入器 — 本機模擬頁</h1>
<p class="note">跑的是 <code>src/checkout_fill.py</code> 產生的<strong>同一份</strong> JavaScript。
名單：王小明/A123456789、李小美/B234567890，卡號前碼 41234567。</p>

<h2>訂購人資料（沒有證件號碼欄 → 整段都不該被填）</h2>
<div class="v-input"><label class="v-label">訂購人姓名</label><input type="text"></div>
<div class="v-input"><label class="v-label">訂購人手機</label><input type="text"></div>
<div class="v-input"><label class="v-label">Email</label><input type="text"></div>

<h2>票區與張數</h2>
<div class="v-input"><label class="v-label">張數</label><input type="text" value="2"></div>
<div class="v-input"><label class="v-label">會員姓名</label><input type="text" id="stray"></div>

<p>
  <button id="install">1. 安裝 observer（模擬 bot 進入 /order/ 頁）</button>
  <button id="render">2. 模擬選完張數，1 秒後才 render 出欄位</button>
</p>
<div id="late"></div>
<div class="box" id="out">（尚未安裝）</div>
<div class="box" id="verdict"></div>

<script>
document.getElementById('install').addEventListener('click', function() {
  const result = __SCRIPT__;
  document.getElementById('out').textContent = '安裝結果：' + JSON.stringify(result);
});

document.getElementById('render').addEventListener('click', function() {
  document.getElementById('out').innerHTML += '<br>等 1 秒後動態插入欄位...';
  setTimeout(function() {
    document.getElementById('late').innerHTML = [
      '<h2>中信卡友資格驗證（動態插入）</h2>',
      '<div class="v-input"><label class="v-label">信用卡前6碼</label><input type="text" maxlength="6" id="bin"></div>',
      '<h2>第 1 張票（動態插入）</h2>',
      '<div class="v-input"><label class="v-label">證件姓名</label><input type="text" id="n1"></div>',
      '<div class="v-input"><label class="v-label">持票人手機</label><input type="text" id="p1"></div>',
      '<div class="v-input"><label class="v-label">證件號碼</label><input type="text" id="i1"></div>',
      '<h2>第 2 張票（動態插入）</h2>',
      '<div class="v-input"><label class="v-label">證件姓名</label><input type="text" id="n2"></div>',
      '<div class="v-input"><label class="v-label">持票人手機</label><input type="text" id="p2"></div>',
      '<div class="v-input"><label class="v-label">證件號碼</label><input type="text" id="i2"></div>',
      '<h2>付款（動態插入，前碼填入器不該碰）</h2>',
      '<div class="v-input"><label class="v-label">信用卡號</label><input type="text" id="fullcard"></div>'
    ].join('');

    setTimeout(function() {
      const val = id => (document.getElementById(id) || {}).value || '';
      const orderInputs = Array.from(document.querySelectorAll('.v-input input')).slice(0, 3);
      const checks = [
        ['信用卡前6碼 = 412345（截到 maxlength）', val('bin') === '412345'],
        ['第1張 證件姓名 = 王小明', val('n1') === '王小明'],
        ['第1張 證件號碼 = A123456789', val('i1') === 'A123456789'],
        ['第2張 證件姓名 = 李小美', val('n2') === '李小美'],
        ['第2張 證件號碼 = B234567890', val('i2') === 'B234567890'],
        ['持票人手機 1 保持空白', val('p1') === ''],
        ['持票人手機 2 保持空白', val('p2') === ''],
        ['信用卡號 保持空白（沒被前碼污染）', val('fullcard') === ''],
        ['訂購人區塊保持空白', orderInputs.every(i => !i.value)],
        ['區塊外的「會員姓名」保持空白', val('stray') === '']
      ];
      const lines = checks.map(c => (c[1] ? '<span class="ok">PASS</span>  ' : '<span class="bad">FAIL</span>  ') + c[0]);
      lines.push('');
      lines.push(checks.every(c => c[1]) ? '<span class="ok">ALLPASS</span>' : '<span class="bad">FAILED</span>');
      document.getElementById('verdict').innerHTML = lines.join('<br>');
      document.getElementById('out').innerHTML += '<br>stats: ' + JSON.stringify(window.__thFillStats);
    }, 400);
  }, 1000);
});
</script>
</body></html>
"""

out = os.path.join(OUT_DIR, "checkout_fill_mock.html")
io.open(out, "w", encoding="utf-8").write(PAGE.replace("__SCRIPT__", script))
print(out)

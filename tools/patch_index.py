# -*- coding: utf-8 -*-
"""一次性补丁 index.html（已执行可删除本脚本）。勿对同一文件重复运行。"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
p = ROOT / "templates" / "index.html"
s = p.read_text(encoding="utf-8")
if "async function loadQuizData()" in s:
    raise SystemExit("index.html 已补丁，勿重复运行 tools/patch_index.py")

insert = """// ===== DATA（/static/quiz-data.json 异步加载，缩短首屏）=====
var MATRIX, QUESTIONS, PERSONALITY_TEXTS, PERSONALITY_DIMS, PATTERNS, Q_IDS;
async function loadQuizData() {
  var res = await fetch('/static/quiz-data.json', { cache: 'no-store' });
  if (!res.ok) throw new Error('题库加载失败（HTTP ' + res.status + '）');
  var pack = await res.json();
  MATRIX = pack.matrix;
  QUESTIONS = pack.questions;
  PERSONALITY_TEXTS = pack.personalityTexts;
  PERSONALITY_DIMS = pack.personalityDims;
  PATTERNS = pack.patterns;
  Q_IDS = QUESTIONS.map(function(q) { return q.id; });
}

"""

start_data = s.index("// ===== DATA =====")
end_data = s.index("const EMOJI_MAP = {")
s = s[:start_data] + insert + s[end_data:]

# 去掉依赖 QUESTIONS 的 Q_IDS 行 + 两段 REGION 监听（改由 revealApp 绑定）
qs = s.index("const Q_IDS = QUESTIONS.map")
state_marker = s.index("// ===== STATE =====")
s = s[:qs] + s[state_marker:]

s = s.replace(
    "// ===== STATE =====\nlet state = { answers: {}, currentQ: 0 };",
    "// ===== STATE =====\nvar state = { answers: {}, currentQ: 0 };",
)

old_dup = """  if (!empId) {
    resultDiv.style.display = 'block';
    resultDiv.innerHTML = '<p style="color:var(--primary); font-size:14px;">请输入工号</p>';
    return;
  }
  if (!empId) {
    resultDiv.style.display = 'block';
    resultDiv.innerHTML = '<p style="color:var(--primary); font-size:14px;">请输入工号</p>';
    return;
  }

"""
s = s.replace(
    old_dup,
    "  if (!empId) {\n    resultDiv.style.display = 'block';\n    resultDiv.innerHTML = '<p style=\"color:var(--primary); font-size:14px;\">请输入工号</p>';\n    return;\n  }\n\n",
)

s = s.replace("\\u{1F48C} 安慰一下：", "💌 安慰一下：")

submit_pat = re.compile(
    r"function submitQuiz\(\) \{.*?showResult\(displayName, bestScore\);\s*\n\}",
    re.DOTALL,
)
submit_new = r"""function submitQuiz() {
  if (window.__cbtiSubmitting) return;
  const Q_IDS = Object.keys(state.answers).sort((a, b) => {
    const na = parseInt(a.replace('Q',''));
    const nb = parseInt(b.replace('Q',''));
    return na - nb;
  });
  const choices = Q_IDS.map(qid => state.answers[qid] || 'A');

  let bestPersonality = null;
  let bestScore = 999;

  for (const [pName, pattern] of Object.entries(PATTERNS)) {
    let haming = 0;
    for (let i = 0; i < 21; i++) {
      if (choices[i] !== pattern[i]) haming++;
    }
    if (haming < bestScore) {
      bestScore = haming;
      bestPersonality = pName;
    }
  }

  let displayName = bestPersonality;
  if (bestPersonality === 'Ctrl+Z终身成就奖得主') displayName = 'Ctrl+Z 终身成就奖得主';

  const userDims = [0, 0, 0];
  for (let i = 0; i < 21; i++) {
    const qid = Q_IDS[i];
    const choice = choices[i];
    const dims = MATRIX[qid] && MATRIX[qid][choice];
    if (dims) {
      userDims[0] += dims[0];
      userDims[1] += dims[1];
      userDims[2] += dims[2];
    }
  }

  const dims = PERSONALITY_DIMS[displayName] || [];
  const submitId = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : ('s' + Date.now() + '-' + Math.random().toString(36).slice(2, 11));
  const payload = {
    name: state.userInfo?.name || '',
    empId: state.userInfo?.empId || '',
    dept: state.userInfo?.dept || '',
    region: state.userInfo?.region || '',
    result: displayName,
    haming: bestScore,
    dims: dims,
    userDims: userDims,
    answers: state.answers,
    submitId: submitId
  };

  var overlay = document.getElementById('submit-overlay');
  if (overlay) overlay.style.display = 'flex';
  window.__cbtiSubmitting = true;

  function sleep(ms) { return new Promise(function(r) { setTimeout(r, ms); }); }

  function tryPost(attempt) {
    return fetch('/api/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(function(r) {
      if (r.ok) return r.json();
      if (r.status >= 500 && attempt < 3) {
        return sleep(1000 * Math.pow(2, attempt)).then(function() { return tryPost(attempt + 1); });
      }
      return r.json().then(function(body) {
        throw new Error(body.message || ('HTTP ' + r.status));
      }).catch(function() {
        throw new Error('HTTP ' + r.status);
      });
    }).catch(function(err) {
      if (attempt < 3) {
        return sleep(1000 * Math.pow(2, attempt)).then(function() { return tryPost(attempt + 1); });
      }
      throw err;
    });
  }

  tryPost(0).then(function(data) {
    if (!data.ok) throw new Error(data.message || '保存失败');
    window.__cbtiSubmitting = false;
    if (overlay) overlay.style.display = 'none';
    showResult(displayName, bestScore);
  }).catch(function(err) {
    window.__cbtiSubmitting = false;
    if (overlay) overlay.style.display = 'none';
    alert('结果保存失败，请检查网络后重试：' + (err && err.message ? err.message : err));
  });
}
"""
m = submit_pat.search(s)
if not m:
    raise SystemExit("submitQuiz pattern not found")
s = submit_pat.sub(submit_new, s, count=1)

if 'id="submit-overlay"' not in s:
    s = s.replace(
        '<div id="quiz-screen">',
        '<div id="quiz-screen">\n  <div id="submit-overlay" style="display:none; position:fixed; inset:0; background:rgba(248,245,240,0.92); z-index:200; align-items:center; justify-content:center; flex-direction:column; gap:12px;">\n    <div style="font-size:17px; font-weight:700; color:var(--secondary);">正在保存测评结果…</div>\n    <div style="font-size:13px; color:var(--text-light);">请稍候，勿关闭页面</div>\n  </div>',
        1,
    )

s = s.replace(
    """// 页面加载后显示二维码（方便扫码分享）
document.addEventListener('DOMContentLoaded', function() {
  showQRCode(window.location.href);
});

</script>""",
    "</script>",
    1,
)

old_boot = """<script>
  // 加载动画：等所有资源（含图片）都加载完毕再显示
  (function() {
    var loading = document.getElementById('app-loading');
    var content = document.getElementById('app-content');
    if (!loading || !content) return;

    // 先预显示100ms让CSS动画跑起来
    setTimeout(function() {
      // 等 window.onload（所有图片/资源都加载完）
      if (document.readyState === 'complete') {
        loading.style.display = 'none';
        content.style.display = 'block';
        content.classList.add('ready');
      } else {
        window.addEventListener('load', function() {
          loading.style.display = 'none';
          content.style.display = 'block';
          content.classList.add('ready');
        });
      }
    }, 200);
  })();
</script>"""
s = s.replace(
    old_boot,
    "<!-- 首屏显示改由题库 JSON 加载完成后触发（revealApp） -->\n",
    1,
)

old_keep = """<script>
(function() {
  function keepAlive() {
    fetch('/health', { method: 'GET', cache: 'no-store' }).catch(function() {});
  }
  // 页面加载时立即ping一次
  keepAlive();
  // 之后每4分钟ping一次
  setInterval(keepAlive, 4 * 60 * 1000);
})();
</script>"""
new_keep = """<script>
(function() {
  function keepAlive() {
    if (document.hidden) return;
    fetch('/health', { method: 'GET', cache: 'no-store' }).catch(function() {});
  }
  keepAlive();
  setInterval(keepAlive, 4 * 60 * 1000);
  document.addEventListener('visibilitychange', function() {
    if (!document.hidden) keepAlive();
  });
})();
</script>"""
s = s.replace(old_keep, new_keep, 1)

inject = """
// ===== 启动：题库加载完成后再展示主界面（不等待全部图片）=====
function bindRegionOtherOnce() {
  var regionSelect = document.getElementById('field-region');
  var otherInput = document.getElementById('field-region-other');
  if (!regionSelect || !otherInput || regionSelect.__cbtiBound) return;
  regionSelect.__cbtiBound = true;
  regionSelect.addEventListener('change', function() {
    if (this.value === '其他区域') {
      otherInput.style.display = 'block';
    } else {
      otherInput.style.display = 'none';
      otherInput.value = '';
    }
  });
}

function revealApp() {
  var loading = document.getElementById('app-loading');
  var content = document.getElementById('app-content');
  if (loading) loading.style.display = 'none';
  if (content) {
    content.style.display = 'block';
    content.classList.add('ready');
  }
  bindRegionOtherOnce();
  try { showQRCode(window.location.href); } catch (e) {}
}

document.addEventListener('DOMContentLoaded', function() {
  loadQuizData().then(function() {
    setTimeout(revealApp, 80);
  }).catch(function(err) {
    var loading = document.getElementById('app-loading');
    if (loading) {
      loading.innerHTML = '<div style="padding:32px;text-align:center;color:#c0392b;font-size:15px;">加载题库失败，请刷新重试<br><span style="color:#666;font-size:13px;">' + (err && err.message ? err.message : err) + '</span></div>';
    }
  });
});
"""
inject_anchor = "// ===== RESTART ====="
if "function revealApp()" not in s:
    s = s.replace(inject_anchor, inject + "\n\n" + inject_anchor, 1)

p.write_text(s, encoding="utf-8")
print("patched", p)

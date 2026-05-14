#!/usr/bin/env python3
"""CBTI 职场人格鉴定所 — 生产版（SQLite / PostgreSQL + Gunicorn）"""
import csv
import io
import json
import re
import os

import qrcode
from urllib.parse import quote
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    stream_with_context,
    url_for,
)
from flask_compress import Compress

import db as database

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cbti-secret-key-change-me")
app.config.update(
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "").lower() in ("1", "true", "yes"),
    COMPRESS_MIN_SIZE=int(os.environ.get("COMPRESS_MIN_SIZE", "2048")),
    # 流式/大文件下载不压缩，避免缓冲整包导致内存暴涨或浏览器卡死
    COMPRESS_MIMETYPES=[
        "text/html",
        "text/css",
        "text/xml",
        "application/json",
        "application/javascript",
        "text/javascript",
        "application/x-javascript",
        "image/svg+xml",
    ],
)

Compress(app)

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
# 兼容旧部署：可通过环境变量关闭硬编码备用密码
LEGACY_ADMIN_PASSWORD = os.environ.get("LEGACY_ADMIN_PASSWORD", "cbti2024")

def _admin_password_ok(pwd: str) -> bool:
    if pwd == ADMIN_PASSWORD:
        return True
    if LEGACY_ADMIN_PASSWORD and pwd == LEGACY_ADMIN_PASSWORD:
        return True
    return False


def _normalize_answers_keys(answers):
    """统一 answers 的键名为大写 Q 格式（兼容前端 Q1 与压测 q1）。"""
    if not isinstance(answers, dict):
        return answers
    normalized = {}
    for k, v in answers.items():
        m = re.match(r'[qQ](\d+)$', str(k))
        if m:
            normalized[f"Q{m.group(1)}"] = v
        else:
            normalized[k] = v
    return normalized



def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)

    return decorated


# ── 预加载 quiz-data.json ──────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_QUIZ_DATA: dict = {}
_quiz_path = os.path.join(BASE_DIR, "static", "quiz-data.json")
if os.path.exists(_quiz_path):
    with open(_quiz_path, "r", encoding="utf-8") as f:
        _QUIZ_DATA = json.load(f)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        pwd = request.form.get("password", "")
        if _admin_password_ok(pwd):
            session["admin_logged_in"] = True
            return redirect(url_for("admin"))
        error = "密码错误，请重试"
    return render_template("admin_login.html", error=error)


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin_login"))


_QR_DATA_MAX = int(os.environ.get("QR_DATA_MAX_LEN", "2048"))


@app.route("/api/quiz-data")
def quiz_data():
    """内存中返回预加载的题目数据，避免磁盘 I/O。"""
    return jsonify(_QUIZ_DATA)


@app.route("/api/qr")
def serve_qr():
    """同源生成二维码 PNG，避免依赖外网 api.qrserver.com（移动端慢/空白）。"""
    raw = request.args.get("data", "") or ""
    if not raw.strip():
        return jsonify({"ok": False, "message": "缺少 data"}), 400
    if len(raw) > _QR_DATA_MAX:
        return jsonify({"ok": False, "message": f"链接过长（>{_QR_DATA_MAX}）"}), 400
    box = request.args.get("box", 6, type=int) or 6
    box = max(3, min(box, 12))
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box,
        border=2,
    )
    qr.add_data(raw)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    resp = send_file(buf, mimetype="image/png")
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


@app.route("/")
def index():
    return render_template("index.html")


@app.after_request
def _cache_quiz_json(resp):
    # 题库会随手册修订而更新，不可用 long immutable 缓存，否则用户长期看到旧题
    if request.path.endswith("/static/quiz-data.json"):
        resp.headers["Cache-Control"] = "no-cache, must-revalidate, max-age=0"
    return resp


@app.route("/api/submit", methods=["POST"])
def submit():
    data = request.get_json()
    if not data:
        return jsonify({"ok": False, "message": "无数据"}), 400

    name = (data.get("name") or "").strip()
    dept = (data.get("dept") or "").strip()
    region = (data.get("region") or "").strip()
    submit_id = (data.get("submitId") or data.get("submit_id") or "").strip() or None

    if not name:
        return jsonify({"ok": False, "message": "请输入姓名"}), 400
    if not region:
        return jsonify({"ok": False, "message": "请选择区域"}), 400

    record, was_dup = database.save_record(
        {
            "name": name,
            "dept": dept,
            "region": region,
            "result": data.get("result", ""),
            "haming": data.get("haming", 0),
            "dims": data.get("dims", []),
            "answers": _normalize_answers_keys(data.get("answers", {})),
            "time": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S"),
        },
        client_submit_id=submit_id,
    )
    return jsonify(
        {
            "ok": True,
            "message": "提交成功",
            "id": record["id"],
            "deduplicated": was_dup,
        }
    )


@app.route("/api/query", methods=["POST"])
def query_result():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    dept = (data.get("dept") or "").strip()
    if not name:
        return jsonify({"ok": False, "message": "请输入姓名"}), 400
    row = database.query_latest_by_name_dept(name, dept)
    if not row:
        return jsonify({"ok": False, "message": "未找到记录，请检查姓名和部门"}), 404
    return jsonify({"ok": True, "record": row})


@app.route("/admin")
@admin_required
def admin():
    page = request.args.get("page", 1, type=int) or 1
    page_size = 150
    total = database.count_records()
    total_pages = max(1, (total + page_size - 1) // page_size)
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages
    region_stats, dept_stats, result_stats = database.stats_aggregates()
    # 默认最新提交在前，避免新数据落在最后一页被误以为「后台没数据」
    page_records = database.fetch_records_page(page, page_size, order_asc=False)
    return render_template(
        "admin.html",
        records=page_records,
        total=total,
        page=page,
        total_pages=total_pages,
        page_size=page_size,
        region_stats=region_stats,
        dept_stats=dept_stats,
        result_stats=result_stats,
    )


@app.route("/api/data")
@admin_required
def get_data():
    """
    默认分页 JSON。参数：
      - page, per_page（per_page 最大 2000）
      - flat=1 时仅返回当前页的数组（兼容旧脚本）
      - legacy_array=1&max_rows=5000 时拉取多页合并为单数组（有上限，慎用）
    """
    flat = request.args.get("flat") == "1"
    legacy = request.args.get("legacy_array") == "1"
    page = request.args.get("page", 1, type=int) or 1
    per_page = min(2000, max(1, request.args.get("per_page", 100, type=int) or 100))

    if legacy:
        max_rows = min(5000, int(request.args.get("max_rows", 5000)))
        merged = []
        p = 1
        chunk_size = min(500, per_page, max_rows)
        while len(merged) < max_rows:
            total, chunk = database.fetch_records_page_json(p, chunk_size)
            if not chunk:
                break
            merged.extend(chunk)
            if len(chunk) < chunk_size or len(merged) >= total:
                break
            p += 1
        return jsonify(merged[:max_rows])

    total, items = database.fetch_records_page_json(page, per_page)
    if flat:
        return jsonify(items)
    return jsonify(
        {
            "ok": True,
            "total": total,
            "page": page,
            "per_page": per_page,
            "items": items,
            "hint": "分页接口；全量请用 /api/export/ndjson 或导出 CSV；旧版数组可加 ?flat=1",
        }
    )


@stream_with_context
def _ndjson_record_lines():
    for rec in database.iter_all_records_rowwise():
        line = json.dumps(rec, ensure_ascii=False) + "\n"
        yield line


@app.route("/api/export/ndjson")
@admin_required
def export_ndjson():
    """流式 NDJSON，适合全量备份，避免一次性占用大量内存。"""
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote('CBTI_records.ndjson')}",
        "X-Accel-Buffering": "no",
        "Cache-Control": "no-store",
    }
    return Response(
        _ndjson_record_lines(),
        mimetype="application/x-ndjson",
        headers=headers,
    )


@stream_with_context
def _csv_export_rows():
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "序号",
            "姓名",
            "部门",
            "区域",
            "测评结果",
            "Haming距离",
            "D1主动性",
            "D2社交性",
            "D3规则性",
            "答题详情",
            "提交时间",
        ]
    )
    yield buf.getvalue().encode("utf-8-sig")
    buf.seek(0)
    buf.truncate(0)
    for r in database.iter_all_records_rowwise():
        answers_str = " ".join([f"{k}:{v}" for k, v in (r.get("answers") or {}).items()])
        writer.writerow(
            [
                r.get("id", ""),
                r.get("name", ""),
                r.get("dept", ""),
                r.get("region", ""),
                r.get("result", ""),
                r.get("haming", 0),
                (r.get("dims") or [None, None, None])[0] or "",
                (r.get("dims") or [None, None, None])[1] or "",
                (r.get("dims") or [None, None, None])[2] or "",
                answers_str,
                r.get("time", ""),
            ]
        )
        if buf.tell() > 65536:
            yield buf.getvalue().encode("utf-8")
            buf.seek(0)
            buf.truncate(0)
    if buf.tell():
        yield buf.getvalue().encode("utf-8")


@app.route("/api/export/csv")
@admin_required
def export_csv():
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote('CBTI测评数据_export.csv')}",
        "X-Accel-Buffering": "no",
        "Cache-Control": "no-store",
    }
    return Response(
        _csv_export_rows(),
        mimetype="text/csv; charset=utf-8",
        headers=headers,
    )


@app.route("/api/update/<int:record_id>", methods=["POST"])
@admin_required
def update_record(record_id):
    data = request.get_json() or {}
    row = database.get_record_row(record_id)
    if not row:
        return jsonify({"ok": False, "message": "记录不存在"}), 404
    m = row._mapping
    name = (data.get("name") or m["name"]).strip()
    dept = (data.get("dept") or m.get("dept") or "").strip()
    region = (data.get("region") or m.get("region") or "").strip()
    result = data.get("result") or m.get("result") or ""
    database.update_record_fields(record_id, name, dept, region, result)
    return jsonify({"ok": True, "message": "更新成功"})


@app.route("/api/delete/<int:record_id>", methods=["POST"])
@admin_required
def delete_record(record_id):
    if not database.delete_record_by_id(record_id):
        return jsonify({"ok": False, "message": "记录不存在"}), 404
    return jsonify({"ok": True, "message": "删除成功"})


@app.route("/api/clear", methods=["POST"])
@admin_required
def clear_all():
    count = database.clear_all_records()
    return jsonify({"ok": True, "message": f"已清空 {count} 条记录"})


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


database.init_db()
database.migrate_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7860, debug=True)

@app.route("/api/migrate")
@admin_required
def api_migrate():
    """执行数据库迁移（添加索引等），用于线上快速修复。"""
    try:
        database.init_db()
        return jsonify({"ok": True, "message": "数据库迁移完成（索引已创建）"})
    except Exception as e:
        return jsonify({"ok": False, "message": f"迁移失败: {e}"}), 500

@app.route("/api/db-stats")
@admin_required
def api_db_stats():
    """轻量级数据库状态检查。"""
    try:
        total = database.count_records()
        return jsonify({"ok": True, "total": total})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)}), 500

@app.after_request
def add_cors_headers(resp):
    resp.headers["X-Robots-Tag"] = "noindex"
    return resp


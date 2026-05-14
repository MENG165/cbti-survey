"""数据库访问层：支持 SQLite（默认）与 PostgreSQL（DATABASE_URL）。

v3 — SQLite 高并发优化（核心思路：后台队列批量写入，非忙等）：
  - 读：使用独立 Engine 直连（WAL 模式下读写不互斥）
  - 写：通过 queue.SimpleQueue 提交，后台线程定期批量 multi-INSERT
  - 调用方通过 threading.Event 等待结果，不消耗 CPU
  - 新增 (name, dept) 复合索引加速查询
  - 增强 PRAGMA 并发调优
"""
from __future__ import annotations

import json
import os
import queue
import threading
import time
from typing import Any, Dict, Iterator, List, Optional, Tuple

from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    Table,
    Text,
    create_engine,
    delete,
    func,
    inspect,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.engine import Engine
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
import concurrent.futures

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data.db")


def _normalize_database_url() -> str:
    raw = (os.environ.get("DATABASE_URL") or "").strip()
    if raw:
        if raw.startswith("postgres://"):
            return "postgresql+psycopg2://" + raw[len("postgres://") :]
        return raw
    return f"sqlite:///{os.path.abspath(DB_PATH)}"


DATABASE_URL = _normalize_database_url()
IS_SQLITE = DATABASE_URL.startswith("sqlite")


def _make_engine(file_path: str = "") -> Engine:
    url = file_path if file_path else DATABASE_URL
    if url.startswith("sqlite"):
        eng = create_engine(
            url,
            connect_args={"timeout": 30, "check_same_thread": False},
            pool_pre_ping=True,
        )

        @event.listens_for(eng, "connect")
        def _sqlite_pragmas(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.execute("PRAGMA cache_size=-64000")
            cur.execute("PRAGMA mmap_size=268435456")
            cur.execute("PRAGMA journal_size_limit=67108864")
            cur.execute("PRAGMA temp_store=MEMORY")
            cur.close()

        return eng

    return create_engine(
        url,
        pool_size=int(os.environ.get("DB_POOL_SIZE", "20")),
        max_overflow=int(os.environ.get("DB_MAX_OVERFLOW", "40")),
        pool_pre_ping=True,
        pool_recycle=int(os.environ.get("DB_POOL_RECYCLE", "3600")),
    )


engine = _make_engine()
metadata = MetaData()

records_tbl = Table(
    "records",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", Text, nullable=False),
    Column("dept", Text, nullable=False),

    Column("region", Text, nullable=False),
    Column("result", Text),
    Column("haming", Integer),
    Column("dims", Text),
    Column("answers", Text),
    Column("time", Text),
    Column("client_submit_id", Text),
)


# -- background batch writer (SQLite only) ----------------------------------

class _WriteItem:
    """Write request item containing values + sync primitives."""
    __slots__ = ("values", "event", "id", "error")
    def __init__(self, values: dict):
        self.values = values
        self.event = threading.Event()
        self.id: Optional[int] = None
        self.error: Optional[Exception] = None


class _BatchWriter(threading.Thread):
    """Background thread that accumulates writes and flushes as multi-INSERT.

    - Every 50 items or 0.3s idle time, flushes all pending writes as a single
      multi-INSERT ... RETURNING.
    - Callers block on threading.Event (zero CPU wait).
    """

    def __init__(self, engine, max_batch: int = 50, max_interval: float = 0.3):
        super().__init__(daemon=True)
        self.engine = engine
        self.max_batch = max_batch
        self.max_interval = max_interval
        self._queue: queue.SimpleQueue = queue.SimpleQueue()
        self._stop_event = threading.Event()
        self.name = "BatchWriter"
        self.start()

    def submit(self, values: dict) -> int:
        """Enqueue a write request and block until ID is assigned."""
        item = _WriteItem(values)
        self._queue.put(item)
        item.event.wait()
        if item.error:
            raise item.error
        return item.id  # type: ignore[return-value]

    def stop(self):
        self._stop_event.set()

    def run(self):
        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=self.max_interval)
            except queue.Empty:
                continue

            batch = [item]
            deadline = time.monotonic() + 0.05
            while len(batch) < self.max_batch and time.monotonic() < deadline:
                try:
                    batch.append(self._queue.get_nowait())
                except queue.Empty:
                    break

            self._flush(batch)

        # drain remaining items at shutdown
        tail = []
        while True:
            try:
                tail.append(self._queue.get_nowait())
            except queue.Empty:
                break
        if tail:
            self._flush(tail)

    def _flush(self, batch: list):
        """Execute multi-INSERT ... RETURNING and notify all waiters."""
        values_list = [item.values for item in batch]
        try:
            with self.engine.begin() as conn:
                stmt = insert(records_tbl).returning(records_tbl.c.id)
                ids = list(conn.execute(stmt, values_list).scalars())
            for item, pk in zip(batch, ids):
                item.id = int(pk)
                item.event.set()
        except Exception as exc:
            for item in batch:
                item.error = exc
                item.event.set()


_write_batch: Optional[_BatchWriter] = _BatchWriter(engine) if IS_SQLITE else None


# -- table / index creation -------------------------------------------------

def init_db() -> None:
    metadata.create_all(engine)
    _ensure_indexes(engine)


def _ensure_indexes(engine) -> None:
    """为高频查询列添加索引（幂等，IF NOT EXISTS）。"""
    indexes = [
        ("idx_records_name", "records", "name"),
        ("idx_records_dept", "records", "dept"),
        ("idx_records_region", "records", "region"),
        ("idx_records_result", "records", "result"),
        ("idx_records_time", "records", "time"),
        ("idx_records_client_submit", "records", "client_submit_id"),
    ]
    for idx_name, tbl, col in indexes:
        try:
            with engine.connect() as conn:
                conn.execute(
                    text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {tbl} ({col})")
                )
                conn.commit()
        except Exception:
            pass  # 兼容不支持IF NOT EXISTS的旧版SQLite
    # 复合索引：name+dept 加速按姓名+部门的查询
    try:
        with engine.connect() as conn:
            conn.execute(
                text("CREATE INDEX IF NOT EXISTS idx_records_name_dept ON records (name, dept)")
            )
            conn.commit()
    except Exception:
        pass


def migrate_db() -> None:
    insp = inspect(engine)
    if not insp.has_table("records"):
        return
    cols = {c["name"] for c in insp.get_columns("records")}
    with engine.begin() as conn:
        if "region" not in cols:
            try:
                if IS_SQLITE:
                    conn.execute(text("ALTER TABLE records ADD COLUMN region TEXT NOT NULL DEFAULT ''"))
                else:
                    conn.execute(text('ALTER TABLE records ADD COLUMN "region" TEXT NOT NULL DEFAULT '''))
            except Exception:
                pass
        if "client_submit_id" not in cols:
            try:
                if IS_SQLITE:
                    conn.execute(text("ALTER TABLE records ADD COLUMN client_submit_id TEXT"))
                else:
                    conn.execute(text('ALTER TABLE records ADD COLUMN "client_submit_id" TEXT'))
            except Exception:
                pass

    with engine.begin() as conn:
        if IS_SQLITE:
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_records_client_submit_id "
                    "ON records(client_submit_id) WHERE client_submit_id IS NOT NULL"
                )
            )
        else:
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_records_client_submit_id "
                    "ON records (client_submit_id) WHERE client_submit_id IS NOT NULL"
                )
            )


    # -- 向后兼容：若旧表存在 empId 列，迁移删除该列 ---------------
    if "empId" in cols:
        with engine.begin() as conn:
            if IS_SQLITE:
                # SQLite 不支持 ALTER TABLE DROP COLUMN（<3.35.0），采用重建表方式
                conn.execute(text("SAVEPOINT empid_migration"))
                try:
                    conn.execute(
                        text(
                            "CREATE TABLE records_v2 ("
                            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                            "  name TEXT NOT NULL,"
                            "  dept TEXT NOT NULL,"
                            "  region TEXT NOT NULL,"
                            "  result TEXT,"
                            "  haming INTEGER,"
                            "  dims TEXT,"
                            "  answers TEXT,"
                            "  time TEXT,"
                            "  client_submit_id TEXT"
                            ")"
                        )
                    )
                    conn.execute(
                        text(
                            "INSERT INTO records_v2 (id, name, dept, region, result, haming, dims, answers, time, client_submit_id) "
                            "SELECT id, name, dept, region, result, haming, dims, answers, time, client_submit_id FROM records"
                        )
                    )
                    conn.execute(text("DROP TABLE records"))
                    conn.execute(text("ALTER TABLE records_v2 RENAME TO records"))
                    conn.execute(
                        text(
                            "CREATE UNIQUE INDEX IF NOT EXISTS idx_records_client_submit_id "
                            "ON records(client_submit_id) WHERE client_submit_id IS NOT NULL"
                        )
                    )

                    conn.execute(text("RELEASE SAVEPOINT empid_migration"))
                except Exception:
                    conn.execute(text("ROLLBACK TO SAVEPOINT empid_migration"))
                    conn.execute(text("RELEASE SAVEPOINT empid_migration"))
                    raise
            else:
                # PostgreSQL 可直接 DROP COLUMN
                conn.execute(text('ALTER TABLE records DROP COLUMN "empId"'))


# -- row conversion -----------------------------------------------------------

def _row_to_record(m: Any) -> Dict[str, Any]:
    return {
        "id": m["id"],
        "name": m["name"],
        "dept": m.get("dept") or "",

        "region": m.get("region") or "",
        "result": m.get("result") or "",
        "haming": m.get("haming") or 0,
        "dims": json.loads(m["dims"]) if m.get("dims") else [],
        "answers": json.loads(m["answers"]) if m.get("answers") else {},
        "time": m.get("time") or "",
    }


# -- read operations ----------------------------------------------------------

def count_records() -> int:
    with engine.connect() as conn:
        return int(conn.scalar(select(func.count()).select_from(records_tbl)) or 0)


def stats_aggregates() -> Tuple[Dict[str, int], Dict[str, int], Dict[str, int]]:
    """区域 / 部门 / 结果 三维聚合（单连接，单次查询实现）。"""
    def stat(col: str) -> Dict[str, int]:
        stmt = text(
            f"SELECT CASE WHEN trim(coalesce({col}, '')) = '' THEN '未知' ELSE trim({col}) END AS bucket, "
            f"COUNT(*) AS c FROM records GROUP BY 1 ORDER BY c DESC"
        )
        out: Dict[str, int] = {}
        try:
            with engine.connect() as conn:
                for bucket, c in conn.execute(stmt):
                    out[str(bucket)] = int(c)
        except Exception:
            pass
        return out

    # 并行执行三个聚合查询，减少总耗时
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        f_region = pool.submit(stat, "region")
        f_dept = pool.submit(stat, "dept")
        f_result = pool.submit(stat, "result")
        return f_region.result(), f_dept.result(), f_result.result()


def fetch_records_page(page: int, page_size: int, order_asc: bool = True) -> List[Dict[str, Any]]:
    page = max(1, page)
    offset = (page - 1) * page_size
    order_col = records_tbl.c.id.asc() if order_asc else records_tbl.c.id.desc()
    stmt = select(records_tbl).order_by(order_col).limit(page_size).offset(offset)
    rows: List[Dict[str, Any]] = []
    with engine.connect() as conn:
        for row in conn.execute(stmt):
            rows.append(_row_to_record(row._mapping))
    return rows


def iter_all_records_rowwise() -> Iterator[Dict[str, Any]]:
    """流式遍历全表（用于导出），按 id 升序。"""
    stmt = select(records_tbl).order_by(records_tbl.c.id.asc())
    with engine.connect() as conn:
        result = conn.execution_options(stream_results=True).execute(stmt)
        for row in result:
            yield _row_to_record(row._mapping)


def fetch_records_page_json(page: int, per_page: int) -> Tuple[int, List[Dict[str, Any]]]:
    total = count_records()
    per_page = max(1, min(per_page, 2000))
    page = max(1, page)
    max_page = max(1, (total + per_page - 1) // per_page)
    if page > max_page:
        page = max_page
    offset = (page - 1) * per_page
    stmt = select(records_tbl).order_by(records_tbl.c.id.asc()).limit(per_page).offset(offset)
    items: List[Dict[str, Any]] = []
    with engine.connect() as conn:
        for row in conn.execute(stmt):
            items.append(_row_to_record(row._mapping))
    return total, items


def query_latest_by_name_dept(name: str, dept: str = "") -> Optional[Dict[str, Any]]:
    stmt = (
        select(records_tbl)
        .where(records_tbl.c.name == name)
    )
    if dept:
        stmt = stmt.where(records_tbl.c.dept == dept)
    stmt = stmt.order_by(records_tbl.c.id.desc()).limit(1)
    with engine.connect() as conn:
        row = conn.execute(stmt).fetchone()
        if not row:
            return None
        m = row._mapping
        return {
            "name": m["name"],
            "dept": m.get("dept") or "",
    
            "region": m.get("region") or "",
            "result": m.get("result") or "",
            "haming": m.get("haming") or 0,
            "dims": json.loads(m["dims"]) if m.get("dims") else [],
            "time": m.get("time") or "",
        }


# -- write operations ---------------------------------------------------------

def save_record(record: Dict[str, Any], client_submit_id: Optional[str] = None) -> Tuple[Dict[str, Any], bool]:
    """
    插入一条记录。若提供 client_submit_id 且已存在，则返回已有 id（幂等）。
    返回 (record_with_id, was_duplicate)
    """
    submit_id = (client_submit_id or "").strip() or None

    # idempotency check
    if submit_id:
        with engine.connect() as conn:
            existing = conn.execute(
                select(records_tbl.c.id).where(records_tbl.c.client_submit_id == submit_id)
            ).scalar_one_or_none()
            if existing is not None:
                record["id"] = int(existing)
                return record, True

    values = {
        "name": record["name"],
        "dept": record.get("dept", ""),

        "region": record.get("region", ""),
        "result": record["result"],
        "haming": record.get("haming", 0),
        "dims": json.dumps(record.get("dims") or [], ensure_ascii=False),
        "answers": json.dumps(record.get("answers") or {}, ensure_ascii=False),
        "time": record["time"],
        "client_submit_id": submit_id,
    }

    if IS_SQLITE and _write_batch is not None:
        # non-blocking batch write via background thread
        record_id = _write_batch.submit(values)
        record["id"] = record_id
        return record, False

    # PostgreSQL direct write
    try:
        with engine.begin() as conn:
            res = conn.execute(insert(records_tbl).values(**values).returning(records_tbl.c.id))
            pk = res.scalar_one()
            record["id"] = int(pk)
            return record, False
    except IntegrityError:
        if not submit_id:
            raise
        with engine.connect() as conn:
            existing = conn.execute(
                select(records_tbl.c.id).where(records_tbl.c.client_submit_id == submit_id)
            ).scalar_one()
            record["id"] = int(existing)
            return record, True


def update_record_fields(record_id: int, name: str, dept: str, region: str, result: str) -> bool:
    with engine.begin() as conn:
        r = conn.execute(select(records_tbl.c.id).where(records_tbl.c.id == record_id)).fetchone()
        if not r:
            return False
        conn.execute(
            update(records_tbl)
            .where(records_tbl.c.id == record_id)
            .values(name=name, dept=dept, region=region, result=result)
        )
    return True


def delete_record_by_id(record_id: int) -> bool:
    with engine.begin() as conn:
        r = conn.execute(select(records_tbl.c.id).where(records_tbl.c.id == record_id)).fetchone()
        if not r:
            return False
        conn.execute(delete(records_tbl).where(records_tbl.c.id == record_id))
    return True


def clear_all_records() -> int:
    with engine.begin() as conn:
        n = conn.scalar(select(func.count()).select_from(records_tbl)) or 0
        if IS_SQLITE:
            conn.execute(delete(records_tbl))
            try:
                conn.execute(text("DELETE FROM sqlite_sequence WHERE name='records'"))
            except Exception:
                pass  # sqlite_sequence 表可能不存在（无自增记录时）
        else:
            conn.execute(text("TRUNCATE TABLE records RESTART IDENTITY"))
        return int(n)


def get_record_row(record_id: int) -> Optional[Any]:
    with engine.connect() as conn:
        return conn.execute(select(records_tbl).where(records_tbl.c.id == record_id)).fetchone()



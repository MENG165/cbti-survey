#!/usr/bin/env python3
"""CBTI 数据迁移工具：SQLite → PostgreSQL

使用方法：
  1. 在 Railway 上添加 PostgreSQL 插件
  2. 在 PostgreSQL 服务页面复制 DATABASE_URL
  3. 运行：python migrate_to_pg.py "postgresql://..."
"""

import json
import os
import sys
import sqlite3
from urllib.parse import urlparse

def migrate(sqlite_path: str, pg_url: str):
    """从 SQLite 迁移所有记录到 PostgreSQL"""

    # 1. 读取 SQLite
    print(f"[1/4] 连接 SQLite: {sqlite_path}")
    if not os.path.exists(sqlite_path):
        print(f"  错误：文件不存在")
        return False

    sl_conn = sqlite3.connect(sqlite_path)
    sl_conn.row_factory = sqlite3.Row
    sl_cur = sl_conn.cursor()

    sl_cur.execute("SELECT COUNT(*) FROM records")
    total = sl_cur.fetchone()[0]
    print(f"  找到 {total} 条记录")

    sl_cur.execute("SELECT * FROM records ORDER BY id")
    rows = sl_cur.fetchall()

    # 2. 连接 PostgreSQL
    print(f"[2/4] 连接 PostgreSQL...")
    from sqlalchemy import create_engine, MetaData, Table, Column, Integer, Text, insert, text
    from sqlalchemy import event

    # 标准化 URL
    raw = pg_url.strip()
    if raw.startswith("postgres://"):
        raw = "postgresql+psycopg2://" + raw[len("postgres://"):]
    elif not raw.startswith("postgresql"):
        raw = "postgresql+psycopg2://" + raw

    engine = create_engine(raw, pool_pre_ping=True)

    # 3. 创建表结构
    print(f"[3/4] 创建表结构...")
    metadata = MetaData()

    records_tbl = Table(
        "records", metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("name", Text, nullable=False),
        Column("dept", Text, nullable=False),
        Column("empId", Text, nullable=False),
        Column("region", Text, nullable=False),
        Column("result", Text),
        Column("haming", Integer),
        Column("dims", Text),
        Column("answers", Text),
        Column("time", Text),
        Column("client_submit_id", Text),
    )

    metadata.create_all(engine)

    # 4. 批量插入
    print(f"[4/4] 开始迁移 {total} 条记录...")
    batch_size = 500
    inserted = 0

    with engine.begin() as conn:
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i+batch_size]
            values_list = []
            for row in batch:
                values_list.append({
                    "id": row["id"],
                    "name": row["name"],
                    "dept": row["dept"] or "",
                    "empId": row["empId"],
                    "region": row["region"] or "",
                    "result": row["result"] or "",
                    "haming": row["haming"] or 0,
                    "dims": row["dims"] or "[]",
                    "answers": row["answers"] or "{}",
                    "time": row["time"] or "",
                    "client_submit_id": row["client_submit_id"] if "client_submit_id" in row.keys() else None,
                })

            conn.execute(insert(records_tbl), values_list)
            inserted += len(batch)
            print(f"  进度: {inserted}/{total} ({inserted*100//total}%)")

    # 5. 重置序列
    with engine.begin() as conn:
        conn.execute(
            text("SELECT setval('records_id_seq', (SELECT MAX(id) FROM records))")
        )

    print(f"\n✅ 迁移完成！共迁移 {inserted} 条记录到 PostgreSQL")

    sl_conn.close()
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python migrate_to_pg.py <DATABASE_URL>")
        print("示例: python migrate_to_pg.py 'postgresql://user:pass@host:port/db'")
        sys.exit(1)

    pg_url = sys.argv[1]

    # SQLite 数据库路径（V4 部署目录，17,749 条记录）
    base_dir = os.path.dirname(os.path.abspath(__file__))
    sqlite_path = os.path.join(base_dir, "data.db")

    # 如果当前目录没有，尝试 V4 目录
    if not os.path.exists(sqlite_path):
        alt = os.path.join(os.path.dirname(base_dir), "CBTI_handbook_v4_latest_deploy", "data.db")
        if os.path.exists(alt):
            sqlite_path = alt

    migrate(sqlite_path, pg_url)

FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制全部代码
COPY . .

# 确保data.db目录可写
RUN chmod -R 777 /app

EXPOSE 8080

# gthread：多线程处理 I/O。生产请设置环境变量 DATABASE_URL 为 PostgreSQL 连接串（见 env.example），避免多实例下 SQLite 数据分裂
# 线程数与 worker 数可按 CPU/内存调整（示例面向 2k~3k 并发读与中等写入）
# SQLite 优化：1 worker × 64 threads + WriteBatch 批量写入
# 设置 DATABASE_URL=PostgreSQL 可切换至 PG 无损升级
CMD gunicorn --bind 0.0.0.0:8080 --worker-class gthread --workers 1 --threads 64 --timeout 60 --graceful-timeout 30 --keep-alive 5 app:app
#!/usr/bin/env python3
"""YashanDB 压测脚本：2并发写入10分钟"""
import yaspy
import threading
import time
import random
from datetime import datetime

HOST = "yas_oracle"
PORT = 1688
USER = "sys"
PASSWORD = "Cod-2022"

TEST_TABLE = "ZBX_TEST_DATA"
DURATION_SEC = 600  # 10分钟
CONCURRENCY = 2

insert_count = 0
error_count = 0
stop_flag = threading.Event()

def get_conn():
    return yaspy.connect(dsn=f"{HOST}:{PORT}", user=USER, password=PASSWORD)

def ts():
    return datetime.now().strftime("%H:%M:%S")

def setup():
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(f"DROP TABLE {TEST_TABLE} PURGE")
        conn.commit()
        print(f"[{ts()}] 旧表已删除")
    except:
        pass
    try:
        cur.execute(f"""CREATE TABLE {TEST_TABLE} (
            id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            metric_name VARCHAR2(128),
            metric_value NUMBER,
            tag VARCHAR2(64),
            ts TIMESTAMP DEFAULT SYSTIMESTAMP
        )""")
        conn.commit()
        print(f"[{ts()}] 表 {TEST_TABLE} 创建成功")
    except Exception as e:
        print(f"[{ts()}] 建表异常: {e}")
        conn.rollback()
    cur.close()
    conn.close()

def worker(wid):
    global insert_count, error_count
    conn = get_conn()
    cur = conn.cursor()
    metrics = [
        'transaction_count','query_count','cache_hit_ratio',
        'disk_reads','disk_writes','cpu_usage',
        'memory_usage','session_count','lock_count',
        'buffer_size','redo_size','connection_pool'
    ]
    tags = ['worker1','worker2','batch','oltp','report']
    base_vals = [(m, random.uniform(1, 1000), t)
                 for m in metrics for t in tags]
    total = 0
    while not stop_flag.is_set():
        try:
            vals = [(m, v + random.uniform(-50, 50), t)
                    for m, v, t in base_vals]
            cur.executemany(
                f"INSERT INTO {TEST_TABLE} (metric_name, metric_value, tag) VALUES (:1, :2, :3)",
                vals
            )
            conn.commit()
            n = len(vals)
            total += n
            insert_count += n
            if total % 6000 == 0:
                print(f"[{ts()}] Worker-{wid}: {total} 条")
        except Exception as e:
            error_count += 1
            if error_count <= 3:
                print(f"[{ts()}] W-{wid} ERR: {e}")
            conn.rollback()
            time.sleep(0.5)
    cur.close()
    conn.close()
    print(f"[{ts()}] Worker-{wid} 完成，插入 {total} 条")

def run():
    global insert_count, error_count
    insert_count = 0
    error_count = 0
    print(f"[{ts()}] 启动 {CONCURRENCY} 并发，持续 {DURATION_SEC}s...")
    threads = [threading.Thread(target=worker, args=(i+1,)) for i in range(CONCURRENCY)]
    for t in threads:
        t.start()
    time.sleep(DURATION_SEC)
    stop_flag.set()
    for t in threads:
        t.join()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM {TEST_TABLE}")
    total = cur.fetchone()[0]
    print(f"\n[{ts()}] ===== 完成 =====")
    print(f"本次插入: {insert_count} 条, 错误: {error_count} 次, 表总计: {total} 条")
    cur.close()
    conn.close()

if __name__ == "__main__":
    setup()
    run()

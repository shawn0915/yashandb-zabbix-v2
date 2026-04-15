#!/usr/bin/env python3
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

def get_conn():
    return yaspy.connect(dsn="%s:%s" % (HOST, PORT), user=USER, password=PASSWORD)

def ts():
    return datetime.now().strftime("%H:%M:%S")

# 1. Test connection
print("[%s] Testing connection..." % ts())
conn = get_conn()
cur = conn.cursor()
cur.execute("SELECT banner FROM v$version WHERE ROWNUM=1")
print("[%s] DB: %s" % (ts(), cur.fetchone()[0]))
cur.close()
conn.close()

# 2. Setup table
print("[%s] Setting up table..." % ts())
conn = get_conn()
cur = conn.cursor()
try:
    cur.execute("DROP TABLE %s PURGE" % TEST_TABLE)
    conn.commit()
    print("[%s] old table dropped" % ts())
except:
    pass
cur.execute("""CREATE TABLE %s (
    id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    metric_name VARCHAR2(128),
    metric_value NUMBER,
    tag VARCHAR2(64),
    ts TIMESTAMP DEFAULT SYSTIMESTAMP
)""" % TEST_TABLE)
conn.commit()
print("[%s] table %s created" % (ts(), TEST_TABLE))
cur.close()
conn.close()

# 3. Quick insert test
print("[%s] Quick insert test (10s, 2 workers)..." % ts())
insert_count = [0]
stop_flag = threading.Event()

def quick_worker(wid):
    conn = get_conn()
    cur = conn.cursor()
    metrics = ['tx_count','qps','cache_hit','disk_r','disk_w','cpu',
               'mem','sessions','locks','buf','redo','pool']
    tags = ['w1','w2','batch','oltp','rpt']
    base = [(m, random.uniform(1,500), t) for m in metrics for t in tags]
    total = 0
    while not stop_flag.is_set():
        vals = [(m, v+random.uniform(-30,30), t) for m,v,t in base]
        cur.executemany(
            "INSERT INTO %s (metric_name,metric_value,tag) VALUES (:1,:2,:3)" % TEST_TABLE,
            vals)
        conn.commit()
        total += len(vals)
        insert_count[0] += len(vals)
    cur.close()
    conn.close()
    print("[%s] Worker-%s done: %s rows" % (ts(), wid, total))

threads = [threading.Thread(target=quick_worker, args=(i+1,)) for i in range(2)]
for t in threads: t.start()
time.sleep(10)
stop_flag.set()
for t in threads: t.join()

conn = get_conn()
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM %s" % TEST_TABLE)
total = cur.fetchone()[0]
print("\n[%s] ===== QUICK TEST DONE =====" % ts())
print("Inserted this run: %s, total rows: %s" % (insert_count[0], total))
cur.close()
conn.close()

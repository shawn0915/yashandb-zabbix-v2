#!/usr/bin/env python3
import yaspy, os
os.environ['LD_LIBRARY_PATH']='/opt/yashandb/yashandb_yasdb_home/lib'
conn = yaspy.connect(dsn='yas_oracle:1688', user='sys', password='Cod-2022')
cur = conn.cursor()

# 搜索 'free buffer' 相关
print("=== free buffer ===")
cur.execute("SELECT NAME, VALUE FROM V$SYSSTAT WHERE NAME LIKE '%free buffer%'")
for r in cur.fetchall(): print(f"  '{r[0]}': {r[1]}")
if cur.rowcount == 0: print("  (无)")

# 搜索 'physical' 相关
print("\n=== physical ===")
cur.execute("SELECT NAME, VALUE FROM V$SYSSTAT WHERE NAME LIKE '%physical%' OR NAME LIKE '%PHYSICAL%'")
for r in cur.fetchall(): print(f"  '{r[0]}': {r[1]}")
if cur.rowcount == 0: print("  (无)")

# 搜索 'user calls'
print("\n=== user calls ===")
cur.execute("SELECT NAME, VALUE FROM V$SYSSTAT WHERE NAME LIKE '%user call%' OR NAME LIKE '%USER CALL%'")
for r in cur.fetchall(): print(f"  '{r[0]}': {r[1]}")
if cur.rowcount == 0: print("  (无)")

# 搜索 redo space
print("\n=== redo space ===")
cur.execute("SELECT NAME, VALUE FROM V$SYSSTAT WHERE NAME LIKE '%redo%' OR NAME LIKE '%REDO%'")
for r in cur.fetchall(): print(f"  '{r[0]}': {r[1]}")
if cur.rowcount == 0: print("  (无)")

# 测试所有当前 monitor.py 中的小写查询
print("\n=== 测试 monitor.py 中现有小写查询 ===")
tests = [
    ("SELECT VALUE FROM V$SYSSTAT WHERE NAME='physical reads'", "physical reads (小写)"),
    ("SELECT VALUE FROM V$SYSSTAT WHERE NAME='PHYSICAL READS'", "PHYSICAL READS (大写)"),
    ("SELECT VALUE FROM V$SYSSTAT WHERE NAME='user calls'", "user calls (小写)"),
    ("SELECT VALUE FROM V$SYSSTAT WHERE NAME='USER CALLS'", "USER CALLS (大写)"),
    ("SELECT VALUE FROM V$SYSSTAT WHERE NAME='free buffer inspected'", "free buffer inspected (小写)"),
    ("SELECT VALUE FROM V$SYSSTAT WHERE NAME='REDO ENTRIES'", "REDO ENTRIES (大写)"),
    ("SELECT VALUE FROM V$SYSSTAT WHERE NAME='REDO LOG SPACE REQUESTS'", "REDO LOG SPACE REQUESTS (大写)"),
]
for sql, label in tests:
    try:
        cur.execute(sql)
        r = cur.fetchone()
        print(f"  {label}: {r[0] if r else 'None'}")
    except Exception as e:
        print(f"  {label}: ERROR - {str(e)[:50]}")

cur.close()
conn.close()

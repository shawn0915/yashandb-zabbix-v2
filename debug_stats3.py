#!/usr/bin/env python3
import yaspy, os
os.environ['LD_LIBRARY_PATH']='/opt/yashandb/yashandb_yasdb_home/lib'
conn = yaspy.connect(dsn='yas_oracle:1688', user='sys', password='Cod-2022')
cur = conn.cursor()

# 搜索 execute 相关的统计项
print("=== execute 相关 ===")
cur.execute("SELECT NAME, VALUE FROM V$SYSSTAT WHERE NAME LIKE '%execute%' OR NAME LIKE '%EXECUTE%'")
for r in cur.fetchall(): print(f"  '{r[0]}': {r[1]}")
if cur.rowcount == 0: print("  (无)")

# 搜索 buffer gets / user calls
print("\n=== buffer / user calls 相关 ===")
cur.execute("SELECT NAME, VALUE FROM V$SYSSTAT WHERE NAME LIKE '%buffer%' OR NAME LIKE '%BUFFER%'")
for r in cur.fetchall(): print(f"  '{r[0]}': {r[1]}")

# V$PARAMETER processes / sessions
print("\n=== processes/sessions 参数 ===")
cur.execute("SELECT NAME, VALUE FROM V$PARAMETER WHERE NAME IN ('processes','sessions')")
for r in cur.fetchall(): print(f"  '{r[0]}': {r[1]}")

# 现有 monitor.py 中用的 SQL 测试
print("\n=== monitor.py 中现有 SQL 测试 ===")
tests = [
    ("SELECT VALUE FROM V$SYSSTAT WHERE NAME='execute count'", "execute count"),
    ("SELECT VALUE FROM V$SYSSTAT WHERE NAME='execute count (total)'", "execute count (total)"),
    ("SELECT VALUE FROM V$SYSSTAT WHERE NAME='EXECUTE COUNT'", "EXECUTE COUNT"),
    ("SELECT VALUE FROM V$SYSSTAT WHERE NAME LIKE '%execute%'", "LIKE %execute%"),
    ("SELECT VALUE FROM V$SYSSTAT WHERE NAME='commits'", "commits"),
]
for sql, label in tests:
    try:
        cur.execute(sql)
        r = cur.fetchone()
        print(f"  {label}: {r[0] if r else 'None'}")
    except Exception as e:
        print(f"  {label}: ERROR - {e}")

cur.close()
conn.close()

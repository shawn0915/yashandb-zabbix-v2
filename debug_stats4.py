#!/usr/bin/env python3
import yaspy, os
os.environ['LD_LIBRARY_PATH']='/opt/yashandb/yashandb_yasdb_home/lib'
conn = yaspy.connect(dsn='yas_oracle:1688', user='sys', password='Cod-2022')
cur = conn.cursor()

# 搜索 processes / sessions 相关参数
print("=== processes/sessions 参数 ===")
cur.execute("SELECT NAME, VALUE FROM V$PARAMETER WHERE NAME LIKE '%process%' OR NAME LIKE '%session%' OR NAME LIKE '%PROCESS%' OR NAME LIKE '%SESSION%'")
for r in cur.fetchall(): print(f"  '{r[0]}': {r[1]}")
print(f"  Total rows: {cur.rowcount}")

# 测试 V$SESSION_COUNT
print("\n=== V$SESSION 检测 ===")
cur.execute("SELECT COUNT(*) FROM V$SESSION")
r = cur.fetchone()
print(f"  V$SESSION COUNT: {r[0]}")
cur.execute("SELECT COUNT(*) FROM V$PROCESS")
r = cur.fetchone()
print(f"  V$PROCESS COUNT: {r[0]}")

# 测试现有 SQL 大小写问题
print("\n=== 大小写测试 ===")
tests = [
    ("SELECT VALUE FROM V$SYSSTAT WHERE NAME='COMMITS'", "COMMITS"),
    ("SELECT VALUE FROM V$SYSSTAT WHERE NAME='execute count'", "execute count (小写)"),
    ("SELECT VALUE FROM V$SYSSTAT WHERE NAME='EXECUTE COUNT'", "EXECUTE COUNT (大写)"),
    ("SELECT VALUE FROM V$SYSSTAT WHERE NAME='PARSE COUNT (HARD)'", "PARSE COUNT (HARD) (大写)"),
    ("SELECT VALUE FROM V$SYSSTAT WHERE NAME='parse count (hard)'", "parse count (hard) (小写)"),
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

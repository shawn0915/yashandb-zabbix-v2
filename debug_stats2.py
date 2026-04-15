#!/usr/bin/env python3
import yaspy, os
os.environ['LD_LIBRARY_PATH']='/opt/yashandb/yashandb_yasdb_home/lib'
conn = yaspy.connect(dsn='yas_oracle:1688', user='sys', password='Cod-2022')
cur = conn.cursor()

# 列出所有 V$SYSSTAT 名称
print("=== 所有 V$SYSSTAT ===")
cur.execute("SELECT NAME, VALUE FROM V$SYSSTAT ORDER BY NAME")
for r in cur.fetchall(): print(f"  {r[0]}: {r[1]}")

print(f"\n总计: {cur.rowcount} rows")

cur.close()

# 单独检查 V$PARAMETER
cur2 = conn.cursor()
print("\n=== 所有 V$PARAMETER ===")
cur2.execute("SELECT NAME, VALUE FROM V$PARAMETER ORDER BY NAME")
for r in cur2.fetchall(): print(f"  {r[0]}: {r[1]}")
print(f"\n总计: {cur2.rowcount} rows")

cur2.close()
conn.close()

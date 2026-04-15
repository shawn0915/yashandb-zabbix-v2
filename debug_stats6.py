#!/usr/bin/env python3
import yaspy, os
os.environ['LD_LIBRARY_PATH']='/opt/yashandb/yashandb_yasdb_home/lib'
conn = yaspy.connect(dsn='yas_oracle:1688', user='sys', password='Cod-2022')
cur = conn.cursor()

# 测试不同大小写
tests = [
    ("SELECT VALUE FROM V$PARAMETER WHERE NAME='statistics_level'", "小写 statistics_level"),
    ("SELECT VALUE FROM V$PARAMETER WHERE NAME='STATISTICS_LEVEL'", "大写 STATISTICS_LEVEL"),
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

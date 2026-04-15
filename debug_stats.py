#!/usr/bin/env python3
import yaspy, os
os.environ['LD_LIBRARY_PATH']='/opt/yashandb/yashandb_yasdb_home/lib'
conn = yaspy.connect(dsn='yas_oracle:1688', user='sys', password='Cod-2022')
cur = conn.cursor()

# 查找 execute/commits/query/transaction 相关统计项
print("=== V$SYSSTAT 相关统计项 ===")
cur.execute("SELECT NAME, VALUE FROM V$SYSSTAT WHERE NAME LIKE '%execute%' OR NAME LIKE '%commit%' OR NAME LIKE '%transact%' OR NAME LIKE '%query%'")
for r in cur.fetchall(): print(f"  {r}")

# 检查 V$PARAMETER 中的相关参数
print("\n=== V$PARAMETER 资源限制相关 ===")
cur.execute("SELECT NAME, VALUE FROM V$PARAMETER WHERE NAME IN ('processes','sessions','resource_limit')")
for r in cur.fetchall(): print(f"  {r}")

# 检查 DBA_TEMP_FREE_SPACE 结构
print("\n=== DBA_TEMP_FREE_SPACE 详情 ===")
cur.execute("SELECT TABLESPACE_NAME, TABLESPACE_SIZE, ALLOCATED_SPACE, FREE_SPACE FROM DBA_TEMP_FREE_SPACE")
for r in cur.fetchall(): print(f"  {r}")

# 检查 STATISTICS_LEVEL 参数名
print("\n=== 模糊搜索 STATISTICS ===")
cur.execute("SELECT NAME, VALUE FROM V$PARAMETER WHERE NAME LIKE '%statistic%'")
for r in cur.fetchall(): print(f"  {r}")

cur.close()
conn.close()

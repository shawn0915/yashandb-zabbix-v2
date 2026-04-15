#!/usr/bin/env python3
"""最终验证 yas_zabbix v2.5 新增指标"""
import sys, os
os.environ['LD_LIBRARY_PATH'] = '/opt/yashandb/yashandb_yasdb_home/lib'
import yaspy

conn = yaspy.connect(dsn="yas_oracle:1688", user="sys", password="Cod-2022")

def q(sql, label):
    cur = conn.cursor()
    try:
        cur.execute(sql)
        row = cur.fetchone()
        val = row[0] if row else None
        status = "OK" if val is not None else "EMPTY"
        print(f"  [{status:6s}] {label}: {val}")
        return val
    except Exception as e:
        print(f"  [ERROR ] {label}: {str(e)[:60]}")
        return None
    finally:
        cur.close()

passed, failed, total = 0, 0, 0

def check(label, val):
    global passed, failed, total
    total += 1
    if val is not None:
        passed += 1
    else:
        failed += 1

print("==========================================")
print("Phase 1 新指标验证")
print("==========================================")

print("\n[QPS/TPS]")
r = q("SELECT VALUE FROM V$SYSSTAT WHERE NAME='EXECUTE COUNT'", "db.qps (EXECUTE COUNT)")
check("db.qps", r)
r = q("SELECT VALUE FROM V$SYSSTAT WHERE NAME='COMMITS'", "db.tps (COMMITS)")
check("db.tps", r)

print("\n[当天归档数]")
r = q("SELECT COUNT(*) FROM V$ARCHIVED_LOG WHERE FIRST_TIME >= TRUNC(SYSDATE)", "archived_log.count_today")
check("archived_log.count_today", r)

print("\n[等待类分组]")
r = q("SELECT COUNT(*) FROM V$SYSTEM_WAIT_CLASS", "wait_class.discovery (count)")
check("wait_class.discovery", r)
r = q("SELECT TOTAL_WAITS FROM V$SYSTEM_WAIT_CLASS WHERE WAIT_CLASS='Application'", "wait_class.count[Application]")
check("wait_class.count[Application]", r)
r = q("SELECT TIME_WAITED FROM V$SYSTEM_WAIT_CLASS WHERE WAIT_CLASS='Application'", "wait_class.time[Application]")
check("wait_class.time[Application]", r)

print("\n[按类型表空间]")
r = q("SELECT NVL(SUM(d.BYTES),0) FROM DBA_DATA_FILES d JOIN DBA_TABLESPACES t ON d.TABLESPACE_NAME=t.TABLESPACE_NAME WHERE t.CONTENTS='PERMANENT'", "tablespace.by_type[PERMANENT]")
check("tablespace.by_type[PERMANENT]", r)
r = q("SELECT NVL(SUM(d.BYTES),0) FROM DBA_DATA_FILES d JOIN DBA_TABLESPACES t ON d.TABLESPACE_NAME=t.TABLESPACE_NAME WHERE t.CONTENTS='UNDO'", "tablespace.by_type[UNDO]")
check("tablespace.by_type[UNDO]", r)
r = q("SELECT NVL(SUM(d.BYTES),0) FROM DBA_DATA_FILES d JOIN DBA_TABLESPACES t ON d.TABLESPACE_NAME=t.TABLESPACE_NAME WHERE t.CONTENTS='TEMPORARY'", "tablespace.by_type[TEMPORARY]")
check("tablespace.by_type[TEMPORARY]", r)

print("\n[Temp/Undo 独立指标]")
r = q("SELECT ROUND(GREATEST((SUM(ALLOCATED_SPACE)-SUM(FREE_SPACE))*100.0/NULLIF(SUM(TABLESPACE_SIZE),0),0),2) FROM DBA_TEMP_FREE_SPACE", "tablespace.temp_usage_pct")
check("tablespace.temp_usage_pct", r)
r = q("SELECT ROUND((SUM(d.BYTES)-NVL(SUM(f.BYTES),0))*100.0/NULLIF(SUM(d.BYTES),0),2) FROM DBA_DATA_FILES d JOIN DBA_TABLESPACES t ON d.TABLESPACE_NAME=t.TABLESPACE_NAME LEFT JOIN DBA_FREE_SPACE f ON d.TABLESPACE_NAME=f.TABLESPACE_NAME WHERE t.CONTENTS='UNDO'", "tablespace.undo_usage_pct")
check("tablespace.undo_usage_pct", r)

print("\n[Top SQL 多维度]")
r = q("SELECT SQL_ID FROM V$SQLAREA ORDER BY BUFFER_GETS DESC FETCH FIRST 1 ROWS ONLY", "sql.top_buffer_gets_sql")
check("sql.top_buffer_gets_sql", r)
r = q("SELECT SQL_ID FROM V$SQLAREA ORDER BY DISK_READS DESC FETCH FIRST 1 ROWS ONLY", "sql.top_disk_reads_sql")
check("sql.top_disk_reads_sql", r)
r = q("SELECT SQL_ID FROM V$SQLAREA ORDER BY EXECUTIONS DESC FETCH FIRST 1 ROWS ONLY", "sql.top_executions_sql")
check("sql.top_executions_sql", r)

print("\n[资源限制使用率]")
try:
    sql = """
        SELECT ROUND(GREATEST(
            (SELECT COUNT(*) * 100.0 / NULLIF(TO_NUMBER(
                (SELECT VALUE FROM V$PARAMETER WHERE NAME='MAX_SESSIONS')), 0)
             FROM V$SESSION),
            (SELECT COUNT(*) * 100.0 / NULLIF(TO_NUMBER(
                (SELECT VALUE FROM V$PARAMETER WHERE NAME='MAX_SESSIONS')), 0)
             FROM V$PROCESS)
        ), 2)
        FROM DUAL
    """
    r = q(sql, "resource_limit.usage_pct")
    check("resource_limit.usage_pct", r)
except Exception as e:
    print(f"  [ERROR ] resource_limit.usage_pct: {e}")

print("\n==========================================")
print("Phase 2 新指标验证")
print("==========================================")

print("\n[P95/P99 延迟]")
r = q("SELECT ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY ELAPSED_TIME)/1000,2) FROM V$SQL WHERE EXECUTIONS>0 AND ELAPSED_TIME>0", "sql.p95_elapsed_ms")
check("sql.p95_elapsed_ms", r)
r = q("SELECT ROUND(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY ELAPSED_TIME)/1000,2) FROM V$SQL WHERE EXECUTIONS>0 AND ELAPSED_TIME>0", "sql.p99_elapsed_ms")
check("sql.p99_elapsed_ms", r)

print("\n[会话分布 LLD]")
r = q("SELECT COUNT(DISTINCT NVL(USERNAME,'(NULL)')) FROM V$SESSION WHERE TYPE='USER'", "session.user.discovery (count)")
check("session.user.discovery", r)
r = q("SELECT COUNT(*) FROM V$SESSION WHERE TYPE='USER' AND USERNAME='SYS'", "session.by_user[SYS]")
check("session.by_user[SYS]", r)

print("\n[INVALID 对象分类]")
r = q("SELECT COUNT(*) FROM DBA_OBJECTS WHERE STATUS='INVALID' AND OBJECT_TYPE='PROCEDURE'", "invalid_objects.by_type[PROCEDURE]")
check("invalid_objects.by_type[PROCEDURE]", r)
r = q("SELECT COUNT(*) FROM DBA_OBJECTS WHERE STATUS='INVALID' AND OBJECT_TYPE='UDF'", "invalid_objects.by_type[UDF]")
check("invalid_objects.by_type[UDF]", r)

print("\n[数据文件非自动扩展]")
r = q("SELECT COUNT(*) FROM DBA_DATA_FILES WHERE AUTOEXTENSIBLE='NO'", "datafile.non_autoextend_count")
check("datafile.non_autoextend_count", r)

print("\n[密码即将过期]")
r = q("SELECT COUNT(*) FROM DBA_USERS WHERE EXPIRY_DATE IS NOT NULL AND EXPIRY_DATE<=TRUNC(SYSDATE)+7 AND ACCOUNT_STATUS NOT IN ('EXPIRED','LOCKED')", "user.expiring_soon_count")
check("user.expiring_soon_count", r)

print("\n[STATISTICS_LEVEL]")
r = q("SELECT VALUE FROM V$PARAMETER WHERE NAME='statistics_level'", "db.statistics_level")
check("db.statistics_level", r)

conn.close()
print("\n==========================================")
print(f"验证完成: {passed}/{total} 通过, {failed} 失败")
print("==========================================")

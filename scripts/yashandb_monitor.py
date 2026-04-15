#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YashanDB Zabbix Monitor Plugin
Version: 2.5.0
Compatible: YashanDB 23.4 LTS + Zabbix 7.4.x

支持两套指标命名空间：
  - yashandb.db.*         原生指标（兼容 v1.0 模板）
  - yashandb.*            Datadog Oracle 兼容指标

v2.4 新增 Phase 1 指标（商业产品对比 gap 补全）：
  - qps / tps                   每秒查询数/事务数（V$SYSSTAT delta）
  - archived_log.count_today    当天归档日志数量（V$ARCHIVED_LOG 按日期过滤）
  - wait_class.*                等待事件按等待类分组（V$SYSTEM_WAIT_CLASS）
  - tablespace.by_type          按类型分类的表空间（PERMANENT/TEMPORARY/UNDO）
  - tablespace.temp_usage_pct   临时表空间使用率（%）
  - tablespace.undo_usage_pct   Undo 表空间使用率（%）
  - sql.top_buffer_gets / disk_reads / executions  Top SQL 多维度（V$SQLAREA）
  - resource_limit_usage_pct    资源限制使用率%（V$PARAMETER+V$PROCESS/V$SESSION 替代 V$RESOURCE_LIMIT）

v2.5 新增 Phase 2 指标：
  - sql.p95_elapsed_ms / p99_elapsed_ms  慢查询 P95/P99 延迟（PERCENTILE_CONT）
  - session.by_user / by_program          按用户/程序的会话分布（V$SESSION）
  - invalid_objects.by_type               无效对象按类型统计（DBA_OBJECTS）
  - datafile.non_autoextend_count         禁用了自动扩展的数据文件数量
  - user.expiring_soon                   密码即将过期的账户数（7天内）
  - parameter.statistics_level            STATISTICS_LEVEL 参数值（告警用）

不适用的指标（已明确标记 N/A）：
  - V$RESOURCE_LIMIT              — 不存在，改用 V$PARAMETER+V$PROCESS 估算
  - DBA_UNDO_EXTENTS              — 不存在，改用 V$TRANSACTION
  - DBA_TABLES.CHAIN_CNT         — 不存在该列
  - V$WAITCLASSMETRIC             — 不存在，使用 V$SYSTEM_WAIT_CLASS 替代
  - V$LIBRARYCACHE / V$ROWCACHE  — 不存在（v2.2 已标记）

用法:
    python yashandb_monitor.py --host <host> --port <port>
        --user <user> --password <password> --metric <metric_key>

示例:
    python yashandb_monitor.py --host 127.0.0.1 --port 1688 \
        --user sys --password yasdb_123 --metric yashandb.db.status

指标命名空间说明:
    yashandb.db.*         原生指标（原 v1.0），部分已映射到 Datadog 同名指标
    yashandb.active_background     活跃后台会话数
    yashandb.buffer_cachehit_ratio  缓冲区缓存命中率(%)
    yashandb.process.pga_*         PGA 进程内存统计
    yashandb.tablespace.in_use      表空间使用率(%)（Datadog版）
    ... 共 42 个 Datadog 兼容指标（详见 --help）
"""

import argparse
import json
import sys
import os
import traceback

# -------------------------------------------------------
# 尝试导入 yaspy（YashanDB 官方 Python 驱动）
# -------------------------------------------------------
try:
    import yaspy
    DRIVER = "yaspy"
except ImportError:
    yaspy = None
    DRIVER = None


# -------------------------------------------------------
# 支持的监控指标定义（两套命名空间）
# -------------------------------------------------------
METRIC_HELP = """
支持的 metric_key 列表：

【原生指标 — yashandb.db.*（v1.0 兼容）】
  yashandb.db.status              数据库实例状态（1=正常, 0=异常）
  yashandb.db.version             数据库版本号
  yashandb.db.uptime              数据库启动时长（秒）
  yashandb.db.mode                数据库运行模式（PRIMARY/STANDBY）
  yashandb.db.sessions.active     活跃会话数
  yashandb.db.sessions.total      当前总会话数
  yashandb.db.sessions.waiting    当前等待中的会话数
  yashandb.db.sessions.max        最大会话数限制
  yashandb.db.memory.buffer_pool_size    Buffer Pool 总大小（字节）
  yashandb.db.memory.buffer_pool_used    Buffer Pool 已使用大小（字节）
  yashandb.db.memory.buffer_pool_hit     Buffer Pool 命中率（%）
  yashandb.db.memory.vm_pool_size        VM Pool 总大小（字节）
  yashandb.db.memory.vm_pool_used        VM Pool 已使用大小（字节）
  yashandb.db.tablespace.discovery       表空间自动发现（JSON，用于 LLD）
  yashandb.db.tablespace.total[{#TS}]    指定表空间总大小（字节）
  yashandb.db.tablespace.used[{#TS}]    指定表空间已使用（字节）
  yashandb.db.tablespace.free[{#TS}]    指定表空间剩余（字节）
  yashandb.db.tablespace.pct_used[{#TS}] 指定表空间使用率（%）
  yashandb.db.redo.flush_speed           Redo 刷盘速度（字节/秒）
  yashandb.db.redo.free_space            Redo 空闲空间（字节）
  yashandb.db.redo.checkpoint_lag         检查点落后量
  yashandb.db.sql.executions_per_sec     每秒 SQL 执行次数
  yashandb.db.sql.avg_elapsed_ms         SQL 平均执行时长（ms）
  yashandb.db.sql.slow_count             慢 SQL 数量（>1s）
  yashandb.db.sql.parse_count            SQL 解析次数（PARSE COUNT (HARD)）
  yashandb.db.wait.top_event             当前 TOP 等待事件名称
  yashandb.db.wait.total_waits           总等待次数
  yashandb.db.wait.time_waited_ms        总等待时间（ms）
  yashandb.db.lock.count                 当前锁数量
  yashandb.db.lock.blocking_sessions     阻塞中的会话数
  yashandb.db.stat[<stat_name>]          从 V_$SYSSTAT 查询指定统计项的值
                                    示例: yashandb.db.stat[physical reads]

【会话与连接 — yashandb.*（Datadog Oracle 兼容）】
  yashandb.active_background         活跃后台会话数（V_$SESSION）
  yashandb.active_sessions           活跃会话总数（V_$SESSION，STATUS='ACTIVE'）
  yashandb.process_limit             进程限制使用率（%）- 已兼容
  yashandb.session_count             会话总数（V_$SESSION）
  yashandb.session_limit_usage       会话限制使用率（%）- 已兼容
  yashandb.user_sessions             用户会话数（V_$SESSION WHERE TYPE='USER'）

【SQL 解析与执行】
  yashandb.hard_parses               硬解析次数（PARSE COUNT (HARD)）
  yashandb.memory_sorts_ratio         内存排序比率（%）

【缓存与内存】
  yashandb.buffer_cachehit_ratio     缓冲区缓存命中率（%）
  yashandb.cache_blocks_lost         丢失的缓存块数（LOST WRITE DETECTED）
  yashandb.physical_memory_gb         物理内存大小（GB，V_$OSSTAT）
  yashandb.shared_memory_size        共享内存大小（字节，V_$SGA）
  yashandb.shared_pool_free          共享池空闲内存百分比（%，V_$SGASTAT）

【PGA 进程内存】
  yashandb.process.pga_allocated_memory  进程 PGA 分配内存（字节）
  yashandb.process.pga_freeable_memory  进程 PGA 可释放内存（字节）
  yashandb.process.pga_max_memory       进程当前最大 PGA 内存（字节）
  yashandb.process.pga_used_memory       进程 PGA 已用内存（字节）

【物理 I/O】
  yashandb.physical_reads            每秒物理读取次数（DISK READS）
  yashandb.physical_writes           每秒物理写入次数（DISK WRITES）

【逻辑读取】
  yashandb.consistent_read_changes   每秒一致性读变更次数（CONSISTENT CHANGES）
  yashandb.db_block_changes          每秒数据库块变更数（BLOCK CHANGES）
  yashandb.logical_reads             每秒逻辑读取次数（DB BLOCK GETS + CONSISTENT GETS）

【排序与扫描】
  yashandb.disk_sorts                每秒磁盘排序次数（SORTS (DISK)）
  yashandb.sorts_per_user_call       每次用户调用的排序次数

【Redo 日志】
  yashandb.redo_allocation_hit_ratio Redo 空间分配命中率（%）
  yashandb.redo_generated             每秒生成 Redo 字节数（REDO SIZE）
  yashandb.redo_writes               每秒 Redo 写入次数（REDO WRITES）

【事务】
  yashandb.dbwr_checkpoints          DBWR 检查点完成数（CHECKPOINTS COMPLETED）
  yashandb.user_commits              每秒用户提交次数（COMMITS）
  yashandb.user_rollbacks            用户回滚次数（ROLLBACKS）

【CPU 与系统资源】
  yashandb.host_cpu_utilization      主机 CPU 利用率（%，V_$OSSTAT）
  yashandb.num_cpus                  CPU 核心数（V_$OSSTAT）
  yashandb.os_load                   操作系统负载（V_$OSSTAT LOAD）

【网络与延迟】
  yashandb.avg_synchronous_single_block_read_latency  平均同步单块读延迟（ms）
  yashandb.network_traffic_volume    每秒网络流量（字节）

【索引】
  yashandb.branch_node_splits        每秒分支节点分裂次数（INDEX BRANCH SPLIT）
  yashandb.leaf_node_splits          每秒叶节点分裂次数（INDEX LEAF SPLIT）

【表空间（Datadog 版，支持 LLD）— yashandb.tablespace.*】
  yashandb.tablespace.discovery      表空间自动发现（JSON，用于 LLD）
  yashandb.tablespace.in_use         表空间使用率（%，全库汇总）
  yashandb.tablespace.maxsize        表空间最大容量（字节）
  yashandb.tablespace.offline        离线表空间数量
  yashandb.tablespace.size           表空间当前总大小（字节）
  yashandb.tablespace.used           表空间已使用字节数
  yashandb.tablespace.total[{#TS}]  指定表空间总大小（字节）
  yashandb.tablespace.free[{#TS}]   指定表空间剩余空间（字节）
  yashandb.tablespace.pct_used[{#TS}] 指定表空间使用率（%）

【全局缓存 RAC（单机 = 0）】
  yashandb.gc_average_cr_get_time    全局缓存平均 CR 获取时间（ms）
  yashandb.gc_average_current_get_time 全局缓存平均 current 块获取时间（ms）

【长事务与高可用（v2.1 新增，来源：YCM 监控指标，实机验证）】
  yashandb.db.long_transactions      超过3分钟活跃事务数（V$TRANSACTION.SID JOIN V$SESSION.SID；START_DATE）
  yashandb.db.ha.sync_delay          主备同步延迟（gap数量，V$ARCHIVE_GAP；V$STANDBY_LOG不存在；单机=0）
  yashandb.db.redo.log_switches      Redo 日志组切换次数（V$ARCHIVED_LOG，近24小时；V$LOG/V$LOG_HISTORY不存在）

【不支持的指标（YashanDB 无对应功能）— N/A】
  yashandb.active_background_on_cpu  N/A — V_$SESSION 无 STATE 列
  yashandb.active_sessions_on_cpu    N/A — V_$SESSION 无 STATE 列
  yashandb.logons                    N/A — YashanDB 无 LOGONS 统计项
  yashandb.session.inactive_seconds  N/A — V_$SESSION 无 LAST_CALL_ET 列
  yashandb.execute_without_parse     N/A — YashanDB 无 PARSE COUNT (TOTAL)
  yashandb.parse_failures            N/A — YashanDB 无此统计项
  yashandb.soft_parse_ratio          N/A — YashanDB 无 PARSE COUNT (TOTAL)
  yashandb.total_parse_count         N/A — YashanDB 无 PARSE COUNT (TOTAL)
  yashandb.cache_blocks_corrupt      N/A — V_$DATABASE_BLOCK_CORRUPTION 不存在
  yashandb.library_cachehit_ratio   库缓存命中率（%，v2.4 改为共享池估算）
  yashandb.pga_cache_hit             N/A — V_$PGASTAT 不存在
  yashandb.row_cache_hit_ratio       N/A — V_$ROWCACHE 不存在
  yashandb.process.pga_maximum_memory N/A — V_$PGASTAT 不存在
  yashandb.physical_read_bytes       N/A — YashanDB 无此统计项
  yashandb.physical_read_io_requests N/A — YashanDB 无此统计项
  yashandb.physical_read_total_bytes N/A — YashanDB 无此统计项
  yashandb.physical_read_total_io_requests N/A — YashanDB 无此统计项
  yashandb.physical_reads_direct     N/A — YashanDB 无此统计项
  yashandb.physical_reads_direct_lobs N/A — YashanDB 无此统计项
  yashandb.physical_write_bytes      N/A — YashanDB 无此统计项
  yashandb.physical_write_io_requests N/A — YashanDB 无此统计项
  yashandb.physical_write_total_bytes N/A — YashanDB 无此统计项
  yashandb.physical_write_total_io_requests N/A — YashanDB 无此统计项
  yashandb.physical_writes_direct    N/A — YashanDB 无此统计项
  yashandb.physical_writes_direct_lobs N/A — YashanDB 无此统计项
  yashandb.consistent_read_gets      N/A — YashanDB V_$SYSSTAT 无 CONSISTENT GETS
  yashandb.db_block_gets             N/A — YashanDB V_$SYSSTAT 无 DB BLOCK GETS
  yashandb.long_table_scans          N/A — YashanDB 无此统计项
  yashandb.rows_per_sort             N/A — YashanDB 无 SORTS (ROWS) 统计项
  yashandb.enqueue_deadlocks         N/A — YashanDB 无此统计项
  yashandb.enqueue_timeouts          N/A — YashanDB 无此统计项
  yashandb.database_cpu_time_ratio   N/A — V_$SYS_TIME_MODEL 不存在
  yashandb.database_wait_time_ratio  N/A — V_$SYS_TIME_MODEL 不存在
  yashandb.service_response_time     N/A — V_$SYS_TIME_MODEL 不存在
  yashandb.temp_space_used           N/A — V_$TEMP_SPACE_HEADER 不存在
  yashandb.asm_diskgroup.free_mb     N/A — YashanDB 无 ASM 功能
  yashandb.asm_diskgroup.offline_disks N/A — YashanDB 无 ASM 功能
  yashandb.asm_diskgroup.total_mb    N/A — YashanDB 无 ASM 功能
  yashandb.data_guard.apply_lag      N/A — V_$DATAGUARD_STATS 不存在
  yashandb.data_guard.transport_lag  N/A — V_$DATAGUARD_STATS 不存在
  yashandb.resource_manager.cpu_consumed_time N/A — V_$RSRC_CONSUMER_GROUP 无 CPU_TIME 列
  yashandb.resource_manager.cpu_wait_time N/A — V_$RSRC_CONSUMER_GROUP 无 CPU_WAIT_TIME 列
  yashandb.gc_cr_block_received      N/A — YashanDB 无此统计项
  yashandb.gc_current_block_received N/A — YashanDB 无此统计项

【v2.2 新增：New Relic Oracle 适配指标 — 来源：nri-oracledb spec.csv】
  yashandb.db.wait_top_event            当前 TOP 等待事件名称（V$SYSTEM_EVENT 排序）
  yashandb.db.wait_event_waits[event]  指定等待事件的 TOTAL_WAITS（参数化）
  yashandb.db.wait_event_time[event]    指定等待事件的 TIME_WAITED（参数化，厘秒）
  yashandb.db.waits_total              所有等待事件 TOTAL_WAITS 之和
  yashandb.db.wait_time_total          所有等待事件 TIME_WAITED 之和（×10=ms）
  yashandb.db.wait_time_ratio          N/A — V$SYS_TIME_MODEL 不存在
  yashandb.sga.buffer_busy_waits       缓冲区忙等待次数（V$SYSTEM_EVENT）
  yashandb.sga.free_buffer_waits       空闲缓冲区等待次数（V$SYSTEM_EVENT）
  yashandb.sga.free_buffer_inspected   空闲缓冲区检查数量（V$SYSSTAT）
  yashandb.sga.fixed_size              SGA 固定部分大小（字节，V$SGASTAT）
  yashandb.sga.redo_buffers            Redo 缓冲区大小（字节，V$SGASTAT）
  yashandb.sga.log_buffer_space_waits  日志缓冲区空间等待次数
  yashandb.disk.total_reads            所有数据文件物理读取总次数（V$FILESTAT）
  yashandb.disk.total_writes           所有数据文件物理写入总次数（V$FILESTAT）
  yashandb.disk.total_read_time        物理读取总时间（×10=ms）
  yashandb.disk.total_write_time       物理写入总时间（×10=ms）
  yashandb.session.inactive            非活跃会话数量（V$SESSION STATUS='INACTIVE'）
  yashandb.session.background          后台会话总数（V$SESSION TYPE='BACKGROUND'）
  yashandb.session.active_detail       活跃会话详细信息（文本，Zabbix 文本监控项）
  yashandb.redolog.waits               Redo 日志相关等待总次数
  yashandb.redolog.switch_checkpoint   检查点未完成导致的日志切换
  yashandb.library_cache_hit_ratio    库缓存命中率（%，v2.4 改为共享池估算）
  yashandb.library_cache_reload_ratio N/A — V$LIBRARYCACHE 不存在
  yashandb.row_cache_hit_ratio         N/A — V$ROWCACHE 不存在
  yashandb.rollback.gets               N/A — V$ROLLSTAT 不存在
  yashandb.rollback.waits              N/A — V$ROLLSTAT 不存在
  yashandb.rollback.ratio_wait        N/A — V$ROLLSTAT 不存在
  yashandb.sql.top_buffer_gets         V$SQLAREA 中最高 BUFFER_GETS
  yashandb.sql.top_disk_reads          V$SQLAREA 中最高 DISK_READS
  yashandb.sql.count                   V$SQLAREA 中 SQL 语句总数
  yashandb.db.current_logons           当前登录会话数
  yashandb.db.open_cursors            游标总数（V$SQLAREA 替代 V$OPEN_CURSOR）
  yashandb.db.user_limit_pct          用户连接限制使用率（%）
  yashandb.db.process_limit_pct        进程限制使用率（%）
  yashandb.db.session_limit_pct       会话限制使用率（%）
  yashandb.tablespace.offline_count   离线表空间数量
  yashandb.datafile.offline_count     离线数据文件数量
  yashandb.archive_log.count          归档日志文件总数
  yashandb.archive_log.first_time    最早归档时间
  yashandb.enqueue.locks              当前持有锁的数量
  yashandb.enqueue.requests          锁请求数量
  yashandb.archiver.failed            归档失败次数

【v2.3 新增：Nagios check_oracle_health 适配指标】
  yashandb.db.invalid_objects         无效数据库对象数量（DBA_OBJECTS，Nagios: invalid-objects）
  yashandb.db.invalid_indexes         无效索引数量（DBA_INDEXES，Nagios: invalid-objects）
  yashandb.db.stale_statistics        统计信息陈旧的表数量（DBA_TAB_STATISTICS，Nagios: stale-statistics）
  yashandb.db.soft_parse_ratio       软解析比率%（V$SYSSTAT SESSION CURSOR CACHE HITS，Nagios: soft-parse-ratio）
  yashandb.db.tablespace_remaining_days 表空间剩余天数（基于增长趋势预测，Nagios: tablespace-remaining-time）
  yashandb.db.datafile_max_usage_pct  数据文件最大容量使用率%（DBA_DATA_FILES，Nagios: datafiles-existing）
  yashandb.db.dbms_stats_available    DBMS_STATS 包是否可用（1=是，Nagios 内部使用）
  yashandb.segment.total_count        段（表/索引/LOB 等）总数（DBA_SEGMENTS）
  yashandb.segment.top_tablespace     占用空间最大的表空间名称（DBA_SEGMENTS）

【v2.4 新增：商业产品 gap 补全 Phase 1】
  yashandb.db.qps                    每秒查询数（V$SYSSTAT EXECUTE COUNT 累计值，Zabbix 自行计算 delta）
  yashandb.db.tps                    每秒事务数（V$SYSSTAT COMMITS 累计值，Zabbix 自行计算 delta）
  yashandb.archived_log.count_today   当天归档日志文件数量（V$ARCHIVED_LOG FIRST_TIME >= TRUNC(SYSDATE)）
  yashandb.db.wait_class.count[Application] 指定等待类的总等待次数（V$SYSTEM_WAIT_CLASS）
  yashandb.db.wait_class.time[Application]  指定等待类的总等待时间（厘秒，V$SYSTEM_WAIT_CLASS）
  yashandb.wait_class.discovery        等待类 LLD 自动发现（JSON，{#WAIT_CLASS} 宏）
  yashandb.tablespace.by_type[PERMANENT]  指定类型表空间总大小（字节）
  yashandb.tablespace.by_type[UNDO]       指定类型表空间总大小（字节）
  yashandb.tablespace.by_type[TEMPORARY]   指定类型表空间总大小（字节）
  yashandb.tablespace.temp_usage_pct    临时表空间使用率%（DBA_TEMP_FREE_SPACE）
  yashandb.tablespace.undo_usage_pct    Undo 表空间使用率%（V$TRANSACTION 活跃事务估算）
  yashandb.sql.top_buffer_gets_sql     Top SQL（按 BUFFER_GETS）的 SQL_ID
  yashandb.sql.top_disk_reads_sql     Top SQL（按 DISK_READS）的 SQL_ID
  yashandb.sql.top_executions_sql     Top SQL（按 EXECUTIONS）的 SQL_ID
  yashandb.resource_limit.usage_pct   资源限制使用率%（V$PARAMETER+V$PROCESS/V$SESSION 替代 V$RESOURCE_LIMIT）

【v2.5 新增：商业产品 gap 补全 Phase 2】
  yashandb.sql.p95_elapsed_ms        慢查询 P95 延迟（ms，PERCENTILE_CONT）
  yashandb.sql.p99_elapsed_ms        慢查询 P99 延迟（ms，PERCENTILE_CONT）
  yashandb.session.by_user[username]  指定用户的会话数量（V$SESSION）
  yashandb.session.by_program[program] 指定程序的会话数量（V$SESSION）
  yashandb.session.user.discovery     用户会话分布 LLD 发现（JSON，{#USERNAME} 宏）
  yashandb.session.program.discovery  程序会话分布 LLD 发现（JSON，{#PROGRAM} 宏）
  yashandb.invalid_objects.by_type[PROCEDURE] 指定类型的 INVALID 对象数量
  yashandb.invalid_objects.by_type[UDF]       指定类型的 INVALID 对象数量
  yashandb.invalid_objects.by_type.discovery   INVALID 对象类型 LLD 发现
  yashandb.datafile.non_autoextend_count   禁用了自动扩展的数据文件数量
  yashandb.user.expiring_soon_count     密码即将过期（7天内）的账户数
  yashandb.db.statistics_level           STATISTICS_LEVEL 参数值（文本）
"""


def get_connection(host, port, user, password):
    """建立 YashanDB 数据库连接"""
    if yaspy is None:
        raise RuntimeError(
            "YashanDB Python 驱动 (yaspy) 未安装。\n"
            "请参考官方文档安装: pip install yashandb-python-driver"
        )
    dsn = f"{host}:{port}"
    conn = yaspy.connect(dsn=dsn, user=user, password=password)
    return conn


def query_one(conn, sql, params=None):
    """执行查询，返回第一行第一列"""
    cursor = conn.cursor()
    try:
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        row = cursor.fetchone()
        return row[0] if row else None
    finally:
        cursor.close()


def query_all(conn, sql, params=None):
    """执行查询，返回所有行"""
    cursor = conn.cursor()
    try:
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        return cursor.fetchall()
    finally:
        cursor.close()


# -------------------------------------------------------
# 指标采集函数
# -------------------------------------------------------

def metric_db_status(conn):
    """数据库状态：1=正常，0=异常"""
    try:
        val = query_one(conn, "SELECT 1 FROM DUAL")
        return 1 if val == 1 else 0
    except Exception:
        return 0


def metric_db_version(conn):
    """数据库版本"""
    return query_one(conn, "SELECT VERSION FROM V$INSTANCE")


def metric_db_uptime(conn):
    """数据库启动时长（秒）
    YashanDB V$INSTANCE.STARTUP_TIME 是 DATE 类型，
    SELECT STARTUP_TIME 返回 datetime 对象（Python datetime 类型，非字符串）。
    在 Python 层做 datetime 减法得到 timedelta，再转换为秒。
    不在 SQL 层用 (SYSDATE - STARTUP_TIME) * 86400，
    因为该表达式在 YashanDB 中返回 INTERVAL DAY TO SECOND 类型，
    而非 NUMBER，导致 YAS-04423 数据类型不匹配错误。
    """
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT STARTUP_TIME FROM V$INSTANCE")
        row = cursor.fetchone()
        if not row or not row[0]:
            return 0
        startup_time = row[0]
        # yaspy 返回的是 Python datetime 对象（不是字符串）
        # 直接用 datetime 减法得到 timedelta
        import datetime
        if isinstance(startup_time, datetime.datetime):
            delta = datetime.datetime.now() - startup_time
        elif isinstance(startup_time, datetime.date):
            delta = datetime.datetime.now() - datetime.datetime.combine(startup_time, datetime.time())
        else:
            return 0
        return int(delta.total_seconds())
    finally:
        cursor.close()


def metric_db_mode(conn):
    """数据库模式"""
    return query_one(conn, "SELECT DATABASE_ROLE FROM V$DATABASE")


def metric_sessions_active(conn):
    """活跃会话数"""
    return query_one(conn,
        "SELECT COUNT(*) FROM V$SESSION WHERE STATUS = 'ACTIVE'")


def metric_sessions_total(conn):
    """总会话数"""
    return query_one(conn, "SELECT COUNT(*) FROM V$SESSION")


def metric_sessions_waiting(conn):
    """等待中的会话数"""
    return query_one(conn,
        "SELECT COUNT(*) FROM V$SESSION WHERE WAIT_CLASS IS NOT NULL")


def metric_sessions_max(conn):
    """最大会话限制"""
    return query_one(conn,
        "SELECT VALUE FROM V$PARAMETER WHERE NAME = 'sessions'")


def metric_memory_buffer_pool_size(conn):
    """Buffer Pool 总大小（字节）"""
    row = query_one(conn,
        "SELECT BLOCK_SIZE * (FREE_BUFFERS + USED_BUFFERS) "
        "FROM V$BUFFER_POOL_STATISTICS")
    return row


def metric_memory_buffer_pool_used(conn):
    """Buffer Pool 已使用大小（字节）"""
    return query_one(conn,
        "SELECT BLOCK_SIZE * USED_BUFFERS FROM V$BUFFER_POOL_STATISTICS")


def metric_memory_buffer_pool_hit(conn):
    """Buffer Pool 命中率（%）"""
    sql = """
        SELECT ROUND(
            (1 - PHYSICAL_READS / GREATEST(DB_BLOCK_GETS + CONSISTENT_GETS, 1))
            * 100, 2
        ) FROM V$BUFFER_POOL_STATISTICS
    """
    return query_one(conn, sql)


def metric_memory_vm_pool_size(conn):
    """VM Pool 总大小（字节）"""
    return query_one(conn,
        "SELECT TOTAL_SIZE FROM V$VMSTAT")


def metric_memory_vm_pool_used(conn):
    """VM Pool 已使用（字节）"""
    return query_one(conn,
        "SELECT USED_SIZE FROM V$VMSTAT")


def metric_tablespace_discovery(conn):
    """表空间 LLD 自动发现，返回 Zabbix LLD JSON（{#TABLESPACE} 宏）"""
    rows = query_all(conn,
        "SELECT TABLESPACE_NAME FROM DBA_TABLESPACES ORDER BY TABLESPACE_NAME")
    data = [{"{#TABLESPACE}": row[0]} for row in rows]
    return json.dumps({"data": data})


def metric_tablespace_total(conn, ts_name):
    """指定表空间总大小（字节）"""
    return query_one(conn,
        "SELECT SUM(BYTES) FROM DBA_DATA_FILES WHERE TABLESPACE_NAME = ?",
        (ts_name.upper(),))


def metric_tablespace_used(conn, ts_name):
    """指定表空间已使用（字节）"""
    sql = """
        SELECT SUM(d.BYTES) - NVL(SUM(f.BYTES), 0)
        FROM DBA_DATA_FILES d
        LEFT JOIN DBA_FREE_SPACE f ON d.TABLESPACE_NAME = f.TABLESPACE_NAME
        WHERE d.TABLESPACE_NAME = ?
    """
    return query_one(conn, sql, (ts_name.upper(),))


def metric_tablespace_free(conn, ts_name):
    """指定表空间剩余（字节）"""
    return query_one(conn,
        "SELECT SUM(BYTES) FROM DBA_FREE_SPACE WHERE TABLESPACE_NAME = ?",
        (ts_name.upper(),))


def metric_tablespace_pct_used(conn, ts_name):
    """指定表空间使用率（%）"""
    total = metric_tablespace_total(conn, ts_name)
    free = metric_tablespace_free(conn, ts_name)
    if total and total > 0:
        used = total - (free or 0)
        return round(used / total * 100, 2)
    return 0


def metric_redo_flush_speed(conn):
    """Redo 刷盘速度（字节/秒）"""
    return query_one(conn, "SELECT FLUSH_SPEED FROM V$REDOSTAT")


def metric_redo_free_space(conn):
    """Redo 空闲空间（字节）"""
    return query_one(conn, "SELECT FREE_SPACE FROM V$REDOSTAT")


def metric_redo_checkpoint_lag(conn):
    """检查点落后量"""
    return query_one(conn, "SELECT CHECKPOINT_LAG FROM V$REDOSTAT")


def metric_sql_executions_per_sec(conn):
    """每秒 SQL 执行次数（EXECUTE COUNT）"""
    return query_one(conn,
        "SELECT VALUE FROM V$SYSSTAT WHERE NAME='EXECUTE COUNT'")


def metric_sql_avg_elapsed_ms(conn):
    """SQL 平均执行时长（ms）"""
    sql = """
        SELECT ROUND(AVG(ELAPSED_TIME) / 1000, 2)
        FROM V$SQL
        WHERE EXECUTIONS > 0
    """
    return query_one(conn, sql)


def metric_sql_slow_count(conn):
    """慢 SQL 数量（执行时间 > 1s）"""
    return query_one(conn,
        "SELECT COUNT(*) FROM V$SQL "
        "WHERE ELAPSED_TIME > 1000000 AND EXECUTIONS > 0")


def metric_sql_parse_count(conn):
    """SQL 解析次数（PARSE COUNT (HARD)）"""
    return query_one(conn,
        "SELECT VALUE FROM V$SYSSTAT WHERE NAME = 'parse count (hard)'")


def metric_wait_top_event(conn):
    """当前 TOP 等待事件"""
    return query_one(conn,
        "SELECT EVENT FROM V$SYSTEM_EVENT "
        "ORDER BY TOTAL_WAITS DESC FETCH FIRST 1 ROWS ONLY")


def metric_wait_total_waits(conn):
    """总等待次数"""
    return query_one(conn,
        "SELECT SUM(TOTAL_WAITS) FROM V$SYSTEM_EVENT "
        "WHERE WAIT_CLASS != 'Idle'")


def metric_wait_time_waited_ms(conn):
    """总等待时间（ms）"""
    return query_one(conn,
        "SELECT ROUND(SUM(TIME_WAITED) / 100, 2) FROM V$SYSTEM_EVENT "
        "WHERE WAIT_CLASS != 'Idle'")


def metric_lock_count(conn):
    """当前锁数量"""
    return query_one(conn, "SELECT COUNT(*) FROM V$LOCK")


def metric_lock_blocking_sessions(conn):
    """阻塞中的会话数"""
    return query_one(conn,
        "SELECT COUNT(DISTINCT BLOCKING_SESSION) FROM V$SESSION "
        "WHERE BLOCKING_SESSION IS NOT NULL")


def metric_sysstat(conn, stat_name):
    """从 V_$SYSSTAT 查询指定统计项"""
    # YashanDB 中统计项名称为大写无括号（如 DISK READS）
    # Oracle 风格名称需转换
    return query_one(conn,
        "SELECT VALUE FROM V$SYSSTAT WHERE NAME = ?",
        (stat_name,))


def metric_db_stat_discovery(conn):
    """V$SYSSTAT 统计项 LLD 发现，返回 Zabbix LLD JSON（{#STAT_NAME} 宏）"""
    rows = query_all(conn,
        "SELECT DISTINCT NAME FROM V$SYSSTAT ORDER BY NAME")
    data = [{"{#STAT_NAME}": row[0]} for row in rows]
    return json.dumps({"data": data})


# =====================================================================
# Datadog Oracle 兼容指标（v2.0 新增，共 42 个可用指标）
# 以下函数对应 Datadog Oracle integration 中的监控指标
# YashanDB 适配说明：
#   - Oracle V$XXX → YashanDB V$XXX（YashanDB 兼容 Oracle 视图命名）
#   - V_$SYSSTAT 统计项名称需用大写无括号形式（如 'DISK READS' 而非 'physical reads'）
#   - 部分 Oracle 视图在 YashanDB 中不存在（标记为 N/A）
# =====================================================================

# ---- 会话与连接（6 个）----

def metric_active_background(conn):
    """活跃后台会话数"""
    return query_one(conn,
        "SELECT COUNT(*) FROM V$SESSION "
        "WHERE TYPE='BACKGROUND' AND STATUS='ACTIVE'")


def metric_active_sessions(conn):
    """活跃会话总数"""
    return query_one(conn,
        "SELECT COUNT(*) FROM V$SESSION WHERE STATUS='ACTIVE'")


def metric_process_limit(conn):
    """进程限制使用率（%）"""
    sql = """
        SELECT COUNT(*)*100.0/NULLIF(
            (SELECT TO_NUMBER(VALUE) FROM V$PARAMETER WHERE NAME='processes'),
            0)
        FROM V$PROCESS
    """
    return query_one(conn, sql)


def metric_session_count(conn):
    """会话总数"""
    return query_one(conn, "SELECT COUNT(*) FROM V$SESSION")


def metric_session_limit_usage(conn):
    """会话限制使用率（%）"""
    sql = """
        SELECT COUNT(*)*100.0/NULLIF(
            (SELECT TO_NUMBER(VALUE) FROM V$PARAMETER WHERE NAME='sessions'),
            0)
        FROM V$SESSION
    """
    return query_one(conn, sql)


def metric_user_sessions(conn):
    """用户会话数"""
    return query_one(conn,
        "SELECT COUNT(*) FROM V$SESSION WHERE TYPE='USER'")


# ---- SQL 解析与执行（2 个）----

def metric_hard_parses(conn):
    """硬解析次数（PARSE COUNT (HARD)）"""
    return query_one(conn,
        "SELECT VALUE FROM V$SYSSTAT WHERE NAME='PARSE COUNT (HARD)'")


def metric_memory_sorts_ratio(conn):
    """内存排序比率（%）"""
    sql = """
        SELECT (SELECT VALUE FROM V$SYSSTAT WHERE NAME='SORTS (MEMORY)')*100.0
               / NULLIF(
                   (SELECT VALUE FROM V$SYSSTAT WHERE NAME='SORTS (MEMORY)')
                   + (SELECT VALUE FROM V$SYSSTAT WHERE NAME='SORTS (DISK)'),
                   0)
        FROM DUAL
    """
    return query_one(conn, sql)


# ---- 缓存与内存（5 个）----

def metric_buffer_cachehit_ratio(conn):
    """缓冲区缓存命中率（%）"""
    sql = """
        SELECT (1-SUM(PHYSICAL_READS)
               / NULLIF(SUM(DB_BLOCK_GETS+CONSISTENT_GETS),0))*100
        FROM V$BUFFER_POOL_STATISTICS
    """
    return query_one(conn, sql)


def metric_cache_blocks_lost(conn):
    """丢失的缓存块数（LOST WRITE DETECTED）"""
    return query_one(conn,
        "SELECT VALUE FROM V$SYSSTAT WHERE NAME='LOST WRITE DETECTED'")


def metric_physical_memory_gb(conn):
    """物理内存大小（GB）"""
    return query_one(conn,
        "SELECT VALUE/1073741824 FROM V$OSSTAT WHERE STAT_NAME='PHYSICAL_MEMORY_BYTES'")


def metric_shared_memory_size(conn):
    """共享内存大小（字节）"""
    return query_one(conn, "SELECT SUM(SIZE) FROM V$SGA")


def metric_shared_pool_free(conn):
    """共享池空闲内存百分比（%）"""
    sql = """
        SELECT (SELECT BYTES FROM V$SGASTAT
                WHERE NAME='free memory' AND POOL='SHARE POOL')*100.0
               / NULLIF((SELECT SUM(BYTES) FROM V$SGASTAT WHERE POOL='SHARE POOL'),0)
        FROM DUAL
    """
    return query_one(conn, sql)


# ---- PGA 进程内存（4 个）----
# 注：YashanDB 23.4 的 V$PROCESS 无 PGA_ALLOC_MEM 等列（只有 NAME/THREAD_ID/STATUS），
#     改用 V$SGASTAT 估算 SGA 总内存作为替代（实际为 SGA 而非 PGA，但有参考价值）。
#     V$PGASTAT 在 YashanDB 23.4 中不存在（已验证）。

def metric_process_pga_allocated_memory(conn):
    """进程 PGA 分配内存（字节）
    替代方案：使用 V$SGASTAT 统计全部 SGA 内存之和。
    注意：此值为 SGA 总内存，与 Oracle 的 PGA 语义不同，仅作参考。
    """
    sql = "SELECT SUM(BYTES) FROM V$SGASTAT"
    return query_one(conn, sql)


def metric_process_pga_freeable_memory(conn):
    """进程 PGA 可释放内存（字节）
    YashanDB 中无可直接对应的 PGA 列，V$SGASTAT 中的 'free memory' 属于 SGA 共享池，
    与 PGA freeable 概念不同。此处返回 'SHARE POOL' 中的空闲内存字节数。
    """
    sql = "SELECT BYTES FROM V$SGASTAT WHERE NAME='free memory' AND POOL='SHARE POOL'"
    return query_one(conn, sql)


def metric_process_pga_max_memory(conn):
    """进程当前 PGA 最大内存（字节）
    YashanDB 无 PGA_MAX_MEM 列。退化为返回 SGA 总内存估算值。
    """
    sql = "SELECT SUM(BYTES) FROM V$SGASTAT"
    return query_one(conn, sql)


def metric_process_pga_used_memory(conn):
    """进程 PGA 已用内存（字节）
    替代方案：返回 SGA 总内存减去共享池空闲内存的估算值。
    公式：SGA总内存 - SHARE POOL free memory
    """
    sql = """
        SELECT (SELECT SUM(BYTES) FROM V$SGASTAT)
             - (SELECT NVL(BYTES,0) FROM V$SGASTAT
                WHERE NAME='free memory' AND POOL='SHARE POOL')
        FROM DUAL
    """
    return query_one(conn, sql)


# =====================================================================
# New Relic Oracle 指标适配（来源：nri-oracledb spec.csv）
# 适配条件：YashanDB 23.4 必须有对应的动态性能视图
# =====================================================================

# ---- 等待事件（V$SYSTEM_EVENT）----

def metric_db_wait_top_event(conn):
    """当前 TOP 等待事件名称（按 TIME_WAITED 排序）
    对标 New Relic: db.waitEventTop
    来源: V$SYSTEM_EVENT（YashanDB 23.4 列名是 WAIT_EVENT，不是 Oracle 的 EVENT）
    """
    sql = """
        SELECT WAIT_EVENT
        FROM V$SYSTEM_EVENT
        ORDER BY TIME_WAITED DESC NULLS LAST
        FETCH FIRST 1 ROWS ONLY
    """
    return query_one(conn, sql)


def metric_db_wait_event_waits(conn, event_name=None):
    """指定等待事件的 TOTAL_WAITS（支持参数化）
    用法: yashandb.db.wait_event_waits[log file sync]
    对标 New Relic: db.waitEventTotalWaits{EVENT}
    """
    if not event_name:
        return None
    sql = f"SELECT TOTAL_WAITS FROM V$SYSTEM_EVENT WHERE EVENT='{event_name}'"
    return query_one(conn, sql)


def metric_db_wait_event_discovery(conn):
    """等待事件 LLD 发现，返回 Zabbix LLD JSON（{#WAIT_EVENT} 宏）"""
    rows = query_all(conn,
        "SELECT DISTINCT EVENT FROM V$SYSTEM_EVENT ORDER BY EVENT")
    data = [{"{#WAIT_EVENT}": row[0]} for row in rows]
    return json.dumps({"data": data})


def metric_db_wait_event_time(conn, event_name=None):
    """指定等待事件的 TIME_WAITED（支持参数化）
    用法: yashandb.db.wait_event_time[log file sync]
    对标 New Relic: db.waitEventTime{EVENT}
    """
    if not event_name:
        return None
    sql = f"SELECT TIME_WAITED FROM V$SYSTEM_EVENT WHERE EVENT='{event_name}'"
    return query_one(conn, sql)


def metric_db_wait_events_count(conn):
    """等待事件总数（所有事件 TOTAL_WAITS 之和）
    对标 New Relic: db.waitsTotal
    """
    sql = "SELECT SUM(TOTAL_WAITS) FROM V$SYSTEM_EVENT"
    return query_one(conn, sql)


def metric_db_wait_time_total(conn):
    """等待时间总和（所有事件 TIME_WAITED 之和，单位：厘秒→转换为 ms）
    对标 New Relic: db.waitTimeTotal
    """
    sql = "SELECT SUM(TIME_WAITED) FROM V$SYSTEM_EVENT"
    val = query_one(conn, sql)
    return val * 10 if val else 0  # TIME_WAITED 单位为 10ms，乘10得ms


def metric_db_wait_time_ratio(conn):
    """数据库等待时间占总 DB time 的比率（%）
    公式: (DB time - DB CPU) / DB time * 100
    V$SYS_TIME_MODEL 在 YashanDB 23.4 不存在（已验证），使用 V$SYSTEM_EVENT 估算：
      DB time ≈ Σ(TIME_WAITED)，DB CPU ≈ 无法获取
    退化为返回 NULL 或使用 wait time / 总运行时间估算。
    """
    # 退化为: 总等待时间 / (总等待时间 + 估算CPU时间)
    # 由于无 V$SYS_TIME_MODEL，暂时返回 NULL 并记录 N/A
    return None


# ---- SGA 缓冲区指标（V$SYSTEM_EVENT + V$SGASTAT）----

def metric_sga_buffer_busy_waits(conn):
    """缓冲区忙等待次数（buffer busy waits）
    对标 New Relic: sga.bufferBusyWaits
    来源: V$SYSTEM_EVENT（YashanDB 有此等待事件）
    """
    sql = """
        SELECT NVL(SUM(TOTAL_WAITS), 0)
        FROM V$SYSTEM_EVENT
        WHERE EVENT IN ('buffer busy waits', 'buffer busy')
    """
    return query_one(conn, sql)


def metric_sga_free_buffer_waits(conn):
    """空闲缓冲区等待次数（free buffer waits）
    对标 New Relic: sga.freeBufferWaits
    """
    sql = """
        SELECT NVL(SUM(TOTAL_WAITS), 0)
        FROM V$SYSTEM_EVENT
        WHERE EVENT IN ('free buffer waits', 'free buffer')
    """
    return query_one(conn, sql)


def metric_sga_free_buffer_inspected(conn):
    """空闲缓冲区检查数量（free buffer inspected）
    对标 New Relic: sga.freeBufferInspected
    注：此统计项可能不存在于 V$SYSSTAT，使用 0 降级。
    """
    sql = "SELECT VALUE FROM V$SYSSTAT WHERE NAME='BUFFER BLOCKS INSPECTED'"
    val = query_one(conn, sql)
    return val if val is not None else 0


# ---- SGA 固定指标（V$SGASTAT）----

def metric_sga_fixed_size(conn):
    """SGA 固定部分大小（字节）
    对标 New Relic: sga.fixedSizeInBytes
    来源: V$SGASTAT 中非 pool 的 NAME='fixed size' 记录。
    若无此记录则返回 0。
    """
    sql = "SELECT BYTES FROM V$SGASTAT WHERE NAME='fixed size' AND POOL IS NULL"
    val = query_one(conn, sql)
    return val if val else 0


def metric_sga_redo_buffers(conn):
    """Redo 缓冲区大小（字节）
    对标 New Relic: sga.redoBuffersInBytes
    YashanDB: V$SGASTAT 中 POOL='LARGE POOL' 或 NAME 含 'redo buffer'。
    """
    sql = "SELECT BYTES FROM V$SGASTAT WHERE NAME='redo buffers' AND POOL IS NULL"
    val = query_one(conn, sql)
    return val if val else 0


def metric_sga_log_buffer_space_waits(conn):
    """日志缓冲区空间等待次数
    对标 New Relic: sga.logBufferSpaceWaits
    """
    sql = """
        SELECT NVL(SUM(TOTAL_WAITS), 0)
        FROM V$SYSTEM_EVENT
        WHERE EVENT IN ('log buffer space', 'log file sync', 'log file parallel write')
    """
    return query_one(conn, sql)


# ---- 磁盘 I/O（V$FILESTAT）----

def metric_disk_total_reads(conn):
    """所有数据文件的物理读取总次数
    对标 New Relic: disk.reads（取自 gv$filestat 汇总）
    来源: V$FILESTAT（YashanDB 23.4 已验证有 6 行数据）
    """
    sql = "SELECT SUM(PHYRDS) FROM V$FILESTAT"
    return query_one(conn, sql)


def metric_disk_total_writes(conn):
    """所有数据文件的物理写入总次数
    对标 New Relic: disk.writes
    """
    sql = "SELECT SUM(PHYWRTS) FROM V$FILESTAT"
    return query_one(conn, sql)


def metric_disk_total_read_time(conn):
    """所有数据文件的物理读取总时间（厘秒）
    对标 New Relic: disk.readTimeInMilliseconds
    单位转换：原值×10=毫秒
    """
    sql = "SELECT SUM(READTIM) FROM V$FILESTAT"
    val = query_one(conn, sql)
    return val if val else 0


def metric_disk_total_write_time(conn):
    """所有数据文件的物理写入总时间（厘秒）
    对标 New Relic: disk.writeTimeInMilliseconds
    单位转换：原值×10=毫秒
    """
    sql = "SELECT SUM(WRITETIM) FROM V$FILESTAT"
    val = query_one(conn, sql)
    return val if val else 0


# ---- 会话增强指标（V$SESSION）----

def metric_session_inactive(conn):
    """非活跃会话数量
    对标 New Relic: db.sessionInactive（近似）
    V$SESSION STATUS='INACTIVE' 即非活跃会话。
    """
    sql = "SELECT COUNT(*) FROM V$SESSION WHERE STATUS='INACTIVE'"
    return query_one(conn, sql)


def metric_session_background(conn):
    """后台会话总数
    对标 New Relic: db.backgroundSessions
    """
    sql = "SELECT COUNT(*) FROM V$SESSION WHERE TYPE='BACKGROUND'"
    return query_one(conn, sql)


def metric_session_active_detail(conn):
    """活跃会话详细信息（JSON），含 SID/用户名/程序/等待事件
    对标 New Relic: db.activeSessions（展平为文本）
    用于告警上下文，Zabbix 中可作为文本监控项展示。
    """
    sql = """
        SELECT LISTAGG(
            SID || '|' || NVL(USERNAME,'NULL') || '|' || NVL(WAIT_EVENT,'ON CPU') || '|' || NVL(PROGRAM,'NULL'),
            ';'
        ) WITHIN GROUP(ORDER BY SID)
        FROM V$SESSION
        WHERE STATUS='ACTIVE' AND TYPE='USER'
    """
    return query_one(conn, sql)


# ---- Redo 日志增强（V$SYSTEM_EVENT）----

def metric_redolog_waits(conn):
    """Redo 日志相关等待总次数
    对标 New Relic: redoLog.waits
    包括: log file sync + log file parallel write + log buffer space
    """
    sql = """
        SELECT SUM(TOTAL_WAITS)
        FROM V$SYSTEM_EVENT
        WHERE EVENT IN ('log file sync', 'log file parallel write', 'log buffer space')
    """
    return query_one(conn, sql)


def metric_redolog_switch_checkpoint_incomplete(conn):
    """检查点未完成导致的日志切换次数
    对标 New Relic: redoLog.logFileSwitchCheckpointIncomplete
    YashanDB 中可能无独立统计项，退化为查 'log file switch' 事件。
    """
    sql = """
        SELECT NVL(SUM(TOTAL_WAITS), 0)
        FROM V$SYSTEM_EVENT
        WHERE EVENT LIKE '%log file switch%checkpoint%incomplete%'
           OR EVENT = 'log file switch checkpoint incomplete'
    """
    return query_one(conn, sql)


# ---- 库缓存/字典缓存（N/A 降级）----

def metric_library_cache_hit_ratio(conn):
    """库缓存命中率（%）
    对标 Dynatrace/New Relic: sga.sharedPoolLibraryCacheHitRatio
    YashanDB 23.4 无 V$LIBRARYCACHE，通过共享池内存分配估算命中率：
      命中率 ≈ 已用共享池 / 总共享池 * 100
      与 Oracle 库缓存命中率不同，但能反映共享池利用率趋势。
    """
    sql = """
        SELECT ROUND(
            (SUM(BYTES) - NVL(SUM(CASE WHEN NAME='free memory' THEN BYTES END), 0))
            * 100.0 / NULLIF(SUM(BYTES), 0),
        2)
        FROM V$SGASTAT WHERE POOL='SHARE POOL'
    """
    return query_one(conn, sql)


def metric_library_cache_reload_ratio(conn):
    """库缓存重载比率
    对标 New Relic: sga.sharedPoolLibraryCacheReloadRatio
    V$LIBRARYCACHE 不存在，返回 0。
    """
    return 0  # N/A


def metric_row_cache_hit_ratio(conn):
    """行缓存命中率（%）
    对标 New Relic: sga.sharedPoolDictCacheMissRatio（反向）
    V$ROWCACHE 在 YashanDB 23.4 不存在（已验证），返回 NULL。
    """
    return None  # N/A - V$ROWCACHE 不存在


# ---- 回滚段（N/A 降级）----

def metric_rollback_gets(conn):
    """回滚段获取次数
    对标 New Relic: rollbackSegments.gets
    V$ROLLSTAT 在 YashanDB 23.4 不存在（已验证），返回 NULL。
    """
    return None  # N/A - V$ROLLSTAT 不存在


def metric_rollback_waits(conn):
    """回滚段等待次数
    对标 New Relic: rollbackSegments.waits
    """
    return None  # N/A


def metric_rollback_ratio_wait(conn):
    """回滚段等待比率
    对标 New Relic: rollbackSegments.ratioWait
    """
    return None  # N/A


# ---- Top SQL 指标（V$SQLAREA）----

def metric_top_sql_buffer_gets(conn):
    """缓冲池总获取次数最多的 SQL 的 BUFFER_GETS
    对标 New Relic: db.sqlAreaBufferGets（近似）
    返回最高 BUFFER_GETS 的 SQL 语句获取次数。
    """
    sql = "SELECT MAX(BUFFER_GETS) FROM V$SQLAREA"
    return query_one(conn, sql)


def metric_top_sql_disk_reads(conn):
    """磁盘读取最多的 SQL 的 DISK_READS
    对标 New Relic: db.sqlAreaDiskReads
    """
    sql = "SELECT MAX(DISK_READS) FROM V$SQLAREA"
    return query_one(conn, sql)


def metric_sql_count(conn):
    """V$SQLAREA 中 SQL 语句总数
    对标 New Relic: db.sqlAreaCount
    """
    sql = "SELECT COUNT(*) FROM V$SQLAREA"
    return query_one(conn, sql)


# ---- 数据库综合指标 ----

def metric_db_current_logons(conn):
    """当前登录会话数（当前实例）
    对标 New Relic: db.currentLogons
    近似: SELECT COUNT(*) FROM V$SESSION
    """
    sql = "SELECT COUNT(*) FROM V$SESSION"
    return query_one(conn, sql)


def metric_db_open_cursors(conn):
    """当前打开的游标总数
    对标 New Relic: db.currentOpenCursors
    V$OPEN_CURSOR 在 YashanDB 不存在（已验证），使用 V$SQLAREA COUNT 替代。
    """
    sql = "SELECT COUNT(*) FROM V$SQLAREA"
    return query_one(conn, sql)


def metric_db_user_limit_pct(conn):
    """用户连接限制使用率（%）
    对标 New Relic: db.userLimitPercentage
    """
    sql = """
        SELECT ROUND(
            (SELECT TO_NUMBER(VALUE) FROM V$PARAMETER WHERE NAME='sessions') * 100.0 /
            NULLIF((SELECT TO_NUMBER(VALUE) FROM V$PARAMETER WHERE NAME='sessions'), 0),
        2)
        FROM DUAL
    """
    return query_one(conn, sql)


def metric_db_process_limit_pct(conn):
    """进程限制使用率（%）
    对标 New Relic: db.processLimitPercentage
    """
    sql = """
        SELECT ROUND(
            COUNT(*) * 100.0 /
            NULLIF((SELECT TO_NUMBER(VALUE) FROM V$PARAMETER WHERE NAME='processes'), 0),
        2)
        FROM V$PROCESS
    """
    return query_one(conn, sql)


def metric_db_session_limit_pct(conn):
    """会话限制使用率（%）
    对标 New Relic: db.sessionLimitPercentage
    """
    sql = """
        SELECT ROUND(
            COUNT(*) * 100.0 /
            NULLIF((SELECT TO_NUMBER(VALUE) FROM V$PARAMETER WHERE NAME='sessions'), 0),
        2)
        FROM V$SESSION
    """
    return query_one(conn, sql)


# ---- 表空间增强 ----

def metric_tablespace_offline_count(conn):
    """离线表空间数量
    对标 New Relic: tablespace.offlineCDBDatafiles（简化版：统计离线的表空间）
    """
    sql = "SELECT COUNT(*) FROM DBA_TABLESPACES WHERE STATUS='OFFLINE'"
    return query_one(conn, sql)


def metric_datafile_offline_count(conn):
    """离线数据文件数量
    对标 New Relic: tablespace.offlineCDBDatafiles
    """
    sql = "SELECT COUNT(*) FROM V$DATAFILE WHERE STATUS='OFFLINE'"
    return query_one(conn, sql)


# ---- V$ARCHIVED_LOG 增强 ----

def metric_archived_log_count(conn):
    """归档日志文件总数
    对标 New Relic: archiveLog.totalCount（近似）
    """
    sql = "SELECT COUNT(*) FROM V$ARCHIVED_LOG"
    return query_one(conn, sql)


def metric_archived_log_first_time(conn):
    """最早的归档日志时间（作为文本）
    用于判断归档是否正常。
    """
    sql = """
        SELECT TO_CHAR(MIN(FIRST_TIME), 'YYYY-MM-DD HH24:MI:SS')
        FROM V$ARCHIVED_LOG
    """
    return query_one(conn, sql)


# ---- V$LOCK 增强 ----

def metric_enqueued_locks(conn):
    """当前持有锁的数量（不重复 SID）
    对标 New Relic: enqueue.locks（近似）
    """
    sql = "SELECT COUNT(DISTINCT SID) FROM V$LOCK WHERE LMODE > 0"
    return query_one(conn, sql)


def metric_enqueued_requests(conn):
    """锁请求数量（REQUEST > 0）
    对标 New Relic: enqueue.requests（近似）
    """
    sql = "SELECT COUNT(*) FROM V$LOCK WHERE REQUEST > 0"
    return query_one(conn, sql)


# ---- 数据质量检查 ----

def metric_archiver_failed(conn):
    """归档失败次数
    对标 New Relic: archiver.failed
    YashanDB 中查 V$SYSTEM_EVENT 的 'archive log' 相关事件。
    """
    sql = """
        SELECT NVL(SUM(TOTAL_WAITS), 0)
        FROM V$SYSTEM_EVENT
        WHERE EVENT LIKE '%archive%error%'
           OR EVENT = 'archive log error'
    """
    return query_one(conn, sql)


# =============================================================================
# v2.3 新增：Nagios check_oracle_health 适配指标
# 视图兼容性参考：
#   DBA_OBJECTS.STATUS          ✅ YashanDB 23.4 官方文档确认
#   DBA_INDEXES.STATUS          ✅ YashanDB 23.4 官方文档确认
#   DBA_TAB_STATISTICS.STALE_STATS ✅ YashanDB 23.4 官方文档确认
#   DBA_DATA_FILES.MAXBYTES      ✅ YashanDB 23.4 官方文档确认
#   DBA_TABLESPACE_USAGE_METRICS ✅ 实机验证存在
#   DBA_TAB_MODIFICATIONS       ✅ YashanDB 23.4 官方文档确认
#   DBA_SEGMENTS                ✅ YashanDB 23.4 官方文档确认
#   USER_OBJECTS (DBMS_STATS)   ✅ 实机验证存在
#   V$SYSSTAT (SESSION CURSOR CACHE HITS) ✅ 23.4 存在
#   DBA_ROLLBACK_SEGS           ❌ YashanDB 23.4 无此视图
#   V$RECOVERY_FILE_DEST        ❌ YashanDB 23.4 无此视图（RMAN/闪回功能不同）
# =============================================================================

def metric_invalid_objects(conn):
    """无效数据库对象数量
    对标 Nagios: check_oracle_health --mode invalid-objects
    来源: DBA_OBJECTS WHERE STATUS='INVALID'
    """
    return query_one(conn,
        "SELECT COUNT(*) FROM DBA_OBJECTS WHERE STATUS='INVALID'")


def metric_invalid_indexes(conn):
    """无效索引数量
    对标 Nagios: check_oracle_health --mode invalid-objects (索引部分)
    来源: DBA_INDEXES WHERE STATUS='INVALID'
    """
    return query_one(conn,
        "SELECT COUNT(*) FROM DBA_INDEXES WHERE STATUS='INVALID'")


def metric_stale_statistics(conn):
    """统计信息陈旧的表数量
    对标 Nagios: check_oracle_health --mode stale-statistics
    来源: DBA_TAB_STATISTICS WHERE STALE_STATS='YES'
    """
    return query_one(conn,
        "SELECT COUNT(*) FROM DBA_TAB_STATISTICS WHERE STALE_STATS='YES'")


def metric_soft_parse_ratio(conn):
    """软解析比率（%）
    对标 Nagios: check_oracle_health --mode soft-parse-ratio
    计算方式: SESSION CURSOR CACHE HITS / (SESSION CURSOR CACHE HITS + PARSE COUNT (HARD)) * 100
    注: YashanDB V$SYSSTAT 有 SESSION CURSOR CACHE HITS，无 TOTAL PARSE COUNT
    """
    sql = """
        SELECT
            NVL(
                (SELECT VALUE FROM V$SYSSTAT WHERE NAME='SESSION CURSOR CACHE HITS') /
                NULLIF(
                    (SELECT VALUE FROM V$SYSSTAT WHERE NAME='SESSION CURSOR CACHE HITS') +
                    (SELECT NVL(VALUE, 0) FROM V$SYSSTAT WHERE NAME='PARSE COUNT (HARD)'),
                    0
                ) * 100,
                0
            )
        FROM DUAL
    """
    return query_one(conn, sql)


def metric_tablespace_remaining_days(conn):
    """表空间剩余天数（基于使用率估算）
    对标 Nagios: check_oracle_health --mode tablespace-remaining-time
    YashanDB 无 DBA_TABLESPACE_USAGE_METRICS，改用 DBA_TABLESPACES + DBA_DATA_FILES
    简化算法：使用率>95%剩余0天，>90%剩余1天，否则估算
    返回: 剩余天数（天），-1 表示无法计算
    """
    try:
        sql = """
            WITH ts_usage AS (
                SELECT
                    d.TABLESPACE_NAME,
                    SUM(d.BYTES) AS total_bytes,
                    SUM(d.MAXBYTES) AS max_bytes,
                    NVL(SUM(f.BYTES), 0) AS free_bytes,
                    CASE WHEN SUM(d.MAXBYTES) > 0
                         THEN ROUND((SUM(d.BYTES) - NVL(SUM(f.BYTES), 0)) * 100.0 / SUM(d.MAXBYTES), 2)
                         ELSE 0 END AS used_pct
                FROM DBA_DATA_FILES d
                LEFT JOIN DBA_FREE_SPACE f ON d.TABLESPACE_NAME = f.TABLESPACE_NAME
                GROUP BY d.TABLESPACE_NAME
            )
            SELECT
                CASE
                    WHEN used_pct > 95 THEN 0
                    WHEN used_pct >= 90 THEN 1
                    WHEN max_bytes = 0 OR free_bytes = 0 THEN -1
                    ELSE GREATEST(0, ROUND((max_bytes - (max_bytes * used_pct / 100.0)) / (max_bytes * used_pct / 100.0 / 30.0)))
                END
            FROM ts_usage
            WHERE used_pct = (SELECT MAX(used_pct) FROM ts_usage)
        """
        result = query_one(conn, sql)
        return result if result is not None else -1
    except Exception:
        return -1

def metric_datafile_max_usage_pct(conn):
    """数据文件最大容量使用率（%）
    对标 Nagios: check_oracle_health --mode datafiles-existing
    计算: MAX(BYTES/MAXBYTES) * 100，所有数据文件中使用率最高者
    """
    sql = """
        SELECT NVL(ROUND(MAX(BYTES / NULLIF(MAXBYTES, 0)) * 100, 2), 0)
        FROM DBA_DATA_FILES
        WHERE MAXBYTES > 0
    """
    return query_one(conn, sql)


def metric_dbms_stats_available(conn):
    """DBMS_STATS 包是否可用（1=可用，0=不可用）
    对标 Nagios: 内部使用
    通过查询 USER_OBJECTS 确认 DBMS_STATS 对象是否存在
    """
    val = query_one(conn,
        "SELECT COUNT(*) FROM USER_OBJECTS WHERE OBJECT_NAME='DBMS_STATS'")
    return 1 if val and val > 0 else 0


def metric_segment_total_count(conn):
    """段（表/索引）总数
    对标 Nagios: check_oracle_health --mode seg-top10-logical-reads（基础）
    来源: DBA_SEGMENTS 计数
    """
    return query_one(conn, "SELECT COUNT(*) FROM DBA_SEGMENTS")


def metric_segment_top_tablespace(conn):
    """占用空间最大的表空间名称
    来源: DBA_SEGMENTS GROUP BY TABLESPACE_NAME ORDER BY SUM(BYTES) DESC
    """
    sql = """
        SELECT TABLESPACE_NAME
        FROM DBA_SEGMENTS
        GROUP BY TABLESPACE_NAME
        ORDER BY SUM(BYTES) DESC
        FETCH FIRST 1 ROW ONLY
    """
    return query_one(conn, sql)


# ---- 物理 I/O（2 个）----

def metric_physical_reads(conn):
    """每秒物理读取次数（DISK READS）"""
    return query_one(conn,
        "SELECT VALUE FROM V$SYSSTAT WHERE NAME='DISK READS'")


def metric_physical_writes(conn):
    """每秒物理写入次数（DISK WRITES）"""
    return query_one(conn,
        "SELECT VALUE FROM V$SYSSTAT WHERE NAME='DISK WRITES'")


# ---- 逻辑读取（2 个）----

def metric_consistent_read_changes(conn):
    """每秒一致性读变更次数（CONSISTENT CHANGES）"""
    return query_one(conn,
        "SELECT VALUE FROM V$SYSSTAT WHERE NAME='CONSISTENT CHANGES'")


def metric_db_block_changes(conn):
    """每秒数据库块变更数（BLOCK CHANGES）"""
    return query_one(conn,
        "SELECT VALUE FROM V$SYSSTAT WHERE NAME='BLOCK CHANGES'")


def metric_logical_reads(conn):
    """每秒逻辑读取次数（DB BLOCK GETS + CONSISTENT GETS）"""
    sql = """
        SELECT (SELECT VALUE FROM V$SYSSTAT WHERE NAME='DB BLOCK GETS')
               + (SELECT VALUE FROM V$SYSSTAT WHERE NAME='CONSISTENT GETS')
        FROM DUAL
    """
    return query_one(conn, sql)


# ---- 排序与扫描（2 个）----

def metric_disk_sorts(conn):
    """每秒磁盘排序次数（SORTS (DISK)）"""
    return query_one(conn,
        "SELECT VALUE FROM V$SYSSTAT WHERE NAME='SORTS (DISK)'")


def metric_sorts_per_user_call(conn):
    """每次用户调用的排序次数"""
    sql = """
        SELECT ((SELECT VALUE FROM V$SYSSTAT WHERE NAME='SORTS (MEMORY)')
                + (SELECT VALUE FROM V$SYSSTAT WHERE NAME='SORTS (DISK)'))
               / NULLIF((SELECT VALUE FROM V$SYSSTAT WHERE NAME='USER CALLS'),0)
        FROM DUAL
    """
    return query_one(conn, sql)


# ---- Redo 日志（3 个）----

def metric_redo_allocation_hit_ratio(conn):
    """Redo 空间分配命中率（%）"""
    sql = """
        SELECT (1
               - (SELECT VALUE FROM V$SYSSTAT WHERE NAME='REDO LOG SPACE REQUESTS')
                 / NULLIF((SELECT VALUE FROM V$SYSSTAT WHERE NAME='REDO ENTRIES'),0)
               )*100
        FROM DUAL
    """
    return query_one(conn, sql)


def metric_redo_generated(conn):
    """每秒生成 Redo 字节数（REDO SIZE）"""
    return query_one(conn,
        "SELECT VALUE FROM V$SYSSTAT WHERE NAME='REDO SIZE'")


def metric_redo_writes(conn):
    """每秒 Redo 写入次数（REDO WRITES）"""
    return query_one(conn,
        "SELECT VALUE FROM V$SYSSTAT WHERE NAME='REDO WRITES'")


# ---- 事务（3 个）----

def metric_dbwr_checkpoints(conn):
    """DBWR 检查点完成数（CHECKPOINTS COMPLETED）"""
    return query_one(conn,
        "SELECT VALUE FROM V$SYSSTAT WHERE NAME='CHECKPOINTS COMPLETED'")


def metric_user_commits(conn):
    """每秒用户提交次数（COMMITS）"""
    return query_one(conn,
        "SELECT VALUE FROM V$SYSSTAT WHERE NAME='COMMITS'")


def metric_user_rollbacks(conn):
    """用户回滚次数（ROLLBACKS）"""
    return query_one(conn,
        "SELECT VALUE FROM V$SYSSTAT WHERE NAME='ROLLBACKS'")


# ---- CPU 与系统资源（3 个）----

def metric_host_cpu_utilization(conn):
    """主机 CPU 利用率（%）"""
    sql = """
        SELECT BUSY_TIME*100.0/NULLIF(BUSY_TIME+IDLE_TIME,0)
        FROM (SELECT
                  SUM(CASE WHEN STAT_NAME='BUSY_TIME' THEN VALUE ELSE 0 END) AS BUSY_TIME,
                  SUM(CASE WHEN STAT_NAME='IDLE_TIME' THEN VALUE ELSE 0 END) AS IDLE_TIME
              FROM V$OSSTAT)
    """
    return query_one(conn, sql)


def metric_num_cpus(conn):
    """CPU 核心数"""
    return query_one(conn,
        "SELECT VALUE FROM V$OSSTAT WHERE STAT_NAME='NUM_CPUS'")


def metric_os_load(conn):
    """操作系统负载"""
    return query_one(conn,
        "SELECT VALUE FROM V$OSSTAT WHERE STAT_NAME='LOAD'")


# ---- 网络与延迟（2 个）----

def metric_avg_synchronous_single_block_read_latency(conn):
    """平均同步单块读延迟（ms）"""
    sql = """
        SELECT TIME_WAITED_MICRO/NULLIF(TOTAL_WAITS,0)/1000
        FROM V$SYSTEM_EVENT
        WHERE EVENT='db file sequential read'
    """
    return query_one(conn, sql)


def metric_network_traffic_volume(conn):
    """每秒网络流量（字节）"""
    return query_one(conn,
        "SELECT VALUE FROM V$SYSSTAT WHERE NAME='BYTES SENT VIA SQL*NET TO CLIENT'")


# ---- 索引（2 个）----

def metric_branch_node_splits(conn):
    """每秒分支节点分裂次数（INDEX BRANCH SPLIT）"""
    return query_one(conn,
        "SELECT VALUE FROM V$SYSSTAT WHERE NAME='INDEX BRANCH SPLIT'")


def metric_leaf_node_splits(conn):
    """每秒叶节点分裂次数（INDEX LEAF SPLIT）"""
    return query_one(conn,
        "SELECT VALUE FROM V$SYSSTAT WHERE NAME='INDEX LEAF SPLIT'")


# ---- 表空间 Datadog 版（5 个）----

def metric_tablespace_in_use(conn):
    """表空间使用率（%，全库汇总）"""
    sql = """
        SELECT (SUM(d.BYTES)-NVL(SUM(f.BYTES),0))*100.0
               / NULLIF(SUM(d.BYTES),0)
        FROM DBA_DATA_FILES d
        LEFT JOIN DBA_FREE_SPACE f
            ON d.TABLESPACE_NAME=f.TABLESPACE_NAME
    """
    return query_one(conn, sql)


def metric_tablespace_maxsize(conn):
    """表空间最大容量（字节）"""
    return query_one(conn, "SELECT SUM(MAXBYTES) FROM DBA_DATA_FILES")


def metric_tablespace_offline(conn):
    """离线表空间数量"""
    return query_one(conn,
        "SELECT COUNT(*) FROM DBA_TABLESPACES WHERE STATUS='OFFLINE'")


def metric_tablespace_size(conn):
    """表空间当前总大小（字节）"""
    return query_one(conn, "SELECT SUM(BYTES) FROM DBA_DATA_FILES")


def metric_tablespace_used(conn):
    """表空间已使用字节数"""
    sql = """
        SELECT SUM(d.BYTES)-NVL(SUM(f.BYTES),0)
        FROM DBA_DATA_FILES d
        LEFT JOIN DBA_FREE_SPACE f
            ON d.TABLESPACE_NAME=f.TABLESPACE_NAME
    """
    return query_one(conn, sql)


# ---- 全局缓存 RAC（2 个）----

def metric_gc_average_cr_get_time(conn):
    """全局缓存平均 CR 获取时间（ms）"""
    return query_one(conn,
        "SELECT VALUE FROM V$SYSSTAT WHERE NAME='GC CR BLOCK RECEIVE TIME'")


def metric_gc_average_current_get_time(conn):
    """全局缓存平均 current 块获取时间（ms）"""
    return query_one(conn,
        "SELECT VALUE FROM V$SYSSTAT WHERE NAME='GC CURRENT BLOCK RECEIVE TIME'")


# =============================================================================
# v2.4 新增：商业产品 gap 补全 Phase 1
# =============================================================================

def metric_db_qps(conn):
    """每秒查询数（累计值，Zabbix 内置 rate 函数计算 delta）
    对标 Flashcat Cprobe: oracle_qps
    来源: V$SYSSTAT NAME='EXECUTE COUNT'（YashanDB 大写敏感）
    注意: 此为累计值，Zabbix 需使用 change/sec 或 delta 计算每秒速率
    """
    return query_one(conn,
        "SELECT VALUE FROM V$SYSSTAT WHERE NAME='EXECUTE COUNT'")


def metric_db_tps(conn):
    """每秒事务数（累计值，Zabbix 内置 rate 函数计算 delta）
    对标 Flashcat Cprobe: oracle_tps
    来源: V$SYSSTAT NAME='COMMITS'（YashanDB 大写敏感）
    注意: 此为累计值，Zabbix 需使用 change/sec 或 delta 计算每秒速率
    """
    return query_one(conn,
        "SELECT VALUE FROM V$SYSSTAT WHERE NAME='COMMITS'")


def metric_archived_log_count_today(conn):
    """当天归档日志文件数量
    对标 Flashcat Cprobe: archivelog.count（当天）
    来源: V$ARCHIVED_LOG FIRST_TIME >= TRUNC(SYSDATE)
    """
    return query_one(conn,
        "SELECT COUNT(*) FROM V$ARCHIVED_LOG WHERE FIRST_TIME >= TRUNC(SYSDATE)")


def metric_wait_class_discovery(conn):
    """等待类 LLD 自动发现，返回 Zabbix LLD JSON（{#WAIT_CLASS} 宏）
    来源: V$SYSTEM_WAIT_CLASS
    """
    rows = query_all(conn,
        "SELECT DISTINCT WAIT_CLASS FROM V$SYSTEM_WAIT_CLASS ORDER BY WAIT_CLASS")
    data = [{"{#WAIT_CLASS}": row[0]} for row in rows]
    return json.dumps({"data": data})


def metric_wait_class_count(conn, wait_class=None):
    """指定等待类的总等待次数
    用法: yashandb.db.wait_class.count[Application]
    """
    if not wait_class:
        return None
    sql = f"SELECT TOTAL_WAITS FROM V$SYSTEM_WAIT_CLASS WHERE WAIT_CLASS='{wait_class}'"
    return query_one(conn, sql)


def metric_wait_class_time(conn, wait_class=None):
    """指定等待类的总等待时间（厘秒）
    用法: yashandb.db.wait_class.time[Application]
    """
    if not wait_class:
        return None
    sql = f"SELECT TIME_WAITED FROM V$SYSTEM_WAIT_CLASS WHERE WAIT_CLASS='{wait_class}'"
    return query_one(conn, sql)


def metric_tablespace_by_type(conn, ts_type=None):
    """指定类型（PERMANENT/TEMPORARY/UNDO）的表空间总大小（字节）
    对标 zCloud 巡检: 按类型分类的表空间
    来源: DBA_TABLESPACES.CONTENTS + DBA_DATA_FILES
    """
    if not ts_type:
        return None
    sql = """
        SELECT NVL(SUM(d.BYTES), 0)
        FROM DBA_DATA_FILES d
        JOIN DBA_TABLESPACES t ON d.TABLESPACE_NAME = t.TABLESPACE_NAME
        WHERE t.CONTENTS = ?
    """
    return query_one(conn, sql, (ts_type.upper(),))


def metric_tablespace_temp_usage_pct(conn):
    """临时表空间使用率（%）
    对标 CSDN Oracle 监控: 临时表空间使用情况
    来源: DBA_TEMP_FREE_SPACE
    公式: (ALLOCATED_SPACE - FREE_SPACE) / TABLESPACE_SIZE * 100
    YashanDB 中 ALLOCATED_SPACE 可能是已分配子池，FREE_SPACE 可能包含未分配空间，
    当 FREE_SPACE > ALLOCATED_SPACE 时已使用空间为 0，标记为 0。
    """
    sql = """
        SELECT ROUND(
            GREATEST(
                (SUM(ALLOCATED_SPACE) - SUM(FREE_SPACE)) * 100.0
                / NULLIF(SUM(TABLESPACE_SIZE), 0),
            0),
        2)
        FROM DBA_TEMP_FREE_SPACE
    """
    return query_one(conn, sql)


def metric_tablespace_undo_usage_pct(conn):
    """Undo 表空间使用率（%）
    对标 CSDN Oracle 监控: Undo 表空间使用情况
    YashanDB 无 DBA_UNDO_EXTENTS，改用 DBA_DATA_FILES+DBA_FREE_SPACE：
      Undo 表空间已用率 = (Undo数据文件总大小 - Undo空闲空间) / Undo数据文件总大小
    """
    sql = """
        SELECT ROUND(
            (SUM(d.BYTES) - NVL(SUM(f.BYTES), 0)) * 100.0
            / NULLIF(SUM(d.BYTES), 0),
        2)
        FROM DBA_DATA_FILES d
        JOIN DBA_TABLESPACES t ON d.TABLESPACE_NAME = t.TABLESPACE_NAME
        LEFT JOIN DBA_FREE_SPACE f ON d.TABLESPACE_NAME = f.TABLESPACE_NAME
        WHERE t.CONTENTS = 'UNDO'
    """
    return query_one(conn, sql)


def metric_sql_top_buffer_gets_sql(conn):
    """Top SQL（按 BUFFER_GETS 排序）的 SQL_ID
    对标 Flashcat/Oracle AWR: Top SQL by buffer gets
    来源: V$SQLAREA ORDER BY BUFFER_GETS DESC
    """
    sql = "SELECT SQL_ID FROM V$SQLAREA ORDER BY BUFFER_GETS DESC FETCH FIRST 1 ROWS ONLY"
    return query_one(conn, sql)


def metric_sql_top_disk_reads_sql(conn):
    """Top SQL（按 DISK_READS 排序）的 SQL_ID
    对标 Flashcat/Oracle AWR: Top SQL by disk reads
    来源: V$SQLAREA ORDER BY DISK_READS DESC
    """
    sql = "SELECT SQL_ID FROM V$SQLAREA ORDER BY DISK_READS DESC FETCH FIRST 1 ROWS ONLY"
    return query_one(conn, sql)


def metric_sql_top_executions_sql(conn):
    """Top SQL（按 EXECUTIONS 排序）的 SQL_ID
    对标 Flashcat/Oracle AWR: Top SQL by executions
    来源: V$SQLAREA ORDER BY EXECUTIONS DESC
    """
    sql = "SELECT SQL_ID FROM V$SQLAREA ORDER BY EXECUTIONS DESC FETCH FIRST 1 ROWS ONLY"
    return query_one(conn, sql)


def metric_resource_limit_usage_pct(conn):
    """资源限制使用率（%）— 取 sessions/processes 中较高者
    V$RESOURCE_LIMIT 在 YashanDB 23.4 中不存在，改用：
      (当前 V$SESSION COUNT / V$PARAMETER sessions) 和
      (当前 V$PROCESS COUNT / V$PARAMETER processes) 的最大值
    对标 Cprobe: resource_limit_usage
    """
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
    return query_one(conn, sql)


# =============================================================================
# v2.5 新增：商业产品 gap 补全 Phase 2
# =============================================================================

def metric_sql_p95_elapsed_ms(conn):
    """慢查询 P95 延迟（ms）
    对标 Cprobe: slow_queries（分位数版）
    来源: V$SQL PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY ELAPSED_TIME)
    注意: ELAPSED_TIME 单位为微秒，除以1000得毫秒
    """
    sql = """
        SELECT ROUND(
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY ELAPSED_TIME) / 1000,
        2)
        FROM V$SQL
        WHERE EXECUTIONS > 0 AND ELAPSED_TIME > 0
    """
    return query_one(conn, sql)


def metric_sql_p99_elapsed_ms(conn):
    """慢查询 P99 延迟（ms）
    对标 Cprobe: slow_queries（分位数版）
    """
    sql = """
        SELECT ROUND(
            PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY ELAPSED_TIME) / 1000,
        2)
        FROM V$SQL
        WHERE EXECUTIONS > 0 AND ELAPSED_TIME > 0
    """
    return query_one(conn, sql)


def metric_session_user_discovery(conn):
    """用户会话分布 LLD 发现，返回 Zabbix LLD JSON（{#USERNAME} 宏）
    对标 HertzBeat: 连接池效率（按用户分组）
    """
    rows = query_all(conn,
        "SELECT DISTINCT NVL(USERNAME,'(NULL)') FROM V$SESSION WHERE TYPE='USER' ORDER BY 1")
    data = [{"{#USERNAME}": row[0]} for row in rows]
    return json.dumps({"data": data})


def metric_session_by_user(conn, username=None):
    """指定用户的会话数量
    用法: yashandb.session.by_user[SYS]
    """
    if not username:
        return None
    sql = "SELECT COUNT(*) FROM V$SESSION WHERE TYPE='USER' AND USERNAME=?"
    return query_one(conn, sql, (username,))


def metric_session_program_discovery(conn):
    """程序会话分布 LLD 发现，返回 Zabbix LLD JSON（{#PROGRAM} 宏）
    对标 CSDN Oracle 监控: 连接池效率（按程序分组）
    """
    rows = query_all(conn,
        "SELECT DISTINCT NVL(PROGRAM,'(NULL)') FROM V$SESSION WHERE TYPE='USER' ORDER BY 1")
    data = [{"{#PROGRAM}": row[0]} for row in rows]
    return json.dumps({"data": data})


def metric_session_by_program(conn, program=None):
    """指定程序的会话数量
    用法: yashandb.session.by_program[python3]
    """
    if not program:
        return None
    sql = "SELECT COUNT(*) FROM V$SESSION WHERE TYPE='USER' AND PROGRAM=?"
    return query_one(conn, sql, (program,))


def metric_invalid_objects_by_type_discovery(conn):
    """INVALID 对象类型 LLD 发现，返回 Zabbix LLD JSON（{#OBJTYPE} 宏）
    """
    rows = query_all(conn,
        "SELECT DISTINCT OBJECT_TYPE FROM DBA_OBJECTS WHERE STATUS='INVALID' ORDER BY OBJECT_TYPE")
    data = [{"{#OBJTYPE}": row[0]} for row in rows]
    return json.dumps({"data": data})


def metric_invalid_objects_by_type(conn, obj_type=None):
    """指定类型的 INVALID 对象数量
    用法: yashandb.invalid_objects.by_type[PROCEDURE]
    """
    if not obj_type:
        return None
    sql = "SELECT COUNT(*) FROM DBA_OBJECTS WHERE STATUS='INVALID' AND OBJECT_TYPE=?"
    return query_one(conn, sql, (obj_type,))


def metric_datafile_non_autoextend_count(conn):
    """禁用了自动扩展的数据文件数量
    对标 zCloud 监控: 数据文件自动扩展状态
    来源: DBA_DATA_FILES WHERE AUTOEXTENSIBLE='NO'
    """
    sql = "SELECT COUNT(*) FROM DBA_DATA_FILES WHERE AUTOEXTENSIBLE='NO'"
    return query_one(conn, sql)


def metric_user_expiring_soon_count(conn):
    """密码即将过期（7天内）的账户数量
    对标 zCloud 安全监控: 密码即将过期账户
    来源: DBA_USERS WHERE EXPIRY_DATE BETWEEN TRUNC(SYSDATE) AND TRUNC(SYSDATE)+7
          AND ACCOUNT_STATUS NOT IN ('EXPIRED', 'LOCKED')
    """
    sql = """
        SELECT COUNT(*)
        FROM DBA_USERS
        WHERE EXPIRY_DATE IS NOT NULL
          AND EXPIRY_DATE <= TRUNC(SYSDATE) + 7
          AND ACCOUNT_STATUS NOT IN ('EXPIRED', 'LOCKED')
    """
    return query_one(conn, sql)


def metric_db_statistics_level(conn):
    """STATISTICS_LEVEL 参数值（文本）
    对标 zCloud 监控: 巡检 STATISTICS_LEVEL 非 TYPICAL 告警
    来源: V$PARAMETER WHERE NAME='STATISTICS_LEVEL'（YashanDB 大写敏感）
    注意: YashanDB 默认 STATISTICS_LEVEL=TYPICAL，返回 NULL 时标记 N/A
    """
    return query_one(conn,
        "SELECT VALUE FROM V$PARAMETER WHERE NAME='STATISTICS_LEVEL'")


def metric_long_transactions(conn):
    """超过3分钟的活跃事务数量
    通过 V$TRANSACTION 关联 V$SESSION（使用 SID 字段），统计 STATUS='ACTIVE' 且
    START_DATE 距当前时间超过3分钟的事务数量。
    YashanDB 实机验证结果（2026-04-10）：
      - V_$TRANSACTION 列：XID, SID, STATUS, START_DATE(DATE类型), ...
      - V_$SESSION 列：SID, SERIAL#, PADDR, XID, ...
      - SID 可直接 JOIN（不同于 Oracle 的 SES_ADDR/SADDR）
      - START_DATE 为 DATE 类型，(SYSDATE - START_DATE)*86400 可直接计算秒数
    单机或无长事务时返回 0。
    """
    sql = """
        SELECT COUNT(*)
        FROM V$TRANSACTION t
        JOIN V$SESSION s ON t.SID = s.SID
        WHERE t.STATUS = 'ACTIVE'
          AND (SYSDATE - t.START_DATE) * 86400 > 180
    """
    try:
        val = query_one(conn, sql)
        return val if val is not None else 0
    except Exception:
        # V$TRANSACTION 不存在或字段名不匹配时退化为0
        return 0


def metric_ha_sync_delay(conn):
    """主备同步延迟（gap 数量）
    通过 V$ARCHIVE_GAP 查询主库与备库之间的归档序列号间隙数量。
    YashanDB 实机验证结果（2026-04-10）：
      - V_$ARCHIVE_GAP 列：ID, LOW_SEQUENCE#, HIGH_SEQUENCE#
      - 单机（无备库）时返回空（COUNT=0），此时 sync_delay=0
      - V_$STANDBY_LOG 在 YashanDB 23.4 中不存在
      - V_$ARCHIVE_DEST_STATUS 有 RECEIVED_SEQ/APPLIED_SEQ 但单机下为空
    返回值为序列号间隙数量（>0=有延迟，0=无延迟或单机）。
    对标 YCM 指标：yashandb_sync_delay。
    """
    sql = """
        SELECT COUNT(*)
        FROM V$ARCHIVE_GAP
    """
    try:
        val = query_one(conn, sql)
        return val if val is not None else 0
    except Exception:
        # V$ARCHIVE_GAP 不存在时退化为0
        return 0


def metric_redo_log_switches(conn):
    """最近24小时 Redo 日志切换次数
    通过 V$ARCHIVED_LOG 统计近24小时内归档的日志文件数量。
    YashanDB 实机验证结果（2026-04-10）：
      - V_$ARCHIVED_LOG 列：NAME, SEQUENCE#, THREAD#, FIRST_TIME, COMPLETION_TIME, STATUS, ...
      - V_$LOG / V_$LOG_HISTORY 在 YashanDB 23.4 中不存在（使用 V_$ARCHIVED_LOG 替代）
      - V_$LOGFILE 有 SEQUENCE# 列但仅反映当前 redo 状态
      - FIRST_TIME 为归档日志的开始时间，可用于统计时间窗口内的切换次数
    若归档功能未启用或近24h无归档切换，返回 0。
    对标 YCM Redo 切换频率指标。
    """
    sql = """
        SELECT COUNT(*)
        FROM V$ARCHIVED_LOG
        WHERE FIRST_TIME >= SYSDATE - 1
    """
    try:
        val = query_one(conn, sql)
        return val if val is not None else 0
    except Exception:
        # V$ARCHIVED_LOG 不可用时退化为0
        return 0




def collect_metric(conn, metric_key):
    """根据 metric_key 调用对应采集函数"""

    # 带参数的指标（格式：metric_key[param]）
    if "[" in metric_key and metric_key.endswith("]"):
        base_key, param = metric_key[:-1].split("[", 1)
    else:
        base_key = metric_key
        param = None

    # 归一化：支持省略 "yashandb." 前缀（方便 wrapper/UserParameter 调用）
    if not base_key.startswith("yashandb."):
        base_key = "yashandb." + base_key

    dispatch = {
        # ---- 原生指标 yashandb.db.* ----
        "yashandb.db.status":                  lambda: metric_db_status(conn),
        "yashandb.db.version":                 lambda: metric_db_version(conn),
        "yashandb.db.uptime":                  lambda: metric_db_uptime(conn),
        "yashandb.db.mode":                    lambda: metric_db_mode(conn),
        "yashandb.db.sessions.active":         lambda: metric_sessions_active(conn),
        "yashandb.db.sessions.total":          lambda: metric_sessions_total(conn),
        "yashandb.db.sessions.waiting":        lambda: metric_sessions_waiting(conn),
        "yashandb.db.sessions.max":            lambda: metric_sessions_max(conn),
        "yashandb.db.memory.buffer_pool_size": lambda: metric_memory_buffer_pool_size(conn),
        "yashandb.db.memory.buffer_pool_used": lambda: metric_memory_buffer_pool_used(conn),
        "yashandb.db.memory.buffer_pool_hit":  lambda: metric_memory_buffer_pool_hit(conn),
        "yashandb.db.memory.vm_pool_size":     lambda: metric_memory_vm_pool_size(conn),
        "yashandb.db.memory.vm_pool_used":     lambda: metric_memory_vm_pool_used(conn),
        "yashandb.tablespace.discovery":       lambda: metric_tablespace_discovery(conn),
        "yashandb.db.wait_event_discovery":    lambda: metric_db_wait_event_discovery(conn),
        "yashandb.db.stat_discovery":          lambda: metric_db_stat_discovery(conn),
        "yashandb.tablespace.total":           lambda: metric_tablespace_total(conn, param),
        "yashandb.tablespace.used":            lambda: metric_tablespace_used(conn, param),
        "yashandb.tablespace.free":            lambda: metric_tablespace_free(conn, param),
        "yashandb.tablespace.pct_used":        lambda: metric_tablespace_pct_used(conn, param),
        "yashandb.db.redo.flush_speed":        lambda: metric_redo_flush_speed(conn),
        "yashandb.db.redo.free_space":         lambda: metric_redo_free_space(conn),
        "yashandb.db.redo.checkpoint_lag":     lambda: metric_redo_checkpoint_lag(conn),
        "yashandb.db.sql.executions_per_sec":  lambda: metric_sql_executions_per_sec(conn),
        "yashandb.db.sql.avg_elapsed_ms":     lambda: metric_sql_avg_elapsed_ms(conn),
        "yashandb.db.sql.slow_count":         lambda: metric_sql_slow_count(conn),
        "yashandb.db.sql.parse_count":        lambda: metric_sql_parse_count(conn),
        "yashandb.db.wait.top_event":         lambda: metric_wait_top_event(conn),
        "yashandb.db.wait.total_waits":       lambda: metric_wait_total_waits(conn),
        "yashandb.db.wait.time_waited_ms":   lambda: metric_wait_time_waited_ms(conn),
        "yashandb.db.lock.count":             lambda: metric_lock_count(conn),
        "yashandb.db.lock.blocking_sessions": lambda: metric_lock_blocking_sessions(conn),
        "yashandb.db.stat":                   lambda: metric_sysstat(conn, param),

        # ---- Datadog Oracle 兼容指标 ----
        # 会话与连接
        "yashandb.active_background":         lambda: metric_active_background(conn),
        "yashandb.active_sessions":           lambda: metric_sessions_active(conn),
        "yashandb.sessions.active_detail":    lambda: metric_session_active_detail(conn),
        "yashandb.sessions.active":           lambda: metric_sessions_active(conn),
        "yashandb.process_limit":             lambda: metric_process_limit(conn),
        "yashandb.session_count":             lambda: metric_session_count(conn),
        "yashandb.session_limit_usage":       lambda: metric_session_limit_usage(conn),
        "yashandb.user_sessions":             lambda: metric_user_sessions(conn),

        # SQL 解析与执行
        "yashandb.hard_parses":               lambda: metric_hard_parses(conn),
        "yashandb.memory_sorts_ratio":        lambda: metric_memory_sorts_ratio(conn),

        # 缓存与内存
        "yashandb.buffer_cachehit_ratio":     lambda: metric_buffer_cachehit_ratio(conn),
        "yashandb.cache_blocks_lost":         lambda: metric_cache_blocks_lost(conn),
        "yashandb.physical_memory_gb":       lambda: metric_physical_memory_gb(conn),
        "yashandb.shared_memory_size":       lambda: metric_shared_memory_size(conn),
        "yashandb.shared_pool_free":         lambda: metric_shared_pool_free(conn),

        # PGA 进程内存
        "yashandb.process.pga_allocated_memory": lambda: metric_process_pga_allocated_memory(conn),
        "yashandb.process.pga_freeable_memory":  lambda: metric_process_pga_freeable_memory(conn),
        "yashandb.process.pga_max_memory":       lambda: metric_process_pga_max_memory(conn),
        "yashandb.process.pga_used_memory":      lambda: metric_process_pga_used_memory(conn),

        # 物理 I/O
        "yashandb.physical_reads":            lambda: metric_physical_reads(conn),
        "yashandb.physical_writes":           lambda: metric_physical_writes(conn),

        # 逻辑读取
        "yashandb.consistent_read_changes":   lambda: metric_consistent_read_changes(conn),
        "yashandb.db_block_changes":          lambda: metric_db_block_changes(conn),
        "yashandb.logical_reads":             lambda: metric_logical_reads(conn),

        # 排序与扫描
        "yashandb.disk_sorts":                lambda: metric_disk_sorts(conn),
        "yashandb.sorts_per_user_call":       lambda: metric_sorts_per_user_call(conn),

        # Redo 日志
        "yashandb.redo_allocation_hit_ratio": lambda: metric_redo_allocation_hit_ratio(conn),
        "yashandb.redo_generated":            lambda: metric_redo_generated(conn),
        "yashandb.redo_writes":              lambda: metric_redo_writes(conn),

        # 事务
        "yashandb.dbwr_checkpoints":         lambda: metric_dbwr_checkpoints(conn),
        "yashandb.user_commits":             lambda: metric_user_commits(conn),
        "yashandb.user_rollbacks":           lambda: metric_user_rollbacks(conn),

        # CPU 与系统资源
        "yashandb.host_cpu_utilization":      lambda: metric_host_cpu_utilization(conn),
        "yashandb.num_cpus":                 lambda: metric_num_cpus(conn),
        "yashandb.os_load":                  lambda: metric_os_load(conn),

        # 网络与延迟
        "yashandb.avg_synchronous_single_block_read_latency":
            lambda: metric_avg_synchronous_single_block_read_latency(conn),
        "yashandb.network_traffic_volume":   lambda: metric_network_traffic_volume(conn),

        # 索引
        "yashandb.branch_node_splits":       lambda: metric_branch_node_splits(conn),
        "yashandb.leaf_node_splits":         lambda: metric_leaf_node_splits(conn),

        # 表空间（Datadog 版）
        "yashandb.tablespace.in_use":        lambda: metric_tablespace_in_use(conn),
        "yashandb.tablespace.maxsize":       lambda: metric_tablespace_maxsize(conn),
        "yashandb.tablespace.offline":       lambda: metric_tablespace_offline(conn),
        "yashandb.tablespace.size":          lambda: metric_tablespace_size(conn),
        "yashandb.tablespace.used":          lambda: metric_tablespace_used(conn),
        "yashandb.tablespace.total":         lambda: metric_tablespace_total(conn, param),
        "yashandb.tablespace.free":          lambda: metric_tablespace_free(conn, param),
        "yashandb.tablespace.pct_used":      lambda: metric_tablespace_pct_used(conn, param),

        # 全局缓存 RAC
        "yashandb.gc_average_cr_get_time":       lambda: metric_gc_average_cr_get_time(conn),
        "yashandb.gc_average_current_get_time":  lambda: metric_gc_average_current_get_time(conn),

        # ---- v2.1 新增：长事务 / 主备延迟 / Redo 切换 ----
        "yashandb.db.long_transactions":         lambda: metric_long_transactions(conn),
        "yashandb.db.ha.sync_delay":             lambda: metric_ha_sync_delay(conn),
        "yashandb.db.redo.log_switches":         lambda: metric_redo_log_switches(conn),

        # ---- v2.2 新增：New Relic Oracle 指标适配 ----
        # 等待事件
        "yashandb.db.wait_top_event":            lambda: metric_db_wait_top_event(conn),
        "yashandb.db.wait_event_waits":          lambda: metric_db_wait_event_waits(conn, param),
        "yashandb.db.wait_event_time":           lambda: metric_db_wait_event_time(conn, param),
        "yashandb.db.waits_total":               lambda: metric_db_wait_events_count(conn),
        "yashandb.db.wait_time_total":           lambda: metric_db_wait_time_total(conn),
        "yashandb.db.wait_time_ratio":           lambda: metric_db_wait_time_ratio(conn),

        # SGA 缓冲区指标
        "yashandb.sga.buffer_busy_waits":        lambda: metric_sga_buffer_busy_waits(conn),
        "yashandb.sga.free_buffer_waits":       lambda: metric_sga_free_buffer_waits(conn),
        "yashandb.sga.free_buffer_inspected":    lambda: metric_sga_free_buffer_inspected(conn),
        "yashandb.sga.fixed_size":               lambda: metric_sga_fixed_size(conn),
        "yashandb.sga.redo_buffers":             lambda: metric_sga_redo_buffers(conn),
        "yashandb.sga.log_buffer_space_waits":   lambda: metric_sga_log_buffer_space_waits(conn),

        # 磁盘 I/O（FILESTAT）
        "yashandb.disk.total_reads":             lambda: metric_disk_total_reads(conn),
        "yashandb.disk.total_writes":            lambda: metric_disk_total_writes(conn),
        "yashandb.disk.total_read_time":         lambda: metric_disk_total_read_time(conn),
        "yashandb.disk.total_write_time":        lambda: metric_disk_total_write_time(conn),

        # 会话增强
        "yashandb.sessions.inactive":           lambda: metric_session_inactive(conn),
        "yashandb.sessions.background":          lambda: metric_session_background(conn),

        # Redo 日志增强
        "yashandb.redo.waits":                  lambda: metric_redolog_waits(conn),
        "yashandb.redo.switch_checkpoint":      lambda: metric_redolog_switch_checkpoint_incomplete(conn),

        # 库缓存/字典缓存（N/A）
        "yashandb.library_cache_hit_ratio":     lambda: metric_library_cache_hit_ratio(conn),
        "yashandb.library_cache_reload_ratio":  lambda: metric_library_cache_reload_ratio(conn),
        "yashandb.row_cache_hit_ratio":          lambda: metric_row_cache_hit_ratio(conn),

        # 回滚段（N/A）
        "yashandb.rollback.gets":                lambda: metric_rollback_gets(conn),
        "yashandb.rollback.waits":               lambda: metric_rollback_waits(conn),
        "yashandb.rollback.ratio_wait":           lambda: metric_rollback_ratio_wait(conn),

        # Top SQL
        "yashandb.sql.top_buffer_gets":          lambda: metric_top_sql_buffer_gets(conn),
        "yashandb.sql.top_disk_reads":           lambda: metric_top_sql_disk_reads(conn),
        "yashandb.sql.count":                    lambda: metric_sql_count(conn),

        # 数据库综合
        "yashandb.db.current_logons":            lambda: metric_db_current_logons(conn),
        "yashandb.db.open_cursors":              lambda: metric_db_open_cursors(conn),
        "yashandb.db.user_limit_pct":            lambda: metric_db_user_limit_pct(conn),
        "yashandb.db.process_limit_pct":          lambda: metric_db_process_limit_pct(conn),
        "yashandb.db.session_limit_pct":          lambda: metric_db_session_limit_pct(conn),

        # 表空间增强
        "yashandb.tablespace.offline_count":      lambda: metric_tablespace_offline_count(conn),
        "yashandb.tablespace.datafile_offline_count": lambda: metric_datafile_offline_count(conn),

        # 归档日志
        "yashandb.archived_log.count":            lambda: metric_archived_log_count(conn),
        "yashandb.archived_log.first_time":      lambda: metric_archived_log_first_time(conn),

        # 锁
        "yashandb.lock.enqueue_locks":           lambda: metric_enqueued_locks(conn),
        "yashandb.lock.enqueue_requests":         lambda: metric_enqueued_requests(conn),

        # 归档器
        "yashandb.archiver.failed":              lambda: metric_archiver_failed(conn),

        # ---- v2.3 新增：Nagios check_oracle_health 适配指标 ----
        "yashandb.db.invalid_objects":           lambda: metric_invalid_objects(conn),
        "yashandb.db.invalid_indexes":          lambda: metric_invalid_indexes(conn),
        "yashandb.db.stale_statistics":          lambda: metric_stale_statistics(conn),
        "yashandb.db.soft_parse_ratio":         lambda: metric_soft_parse_ratio(conn),
        "yashandb.db.tablespace_remaining_days": lambda: metric_tablespace_remaining_days(conn),
        "yashandb.db.datafile_max_usage_pct":   lambda: metric_datafile_max_usage_pct(conn),
        "yashandb.db.dbms_stats_available":      lambda: metric_dbms_stats_available(conn),
        "yashandb.segment.total_count":         lambda: metric_segment_total_count(conn),
        "yashandb.segment.top_tablespace":      lambda: metric_segment_top_tablespace(conn),

        # ---- v2.4 新增 Phase 1 ----
        "yashandb.db.qps":                    lambda: metric_db_qps(conn),
        "yashandb.db.tps":                    lambda: metric_db_tps(conn),
        "yashandb.archived_log.count_today":   lambda: metric_archived_log_count_today(conn),
        "yashandb.wait_class.discovery":        lambda: metric_wait_class_discovery(conn),
        "yashandb.db.wait_class.count":        lambda: metric_wait_class_count(conn, param),
        "yashandb.db.wait_class.time":          lambda: metric_wait_class_time(conn, param),
        "yashandb.tablespace.by_type":         lambda: metric_tablespace_by_type(conn, param),
        "yashandb.tablespace.temp_usage_pct":  lambda: metric_tablespace_temp_usage_pct(conn),
        "yashandb.tablespace.undo_usage_pct":  lambda: metric_tablespace_undo_usage_pct(conn),
        "yashandb.sql.top_buffer_gets_sql":     lambda: metric_sql_top_buffer_gets_sql(conn),
        "yashandb.sql.top_disk_reads_sql":      lambda: metric_sql_top_disk_reads_sql(conn),
        "yashandb.sql.top_executions_sql":     lambda: metric_sql_top_executions_sql(conn),
        "yashandb.resource_limit.usage_pct":    lambda: metric_resource_limit_usage_pct(conn),

        # ---- v2.5 新增 Phase 2 ----
        "yashandb.sql.p95_elapsed_ms":         lambda: metric_sql_p95_elapsed_ms(conn),
        "yashandb.sql.p99_elapsed_ms":         lambda: metric_sql_p99_elapsed_ms(conn),
        "yashandb.session.user.discovery":      lambda: metric_session_user_discovery(conn),
        "yashandb.session.by_user":            lambda: metric_session_by_user(conn, param),
        "yashandb.session.program.discovery":   lambda: metric_session_program_discovery(conn),
        "yashandb.session.by_program":          lambda: metric_session_by_program(conn, param),
        "yashandb.invalid_objects.by_type.discovery": lambda: metric_invalid_objects_by_type_discovery(conn),
        "yashandb.invalid_objects.by_type":    lambda: metric_invalid_objects_by_type(conn, param),
        "yashandb.datafile.non_autoextend_count": lambda: metric_datafile_non_autoextend_count(conn),
        "yashandb.user.expiring_soon_count":   lambda: metric_user_expiring_soon_count(conn),
        "yashandb.db.statistics_level":         lambda: metric_db_statistics_level(conn),
    }

    if base_key not in dispatch:
        raise ValueError(f"未知的监控指标: {metric_key}\n\n{METRIC_HELP}")

    return dispatch[base_key]()


# -------------------------------------------------------
# 主入口
# -------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="YashanDB Zabbix Monitor Plugin v2.5.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=METRIC_HELP
    )
    parser.add_argument("--host",     required=False, default=None, help="YashanDB 主机地址（可从 --config 读取）")
    parser.add_argument("--port",     required=False, default=None,
                        help="YashanDB 端口（默认 1688，可从 --config 读取）")
    parser.add_argument("--user",     required=False, default=None, help="数据库用户名（可从 --config 读取）")
    parser.add_argument("--password", required=False, default=None, help="数据库密码（可从 --config 读取）")
    parser.add_argument("--metric",   required=True,  help="监控指标 key")
    parser.add_argument("--timeout",  required=False, default="10",
                        help="连接超时秒数（默认 10）")
    parser.add_argument("--config",   required=False, default=None,
                        help="连接配置文件路径（INI格式），优先级低于命令行参数")
    return parser.parse_args()


def load_config(config_path):
    """从 INI 配置文件加载连接参数"""
    import configparser
    cfg = configparser.ConfigParser()
    cfg.read(config_path, encoding="utf-8")
    section = "yashandb"
    if section not in cfg:
        return {}
    return dict(cfg[section])


def main():
    args = parse_args()

    config = {}
    if args.config and os.path.isfile(args.config):
        config = load_config(args.config)

    host     = args.host     or config.get("host", "127.0.0.1")
    port     = args.port     or config.get("port", "1688")
    user     = args.user     or config.get("user", "sys")
    password = args.password or config.get("password", "")
    if not host or not user or not password:
        print("ERROR: host/user/password required (via --host/--user/--password or --config)", file=sys.stderr)
        sys.exit(1)
    metric   = args.metric

    conn = None
    try:
        try:
            conn = get_connection(host, port, user, password)
        except Exception as e:
            if metric == "yashandb.db.status":
                print(0)
                return
            raise

        result = collect_metric(conn, metric)

        if result is None:
            print(0)
        else:
            print(result)

    except Exception as e:
        sys.stderr.write(f"ERROR: {e}\n")
        if metric == "yashandb.db.status":
            print(0)
        else:
            print("ZBX_NOTSUPPORTED")
        sys.exit(1)
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YashanDB Zabbix 批量采集脚本
一次性采集所有常用指标并输出为 JSON，用于 Zabbix Trapper 或调试诊断

用法:
    python yashandb_bulk.py --host 127.0.0.1 --port 1688 \
        --user sys --password yasdb_123

支持全部 125 个监控指标（含 42 个 Datadog Oracle 兼容 + 3 个 v2.1 YCM 对标 + 41 个 v2.2 New Relic 适配 + 9 个 v2.3 Nagios 适配）
"""

import argparse
import json
import sys
import os

# 将 scripts 目录加入模块路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yashandb_monitor import get_connection, collect_metric


# 全部可批量采集的指标（v2.3，共 125 个）
BULK_METRICS = [
    # ---- 原生指标 yashandb.db.* ----
    "yashandb.db.status",
    "yashandb.db.version",
    "yashandb.db.uptime",
    "yashandb.db.mode",
    "yashandb.db.sessions.active",
    "yashandb.db.sessions.total",
    "yashandb.db.sessions.waiting",
    "yashandb.db.sessions.max",
    "yashandb.db.memory.buffer_pool_size",
    "yashandb.db.memory.buffer_pool_used",
    "yashandb.db.memory.buffer_pool_hit",
    "yashandb.db.memory.vm_pool_size",
    "yashandb.db.memory.vm_pool_used",
    "yashandb.db.redo.flush_speed",
    "yashandb.db.redo.free_space",
    "yashandb.db.redo.checkpoint_lag",
    "yashandb.db.sql.executions_per_sec",
    "yashandb.db.sql.avg_elapsed_ms",
    "yashandb.db.sql.slow_count",
    "yashandb.db.sql.parse_count",
    "yashandb.db.wait.top_event",
    "yashandb.db.wait.total_waits",
    "yashandb.db.wait.time_waited_ms",
    "yashandb.db.lock.count",
    "yashandb.db.lock.blocking_sessions",

    # 原生表空间（LLD + 无参数版本）
    "yashandb.db.tablespace.discovery",   # 表空间 LLD 自动发现

    # ---- Datadog Oracle 兼容指标 ----
    # 会话与连接
    "yashandb.active_background",
    "yashandb.active_sessions",
    "yashandb.process_limit",
    "yashandb.session_count",
    "yashandb.session_limit_usage",
    "yashandb.user_sessions",

    # SQL 解析与执行
    "yashandb.hard_parses",
    "yashandb.memory_sorts_ratio",

    # 缓存与内存
    "yashandb.buffer_cachehit_ratio",
    "yashandb.cache_blocks_lost",
    "yashandb.physical_memory_gb",
    "yashandb.shared_memory_size",
    "yashandb.shared_pool_free",

    # PGA 进程内存
    "yashandb.process.pga_allocated_memory",
    "yashandb.process.pga_freeable_memory",
    "yashandb.process.pga_max_memory",
    "yashandb.process.pga_used_memory",

    # 物理 I/O
    "yashandb.physical_reads",
    "yashandb.physical_writes",

    # 逻辑读取
    "yashandb.consistent_read_changes",
    "yashandb.db_block_changes",
    "yashandb.logical_reads",

    # 排序与扫描
    "yashandb.disk_sorts",
    "yashandb.sorts_per_user_call",

    # Redo 日志
    "yashandb.redo_allocation_hit_ratio",
    "yashandb.redo_generated",
    "yashandb.redo_writes",

    # 事务
    "yashandb.dbwr_checkpoints",
    "yashandb.user_commits",
    "yashandb.user_rollbacks",

    # CPU 与系统资源
    "yashandb.host_cpu_utilization",
    "yashandb.num_cpus",
    "yashandb.os_load",

    # 网络与延迟
    "yashandb.avg_synchronous_single_block_read_latency",
    "yashandb.network_traffic_volume",

    # 索引
    "yashandb.branch_node_splits",
    "yashandb.leaf_node_splits",

    # 表空间（Datadog 版，9个无参指标）
    "yashandb.tablespace.discovery",   # LLD 自动发现
    "yashandb.tablespace.in_use",       # 全库使用率(%)
    "yashandb.tablespace.maxsize",      # 最大容量(字节)
    "yashandb.tablespace.offline",      # 离线表空间数量
    "yashandb.tablespace.size",         # 当前总大小(字节)
    "yashandb.tablespace.used",         # 已使用字节数

    # 全局缓存 RAC（单机=0）
    "yashandb.gc_average_cr_get_time",
    "yashandb.gc_average_current_get_time",

    # ---- v2.1 新增：YCM 对标指标 ----
    "yashandb.db.long_transactions",     # 超过3分钟的活跃事务数
    "yashandb.db.ha.sync_delay",         # 主备同步延迟（秒，单机=0）
    "yashandb.db.redo.log_switches",     # 近24小时 Redo 日志切换次数

    # ---- v2.2 新增：New Relic Oracle 适配指标 ----
    # 等待事件（5 个）
    "yashandb.db.wait_top_event",         # TOP 等待事件名称
    "yashandb.db.waits_total",            # 总会话等待次数
    "yashandb.db.wait_time_total",        # 总会话等待时间（秒）

    # SGA Buffer（6 个）
    "yashandb.sga.buffer_busy_waits",     # Buffer Busy Waits
    "yashandb.sga.free_buffer_waits",     # Free Buffer Waits
    "yashandb.sga.free_buffer_inspected", # Free Buffer Inspected
    "yashandb.sga.fixed_size",            # SGA Fixed Size
    "yashandb.sga.redo_buffers",          # Redo Buffers
    "yashandb.sga.log_buffer_space_waits", # Log Buffer Space Waits

    # 物理 I/O FILESTAT（4 个）
    "yashandb.disk.total_reads",          # 物理读取总次数
    "yashandb.disk.total_writes",         # 物理写入总次数
    "yashandb.disk.total_read_time",      # 物理读取总时间（秒）
    "yashandb.disk.total_write_time",     # 物理写入总时间（秒）

    # 会话增强（3 个）
    "yashandb.sessions.inactive",         # 非活跃会话数
    "yashandb.sessions.background",        # 后台会话数
    "yashandb.sessions.active_detail",    # 活跃会话数

    # Redo 增强（2 个）
    "yashandb.redo.waits",                # Redo 日志等待次数
    "yashandb.redo.switch_checkpoint",    # Redo 切换触发检查点

    # N/A 标记指标（6 个，返回 0 或 NULL）
    "yashandb.library_cache_hit_ratio",   # N/A - V$LIBRARYCACHE 不存在
    "yashandb.library_cache_reload_ratio", # N/A - V$LIBRARYCACHE 不存在
    "yashandb.row_cache_hit_ratio",       # N/A - V$ROWCACHE 不存在
    "yashandb.rollback.gets",             # N/A - V$ROLLSTAT 不存在
    "yashandb.rollback.waits",           # N/A - V$ROLLSTAT 不存在
    "yashandb.rollback.ratio_wait",      # N/A - V$ROLLSTAT 不存在

    # Top SQL（3 个）
    "yashandb.sql.top_buffer_gets",       # Top SQL by Buffer Gets
    "yashandb.sql.top_disk_reads",        # Top SQL by Disk Reads
    "yashandb.sql.count",                 # 共享池 SQL 语句总数

    # DB 常规（5 个）
    "yashandb.db.current_logons",         # 当前登录数
    "yashandb.db.open_cursors",          # 打开游标数
    "yashandb.db.user_limit_pct",        # 用户会话限制使用率
    "yashandb.db.process_limit_pct",     # 进程限制使用率
    "yashandb.db.session_limit_pct",     # 会话限制使用率

    # 表空间增强（2 个）
    "yashandb.tablespace.offline_count",       # 离线表空间数量
    "yashandb.tablespace.datafile_offline_count", # 离线数据文件数量

    # 归档日志（2 个）
    "yashandb.archived_log.count",         # 近24h 归档日志数量
    "yashandb.archived_log.first_time",   # 最新归档日志时间

    # 锁（2 个）
    "yashandb.lock.enqueue_locks",        # Enqueue 锁数量
    "yashandb.lock.enqueue_requests",     # Enqueue 锁请求次数

    # 归档进程（1 个）
    "yashandb.archiver.failed",           # 归档进程失败次数

    # ---- v2.3 新增：Nagios check_oracle_health 适配指标 ----
    # 数据质量检查
    "yashandb.db.invalid_objects",        # 无效数据库对象数量
    "yashandb.db.invalid_indexes",        # 无效索引数量
    "yashandb.db.stale_statistics",       # 统计信息陈旧的表数量

    # SQL 解析
    "yashandb.db.soft_parse_ratio",      # 软解析比率（%）

    # 表空间管理
    "yashandb.db.tablespace_remaining_days",  # 表空间剩余天数（基于增长趋势）
    "yashandb.db.datafile_max_usage_pct",    # 数据文件最大容量使用率（%）

    # 统计信息包
    "yashandb.db.dbms_stats_available",   # DBMS_STATS 包是否可用

    # 段管理
    "yashandb.segment.total_count",      # 段总数
    "yashandb.segment.top_tablespace",   # 占用空间最大的表空间
]


def main():
    parser = argparse.ArgumentParser(
        description="YashanDB Zabbix 批量采集 v2.3（支持 125 个指标）")
    parser.add_argument("--host",     required=True)
    parser.add_argument("--port",     default="1688")
    parser.add_argument("--user",     required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--json",     action="store_true",
                        help="以 JSON 格式输出（默认 key=value）")
    args = parser.parse_args()

    results = {}
    errors = {}

    try:
        conn = get_connection(args.host, args.port, args.user, args.password)
    except Exception as e:
        print(json.dumps({"error": str(e), "yashandb.db.status": 0}))
        sys.exit(1)

    for metric in BULK_METRICS:
        try:
            val = collect_metric(conn, metric)
            results[metric] = val if val is not None else 0
        except Exception as e:
            errors[metric] = str(e)
            results[metric] = "ERROR"

    try:
        conn.close()
    except Exception:
        pass

    if args.json:
        output = {"metrics": results}
        if errors:
            output["errors"] = errors
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        for k, v in results.items():
            print(f"{k} = {v}")
        if errors:
            print("\n--- ERRORS ---", file=sys.stderr)
            for k, v in errors.items():
                print(f"{k}: {v}", file=sys.stderr)


if __name__ == "__main__":
    main()

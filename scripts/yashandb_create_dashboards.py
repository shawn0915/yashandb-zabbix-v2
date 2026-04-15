#!/usr/bin/env python3
"""
YashanDB Zabbix Dashboard Creator - Zabbix 7.x API
"""
import argparse, json, sys, time

try:
    from zabbix_api import ZabbixAPI
except ImportError:
    print("ERROR: 需要 zabbix-api: pip install zabbix-api")
    sys.exit(1)

# ── 配色 ─────────────────────────────────────────────────────────────────────
LINE_COLORS = [
    "#1E88E5", "#43A047", "#FB8C00", "#E53935",
    "#8E24AA", "#00ACC1", "#FDD835", "#6D4C41",
    "#546E7A", "#D81B60",
]
STACK_COLORS = ["#1E88E5", "#43A047", "#FB8C00", "#E53935", "#8E24AA", "#00ACC1"]

# 全局 widget 序号（用于 reference）
_wid_counter = [0]

def _next_ref():
    _wid_counter[0] += 1
    # 生成 5 位字母引用码（Zabbix 惯例：AAAAA, AAAB, AAAC...）
    n = _wid_counter[0]
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    result = ""
    for _ in range(5):
        result = letters[n % 26] + result
        n = n // 26
    return result

def _next_wid():
    _wid_counter[0] += 1
    return _wid_counter[0]

# ─────────────────────────────────────────────────────────────────────────────
# 核心：构建 SVG Graph widget
# items: [{"key": "yashandb.db.status", "host": "yas-zabbix-agent"}, ...]
# single_item: {"key": "...", "host": "..."} (无 legend 时单指标)
# ─────────────────────────────────────────────────────────────────────────────
def svg_graph(name, items, width=12, height=5, x=0, y=0,
              show_legend=True, stacked=False, thresholds=None):
    """
    Zabbix 7.x SVG Graph widget。
    字段格式对照 Zabbix 自带 dashboard 真实结构。
    """
    wid = _next_wid()
    fields = []

    # Data source fields: ds.0.hosts.0, ds.0.items.0, ds.0.color, ds.0.transparency
    colors = LINE_COLORS if not stacked else STACK_COLORS
    for i, it in enumerate(items):
        color = it.get("color") or colors[i % len(colors)]
        fields.append({"type": 1, "name": f"ds.{i}.hosts.0", "value": it.get("host", "")})
        fields.append({"type": 1, "name": f"ds.{i}.items.0", "value": it.get("key", "")})
        fields.append({"type": 1, "name": f"ds.{i}.color", "value": color})
        fields.append({"type": 0, "name": f"ds.{i}.transparency", "value": 0})

    # Display settings
    fields.append({"type": 0, "name": "lefty", "value": 0})
    fields.append({"type": 0, "name": "righty", "value": 0})
    fields.append({"type": 0, "name": "axisx", "value": 0})
    fields.append({"type": 0, "name": "legend", "value": 1 if show_legend else 0})
    fields.append({"type": 0, "name": "show_problems", "value": 0})

    # Stacked mode
    if stacked:
        fields.append({"type": 0, "name": "stacked", "value": 1})

    # Reference (required)
    ref = _next_ref()
    fields.append({"type": 1, "name": "reference", "value": ref})

    # Time period
    fields.append({"type": 1, "name": "time_period.from", "value": "now-1h"})
    fields.append({"type": 1, "name": "time_period.to", "value": "now"})

    # Thresholds (if any)
    if thresholds:
        for t in thresholds:
            fields.append({"type": 1, "name": "thresholds.color", "value": t["color"]})
            fields.append({"type": 0, "name": "thresholds.value", "value": t["value"]})

    return {
        "type": "svggraph",
        "name": name,
        "x": x, "y": y,
        "width": width, "height": height,
        "view_mode": 0,
        "fields": fields
    }


def nav_history(width=24, height=3, x=0, y=0):
    """导航树 widget"""
    return {
        "type": "navtree",
        "name": "Navigation history",
        "x": x, "y": y,
        "width": width, "height": height,
        "view_mode": 0,
        "fields": []
    }


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard 1: YashanDB 概览
# ─────────────────────────────────────────────────────────────────────────────
def build_overview(host="yas-zabbix-agent"):
    """Oracle OEM 风格概览"""
    _ = host  # 保留参数（未来可扩展）
    return {
        "name": "YashanDB 概览",
                "display_period": 30,
        "auto_start": 1,
        "pages": [{
            "name": "",
            "display_period": 30,
            "widgets": [
                # 第一行：5 KPI
                svg_graph("数据库状态 (1=OK)",
                    [{"key": "yashandb.db.status", "host": "yas-zabbix-agent"}],
                    width=4, height=3, x=0, y=0,
                    show_legend=False),
                svg_graph("QPS",
                    [{"key": "yashandb.db.qps", "host": "yas-zabbix-agent"}],
                    width=4, height=3, x=4, y=0,
                    show_legend=False),
                svg_graph("活跃/总会话",
                    [{"key": "yashandb.db.sessions.active", "host": "yas-zabbix-agent", "color": LINE_COLORS[0]},
                     {"key": "yashandb.db.sessions.total", "host": "yas-zabbix-agent", "color": LINE_COLORS[1]}],
                    width=4, height=3, x=8, y=0),
                svg_graph("表空间使用率 (%)",
                    [{"key": "yashandb.tablespace.in_use", "host": "yas-zabbix-agent"}],
                    width=4, height=3, x=12, y=0,
                    show_legend=False),
                svg_graph("缓冲池命中率 (%)",
                    [{"key": "yashandb.db.memory.buffer_pool_hit", "host": "yas-zabbix-agent"}],
                    width=4, height=3, x=16, y=0,
                    show_legend=False),

                # 第二行：QPS/TPS + 会话趋势
                svg_graph("QPS / TPS 趋势",
                    [{"key": "yashandb.db.qps", "host": "yas-zabbix-agent", "color": LINE_COLORS[0]},
                     {"key": "yashandb.db.tps", "host": "yas-zabbix-agent", "color": LINE_COLORS[1]}],
                    width=12, height=5, x=0, y=3),
                svg_graph("会话趋势",
                    [{"key": "yashandb.db.sessions.active", "host": "yas-zabbix-agent", "color": LINE_COLORS[0]},
                     {"key": "yashandb.db.sessions.waiting", "host": "yas-zabbix-agent", "color": LINE_COLORS[2]},
                     {"key": "yashandb.session.inactive", "host": "yas-zabbix-agent", "color": LINE_COLORS[3]}],
                    width=8, height=5, x=12, y=3),

                # 第三行：内存 + SQL
                svg_graph("Buffer Pool 使用量",
                    [{"key": "yashandb.db.memory.buffer_pool_used", "host": "yas-zabbix-agent", "color": LINE_COLORS[0]},
                     {"key": "yashandb.db.memory.buffer_pool_size", "host": "yas-zabbix-agent", "color": LINE_COLORS[1]}],
                    width=8, height=5, x=0, y=8),
                svg_graph("SQL 执行趋势",
                    [{"key": "yashandb.db.sql.executions_per_sec", "host": "yas-zabbix-agent", "color": LINE_COLORS[0]},
                     {"key": "yashandb.db.sql.slow_count", "host": "yas-zabbix-agent", "color": LINE_COLORS[2]}],
                    width=6, height=5, x=8, y=8),
                svg_graph("VM Pool",
                    [{"key": "yashandb.db.memory.vm_pool_used", "host": "yas-zabbix-agent", "color": LINE_COLORS[0]},
                     {"key": "yashandb.db.memory.vm_pool_size", "host": "yas-zabbix-agent", "color": LINE_COLORS[1]}],
                    width=6, height=5, x=14, y=8),

                # 第四行：等待 + 锁
                svg_graph("等待时间趋势",
                    [{"key": "yashandb.db.wait.time_waited_ms", "host": "yas-zabbix-agent", "color": LINE_COLORS[0]},
                     {"key": "yashandb.db.wait.total_waits", "host": "yas-zabbix-agent", "color": LINE_COLORS[1]}],
                    width=12, height=5, x=0, y=13),
                svg_graph("锁统计",
                    [{"key": "yashandb.db.lock.count", "host": "yas-zabbix-agent", "color": LINE_COLORS[0]},
                     {"key": "yashandb.db.lock.blocking_sessions", "host": "yas-zabbix-agent", "color": LINE_COLORS[2]}],
                    width=8, height=5, x=12, y=13),
            ]
        }]
    }


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard 2: YashanDB 性能
# ─────────────────────────────────────────────────────────────────────────────
def build_performance(host="yas-zabbix-agent"):
    """AWR 报告风格性能页"""
    return {
        "name": "YashanDB 性能",
                "display_period": 30,
        "auto_start": 1,
        "pages": [{
            "name": "",
            "display_period": 30,
            "widgets": [
                # 第一行：5 KPI
                svg_graph("QPS",
                    [{"key": "yashandb.db.qps", "host": "yas-zabbix-agent"}],
                    width=4, height=3, x=0, y=0, show_legend=False),
                svg_graph("TPS",
                    [{"key": "yashandb.db.tps", "host": "yas-zabbix-agent"}],
                    width=4, height=3, x=4, y=0, show_legend=False),
                svg_graph("平均响应时间 (ms)",
                    [{"key": "yashandb.db.sql.avg_elapsed_ms", "host": "yas-zabbix-agent"}],
                    width=4, height=3, x=8, y=0, show_legend=False),
                svg_graph("P95 延迟 (ms)",
                    [{"key": "yashandb.sql.p95_elapsed_ms", "host": "yas-zabbix-agent"}],
                    width=4, height=3, x=12, y=0, show_legend=False),
                svg_graph("P99 延迟 (ms)",
                    [{"key": "yashandb.sql.p99_elapsed_ms", "host": "yas-zabbix-agent"}],
                    width=4, height=3, x=16, y=0, show_legend=False),

                # 第二行
                svg_graph("软解析比率 (%)",
                    [{"key": "yashandb.db.soft_parse_ratio", "host": "yas-zabbix-agent"}],
                    width=6, height=5, x=0, y=3, show_legend=False),
                svg_graph("慢查询计数",
                    [{"key": "yashandb.db.sql.slow_count", "host": "yas-zabbix-agent"}],
                    width=6, height=5, x=6, y=3, show_legend=False),
                svg_graph("Buffer Pool 命中率 (%)",
                    [{"key": "yashandb.db.memory.buffer_pool_hit", "host": "yas-zabbix-agent"}],
                    width=8, height=5, x=12, y=3, show_legend=False),

                # 第三行
                svg_graph("等待时间与次数",
                    [{"key": "yashandb.db.wait.time_waited_ms", "host": "yas-zabbix-agent", "color": LINE_COLORS[0]},
                     {"key": "yashandb.db.wait.total_waits", "host": "yas-zabbix-agent", "color": LINE_COLORS[1]}],
                    width=12, height=5, x=0, y=8),
                svg_graph("单块读延迟 (ms)",
                    [{"key": "yashandb.avg_synchronous_single_block_read_latency", "host": "yas-zabbix-agent"}],
                    width=8, height=5, x=12, y=8, show_legend=False),

                # 第四行
                svg_graph("物理读/写次数趋势",
                    [{"key": "yashandb.disk.total_reads", "host": "yas-zabbix-agent", "color": LINE_COLORS[0]},
                     {"key": "yashandb.disk.total_writes", "host": "yas-zabbix-agent", "color": LINE_COLORS[1]}],
                    width=10, height=5, x=0, y=13),
                svg_graph("物理 I/O 时间 (ms)",
                    [{"key": "yashandb.disk.total_read_time", "host": "yas-zabbix-agent", "color": LINE_COLORS[0]},
                     {"key": "yashandb.disk.total_write_time", "host": "yas-zabbix-agent", "color": LINE_COLORS[1]}],
                    width=10, height=5, x=10, y=13),
            ]
        }]
    }


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard 3: YashanDB 会话
# ─────────────────────────────────────────────────────────────────────────────
def build_sessions(host="yas-zabbix-agent"):
    """会话管理页"""
    return {
        "name": "YashanDB 会话",
                "display_period": 30,
        "auto_start": 1,
        "pages": [{
            "name": "",
            "display_period": 30,
            "widgets": [
                # 第一行：4 KPI
                svg_graph("活跃会话",
                    [{"key": "yashandb.db.sessions.active", "host": "yas-zabbix-agent"}],
                    width=5, height=3, x=0, y=0, show_legend=False),
                svg_graph("等待会话",
                    [{"key": "yashandb.db.sessions.waiting", "host": "yas-zabbix-agent"}],
                    width=5, height=3, x=5, y=0, show_legend=False),
                svg_graph("非活跃会话",
                    [{"key": "yashandb.session.inactive", "host": "yas-zabbix-agent"}],
                    width=5, height=3, x=10, y=0, show_legend=False),
                svg_graph("后台会话",
                    [{"key": "yashandb.session.background", "host": "yas-zabbix-agent"}],
                    width=5, height=3, x=15, y=0, show_legend=False),

                # 第二行
                svg_graph("会话类型趋势（堆叠）",
                    [{"key": "yashandb.db.sessions.active", "host": "yas-zabbix-agent", "color": LINE_COLORS[0]},
                     {"key": "yashandb.db.sessions.waiting", "host": "yas-zabbix-agent", "color": LINE_COLORS[2]},
                     {"key": "yashandb.session.inactive", "host": "yas-zabbix-agent", "color": LINE_COLORS[1]},
                     {"key": "yashandb.session.background", "host": "yas-zabbix-agent", "color": LINE_COLORS[3]}],
                    width=12, height=5, x=0, y=3, stacked=True),
                svg_graph("资源限制使用率",
                    [{"key": "yashandb.db.process_limit_pct", "host": "yas-zabbix-agent", "color": LINE_COLORS[0]},
                     {"key": "yashandb.db.session_limit_pct", "host": "yas-zabbix-agent", "color": LINE_COLORS[1]}],
                    width=8, height=5, x=12, y=3),

                # 第三行
                svg_graph("锁统计趋势",
                    [{"key": "yashandb.db.lock.count", "host": "yas-zabbix-agent", "color": LINE_COLORS[0]},
                     {"key": "yashandb.db.lock.blocking_sessions", "host": "yas-zabbix-agent", "color": LINE_COLORS[2]},
                     {"key": "yashandb.enqueue.locks", "host": "yas-zabbix-agent", "color": LINE_COLORS[1]},
                     {"key": "yashandb.enqueue.requests", "host": "yas-zabbix-agent", "color": LINE_COLORS[3]}],
                    width=12, height=5, x=0, y=8),
                svg_graph("长事务数",
                    [{"key": "yashandb.db.long_transactions", "host": "yas-zabbix-agent"}],
                    width=8, height=5, x=12, y=8, show_legend=False),

                # 第四行
                svg_graph("Top SQL - Buffer Gets",
                    [{"key": "yashandb.sql.top_buffer_gets", "host": "yas-zabbix-agent"}],
                    width=8, height=5, x=0, y=13, show_legend=False),
                svg_graph("Top SQL - Disk Reads",
                    [{"key": "yashandb.sql.top_disk_reads", "host": "yas-zabbix-agent"}],
                    width=8, height=5, x=8, y=13, show_legend=False),
                svg_graph("会话限制使用率",
                    [{"key": "yashandb.db.session_limit_pct", "host": "yas-zabbix-agent"}],
                    width=4, height=5, x=16, y=13, show_legend=False),
            ]
        }]
    }


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard 4: YashanDB 存储
# ─────────────────────────────────────────────────────────────────────────────
def build_storage(host="yas-zabbix-agent"):
    """容量规划存储页"""
    return {
        "name": "YashanDB 存储",
                "display_period": 30,
        "auto_start": 1,
        "pages": [{
            "name": "",
            "display_period": 30,
            "widgets": [
                # 第一行：5 KPI
                svg_graph("表空间使用率（全库）",
                    [{"key": "yashandb.tablespace.in_use", "host": "yas-zabbix-agent"}],
                    width=4, height=3, x=0, y=0, show_legend=False),
                svg_graph("临时表空间使用率",
                    [{"key": "yashandb.tablespace.temp_usage_pct", "host": "yas-zabbix-agent"}],
                    width=4, height=3, x=4, y=0, show_legend=False),
                svg_graph("Undo 表空间使用率",
                    [{"key": "yashandb.tablespace.undo_usage_pct", "host": "yas-zabbix-agent"}],
                    width=4, height=3, x=8, y=0, show_legend=False),
                svg_graph("剩余可用天数",
                    [{"key": "yashandb.db.tablespace_remaining_days", "host": "yas-zabbix-agent"}],
                    width=4, height=3, x=12, y=0, show_legend=False),
                svg_graph("总容量 / 最大容量",
                    [{"key": "yashandb.tablespace.size", "host": "yas-zabbix-agent", "color": LINE_COLORS[0]},
                     {"key": "yashandb.tablespace.maxsize", "host": "yas-zabbix-agent", "color": LINE_COLORS[1]}],
                    width=4, height=3, x=16, y=0),

                # 第二行
                svg_graph("表空间类型容量（堆叠）",
                    [{"key": "yashandb.tablespace.by_type[PERMANENT]", "host": "yas-zabbix-agent", "color": LINE_COLORS[0]},
                     {"key": "yashandb.tablespace.by_type[TEMPORARY]", "host": "yas-zabbix-agent", "color": LINE_COLORS[1]},
                     {"key": "yashandb.tablespace.by_type[UNDO]", "host": "yas-zabbix-agent", "color": LINE_COLORS[2]}],
                    width=12, height=5, x=0, y=3, stacked=True),
                svg_graph("数据文件最大使用率",
                    [{"key": "yashandb.db.datafile_max_usage_pct", "host": "yas-zabbix-agent"}],
                    width=8, height=5, x=12, y=3, show_legend=False),

                # 第三行
                svg_graph("Invalid 对象趋势",
                    [{"key": "yashandb.db.invalid_objects", "host": "yas-zabbix-agent", "color": LINE_COLORS[0]},
                     {"key": "yashandb.db.invalid_indexes", "host": "yas-zabbix-agent", "color": LINE_COLORS[2]},
                     {"key": "yashandb.db.stale_statistics", "host": "yas-zabbix-agent", "color": LINE_COLORS[3]}],
                    width=10, height=5, x=0, y=8),
                svg_graph("归档日志趋势",
                    [{"key": "yashandb.archived_log.count_today", "host": "yas-zabbix-agent", "color": LINE_COLORS[0]},
                     {"key": "yashandb.archive_log.count", "host": "yas-zabbix-agent", "color": LINE_COLORS[1]}],
                    width=10, height=5, x=10, y=8),

                # 第四行
                svg_graph("Redo 统计",
                    [{"key": "yashandb.db.redo.log_switches", "host": "yas-zabbix-agent", "color": LINE_COLORS[0]},
                     {"key": "yashandb.archived_log.count_today", "host": "yas-zabbix-agent", "color": LINE_COLORS[1]},
                     {"key": "yashandb.archiver.failed", "host": "yas-zabbix-agent", "color": LINE_COLORS[2]}],
                    width=12, height=5, x=0, y=13),
                svg_graph("归档失败",
                    [{"key": "yashandb.archiver.failed", "host": "yas-zabbix-agent"}],
                    width=8, height=5, x=12, y=13, show_legend=False),
            ]
        }]
    }


# ─────────────────────────────────────────────────────────────────────────────
# 主程序
# ─────────────────────────────────────────────────────────────────────────────
BUILDERS = {
    "YashanDB 概览":     build_overview,
    "YashanDB 性能":     build_performance,
    "YashanDB 会话":     build_sessions,
    "YashanDB 存储":     build_storage,
}


def main():
    parser = argparse.ArgumentParser(description="YashanDB Zabbix Dashboard Creator")
    parser.add_argument("--url",      default="http://localhost:8080")
    parser.add_argument("--user",     default="Admin")
    parser.add_argument("--password", default="zabbix")
    parser.add_argument("--host",     default="yas-zabbix-agent")
    parser.add_argument("--dry-run",  action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        for name, builder in BUILDERS.items():
            data = builder(args.host)
            print(f"\n{'='*60}\nDashboard: {name}\n{'='*60}")
            print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    print(f"Connecting to {args.url} ...")
    zapi = ZabbixAPI(args.url, validate_certs=False)
    try:
        zapi.login(args.user, args.password)
        print("Login OK")
    except Exception as e:
        print(f"Login failed: {e}")
        sys.exit(1)

    # 检查主机
    hosts = zapi.host.get({"filter": {"host": args.host}, "output": ["hostid", "name"]})
    if hosts:
        print(f"Host: {args.host} (id={hosts[0]['hostid']})")
    else:
        print(f"Warning: host '{args.host}' not found, widgets will resolve via template")

    print(f"\n{'='*50}\nCreating {len(BUILDERS)} dashboards...\n")
    for name, builder in BUILDERS.items():
        _wid_counter[0] = 0  # 重置计数器
        data = builder(args.host)
        # 检查是否已存在
        existing = zapi.dashboard.get({"filter": {"name": data["name"]}, "output": ["dashboardid"]})
        if existing:
            did = existing[0]["dashboardid"]
            print(f"  [SKIP] '{name}' already exists (id={did})")
            continue
        try:
            r = zapi.dashboard.create(data)
            did = r.get("dashboardids", [None])[0]
            print(f"  [OK]   '{name}' created (id={did})")
        except Exception as e:
            print(f"  [FAIL] '{name}': {e}")

    print("\nDone!")


if __name__ == "__main__":
    main()

# YashanDB Zabbix Dashboard 设计方案

> Zabbix 7.4.x + YashanDB 23.4 LTS
> 参考 Oracle Enterprise Manager / MySQL Enterprise Monitor 经典布局
> 生成时间：2026-04-13

---

## Dashboard 总览

| # | 名称 | UUID | 定位 | 主要指标数 |
|---|------|------|------|-----------|
| 1 | **YashanDB 概览** | `a0e8c000000000000000000000000001` | 每日查看第一步 | 18 个图表 |
| 2 | **YashanDB 性能** | `a0e8c000000000000000000000000002` | 性能调优分析 | 14 个图表 |
| 3 | **YashanDB 会话** | `a0e8c000000000000000000000000003` | 会话与锁分析 | 14 个图表 |
| 4 | **YashanDB 存储** | `a0e8c000000000000000000000000004` | 容量规划预测 | 14 个图表 |

---

## 1. YashanDB 概览

**设计理念**：Oracle OEM 首页风格，顶部 KPI 大数字 → 中部趋势图 → 底部明细

### 布局（5 行 × 20 列）

```
Row 1: [数据库状态] [QPS] [活跃/总会话] [表空间使用率] [缓冲池命中率]
Row 2: [QPS/TPS 趋势 12列] [会话趋势 8列]
Row 3: [Buffer Pool 8列] [SQL执行趋势 6列] [VM Pool 6列]
Row 4: [等待时间趋势 12列] [锁统计 8列]
```

### Widget 清单

| Widget | 类型 | Items | 说明 |
|--------|------|-------|------|
| 数据库状态 | Gauge | `yashandb.db.status` | 1=OK 绿色, 0=红色 |
| QPS | Line | `yashandb.db.qps` | 每秒查询数 |
| 活跃/总会话 | Bar | `yashandb.db.sessions.active`, `total` | 双系列柱状图 |
| 表空间使用率 | Gauge | `yashandb.tablespace.in_use` | 80%黄/90%橙/95%红 |
| 缓冲池命中率 | Gauge | `yashandb.db.memory.buffer_pool_hit` | <95% 红色告警 |
| QPS / TPS 趋势 | Line | `yashandb.db.qps`, `tps` | 1小时趋势 |
| 会话趋势 | Line | `active`, `waiting`, `inactive` | 三系列趋势 |
| Buffer Pool | Line | `buffer_pool_used`, `buffer_pool_size` | 容量监控 |
| SQL 执行趋势 | Line | `executions_per_sec`, `slow_count` | 执行数/慢查询 |
| VM Pool | Line | `vm_pool_used`, `vm_pool_size` | 虚拟内存池 |
| 等待时间趋势 | Line | `wait.time_waited_ms`, `total_waits` | 等待分析 |
| 锁统计 | Line | `lock.count`, `blocking_sessions` | 锁争用 |

---

## 2. YashanDB 性能

**设计理念**：AWR 性能报告风格，顶部 KPI → 解析/慢查询 → 等待 → I/O

### 布局（4 行）

```
Row 1: [QPS] [TPS] [平均响应时间] [P95延迟] [P99延迟]
Row 2: [软解析比率 6列] [慢查询计数 6列] [Buffer Pool命中率 8列]
Row 3: [等待时间与次数趋势 12列] [单块读延迟 8列]
Row 4: [物理读/写次数趋势 10列] [物理 I/O 时间 10列]
```

### Widget 清单

| Widget | 类型 | Items | 说明 |
|--------|------|-------|------|
| QPS | Line | `yashandb.db.qps` | 每秒查询数 |
| TPS | Line | `yashandb.db.tps` | 每秒事务数 |
| 平均响应时间 | Line | `yashandb.db.sql.avg_elapsed_ms` | ms 单位 |
| P95 延迟 | Line | `yashandb.sql.p95_elapsed_ms` | >1000ms 告警 |
| P99 延迟 | Line | `yashandb.sql.p99_elapsed_ms` | >2000ms 告警 |
| 软解析比率 | Line | `yashandb.db.soft_parse_ratio` | <95% 告警 |
| 慢查询计数 | Area | `yashandb.db.sql.slow_count` | 面积图显示趋势 |
| Buffer Pool 命中率 | Line | `yashandb.db.memory.buffer_pool_hit` | <95% 告警 |
| 等待时间与次数 | Line | `wait.time_waited_ms`, `total_waits` | 双Y轴 |
| 单块读延迟 | Line | `avg_synchronous_single_block_read_latency` | >20ms 告警 |
| 物理读/写次数 | Line | `disk.total_reads`, `total_writes` | I/O 吞吐量 |
| 物理 I/O 时间 | Line | `disk.total_read_time`, `total_write_time` | I/O 延迟 |

---

## 3. YashanDB 会话

**设计理念**：Oracle OEM 会话管理页面，关注连接健康与锁争用

### 布局（4 行）

```
Row 1: [活跃会话] [等待会话] [非活跃会话] [后台会话] [总会话/最大]
Row 2: [会话类型趋势堆叠 12列] [资源限制使用率 8列]
Row 3: [锁统计趋势 12列] [长事务数 8列]
Row 4: [Top SQL Buffer Gets 8列] [Top SQL Disk Reads 8列] [会话限制 4列]
```

### Widget 清单

| Widget | 类型 | Items | 说明 |
|--------|------|-------|------|
| 活跃会话 | Bar | `yashandb.db.sessions.active` | >100 告警 |
| 等待会话 | Bar | `yashandb.db.sessions.waiting` | >20 告警 |
| 非活跃会话 | Bar | `yashandb.session.inactive` | >50 提示 |
| 后台会话 | Bar | `yashandb.session.background` | 参考值 |
| 会话趋势（堆叠） | Stacked | `active`, `waiting`, `inactive`, `background` | 容量直观 |
| 资源限制使用率 | Line | `process_limit_pct`, `session_limit_pct`, `usage_pct` | >80% 黄, >90% 红 |
| 锁统计趋势 | Line | `lock.count`, `blocking`, `enqueue.locks`, `enqueue.requests` | 锁争用分析 |
| 长事务数 | Bar | `yashandb.db.long_transactions` | >5 黄, >10 红 |
| Top SQL Buffer Gets | Line | `yashandb.sql.top_buffer_gets` | 高负载 SQL |
| Top SQL Disk Reads | Line | `yashandb.sql.top_disk_reads` | I/O 密集 SQL |

---

## 4. YashanDB 存储

**设计理念**：容量规划页面，关注增长趋势与剩余天数

### 布局（4 行）

```
Row 1: [表空间使用率] [临时表空间] [Undo表空间] [剩余天数] [总/最大容量]
Row 2: [表空间类型容量堆叠 12列] [数据文件最大使用率 8列]
Row 3: [Invalid 对象趋势 10列] [归档日志趋势 10列]
Row 4: [Redo统计 12列] [归档失败 8列]
```

### Widget 清单

| Widget | 类型 | Items | 说明 |
|--------|------|-------|------|
| 表空间使用率（全库） | Gauge | `tablespace.in_use` | 80/90/95 三色 |
| 临时表空间使用率 | Gauge | `tablespace.temp_usage_pct` | >80% 告警 |
| Undo 表空间使用率 | Gauge | `tablespace.undo_usage_pct` | >80% 告警 |
| 剩余可用天数 | Bar | `tablespace_remaining_days` | <30 红, <60 黄 |
| 总容量/最大容量 | Line | `tablespace.size`, `maxsize` | 容量规划 |
| 表空间类型堆叠 | Stacked | `by_type[PERMANENT/TEMPORARY/UNDO]` | 三类容量趋势 |
| 数据文件最大使用率 | Line | `datafile_max_usage_pct` | >90% 告警 |
| Invalid 对象趋势 | Line | `invalid_objects`, `invalid_indexes`, `stale_statistics` | 健康检查 |
| 归档日志趋势 | Line | `archived_log.count_today`, `archive_log.count` | 归档量监控 |
| Redo 统计 | Line | `redo.log_switches`, `archived_log.count_today`, `archiver.failed` | Redo 健康 |
| 归档失败 | Bar | `archiver.failed` | >0 红色告警 |

---

## 指标覆盖总表

| 类别 | 子类 | 指标数 | 覆盖率 |
|------|------|--------|--------|
| **实例** | 状态/版本/运行时间/模式 | 4 | 4/4 |
| **会话** | 活跃/等待/总/最大/非活跃/后台 | 6 | 6/6 |
| **内存** | Buffer Pool / VM Pool / 命中率 | 6 | 6/6 |
| **SQL** | QPS/TPS/执行/解析/P95/P99/慢查询 | 7 | 7/7 |
| **等待** | 等待时间/次数/单块读延迟 | 3 | 3/3 |
| **I/O** | 物理读写次数/时间 | 4 | 4/4 |
| **锁** | 锁数量/阻塞/Enqueue | 4 | 4/4 |
| **表空间** | 使用率/容量/类型/临时/Undo/剩余天数 | 8 | 8/8 |
| **归档** | 当天数量/总数/失败次数/最早时间 | 4 | 4/4 |
| **对象** | Invalid 对象/索引/陈旧统计/段统计 | 5 | 5/5 |
| **资源** | 进程/会话限制使用率/资源限制 | 4 | 4/4 |
| **Redo** | 刷新速度/空闲空间/Checkpoint延迟/日志切换 | 4 | 4/4 |
| **Top SQL** | Buffer Gets/Disk Reads/Executions | 3 | 3/3 |

---

## 使用方法

### 方法一：API 脚本自动创建（推荐）

```bash
# 1. 安装依赖
pip install zabbix-api

# 2. 运行脚本（先 dry-run 查看）
cd C:/Users/DELL/WorkBuddy/Claw/analyze
python yashandb_create_dashboards.py --dry-run

# 3. 连接 Zabbix Server 创建 Dashboard
python yashandb_create_dashboards.py \
    --url http://localhost:8080 \
    --user Admin \
    --password zabbix \
    --host "yas-zabbix-agent"
```

### 方法二：Zabbix Web UI 手动创建

在 Zabbix Web 中：
1. **Dashboards → Create dashboard**
2. 设置 Name 和 UUID（如上表）
3. 添加 Widget → 选择 "SVG Graph" 类型
4. Item 选择对应的 `yashandb.*` 指标
5. 设置 Graph type (line/gauge/bar/area/stacked)
6. 拖拽调整位置

### 方法三：导入 YAML 定义

```bash
# 将 yashandb_zabbix_dashboards.yaml 内容粘贴到
# Zabbix Web UI → Dashboards → Import
```

---

## 设计原则

1. **顶部 KPI → 底部详情**：决策者看 KPI（DBA/Leader），深度分析用趋势图
2. **告警可视化**：阈值直接体现在图表上（红线/黄线/绿区）
3. **Oracle/MySQL 风格**：参考 OEM 6 列网格布局，Zabbix 放宽到 20 列
4. **一个 Widget 聚焦一个主题**：避免信息过载，每个图不超过 3 个数据系列
5. **LLD 动态发现**：用户会话/等待类/表空间等通过模板内置 LLD 自动扩展

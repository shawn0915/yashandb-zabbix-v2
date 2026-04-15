# yas_zabbix

> YashanDB 数据库 Zabbix 监控插件
>
> **适配版本：YashanDB 23.4 LTS + Zabbix 7.0 LTS / 7.4.x**
>
> **v2.3 适配 Nagios check_oracle_health 监控指标，新增 9 个监控项，总计 125 个可用指标**

---

## 目录

- [功能简介](#功能简介)
- [目录结构](#目录结构)
- [前置条件](#前置条件)
- [快速安装](#快速安装)
- [配置 Zabbix Agent](#配置-zabbix-agent)
- [导入 Zabbix 模板](#导入-zabbix-模板)
- [监控指标说明](#监控指标说明)
- [告警规则](#告警规则)
- [常用宏配置](#常用宏配置)
- [手动测试](#手动测试)
- [YashanDB 适配说明](#yashandb-适配说明)
- [N/A 指标说明](#na-指标说明)
- [FAQ](#faq)

---

## 功能简介

本插件通过 **Zabbix Agent UserParameter** 机制，使用 YashanDB 官方 Python 驱动（`yaspy`）连接数据库，支持三套指标命名空间：

| 命名空间 | 指标数量 | 说明 |
|---------|----------|------|
| `yashandb.db.*`（原生） | 33 | v1.0 原有指标 + v2.1 新增长事务/HA/Redo切换 |
| `yashandb.*`（Datadog Oracle 兼容） | 42 | 与 Datadog Oracle 监控指标兼容 |
| `yashandb.db.*`（New Relic 适配） | 41 | 适配 New Relic nri-oracledb 监控指标 |

**v2.3 监控维度（28 类 125 指标）：**

| 类别 | 原生 | Datadog 兼容 | New Relic 适配 | Nagios 适配 | 合计 |
|------|------|-------------|---------------|------------|------|
| 实例状态 | 4 | - | - | 4 |
| 会话与连接 | 4 | 6 | 3 | 13 |
| SQL 解析与执行 | 4 | 2 | 3 | 9 |
| 缓存与内存 | 5 | 5 | 6 | 16 |
| PGA 进程内存 | - | 4 | - | 4 |
| 物理 I/O | - | 2 | 4 | 6 |
| 逻辑读取 | - | 3 | - | 3 |
| 排序与扫描 | - | 2 | - | 2 |
| Redo 日志 | 4 | 3 | 2 | 9 |
| 事务 | - | 3 | - | 3 |
| CPU 与系统资源 | - | 3 | - | 3 |
| 网络与延迟 | - | 2 | - | 2 |
| 等待事件 | 3 | - | 5 | 8 |
| 锁 | 2 | - | 2 | 4 |
| 索引 | - | 2 | - | 2 |
| 表空间 | 4×N | 5 | 2 | 7+N×4 |
| 全局缓存 RAC | - | 2 | - | 2 |
| 长事务与高可用（v2.1） | 2 | - | - | 2 |
| 归档日志 | - | - | 2 | 2 |
| 进程与会话限制 | - | - | 5 | - | 5 |
| N/A 指标标记 | - | - | 6 | - | 6 |
| Nagios 适配（v2.3） | - | - | - | 9 | 9 |
| **合计** | **33** | **42** | **41** | **9** | **125** |

> 注：v2.2 新增的 41 个 New Relic 适配指标中，6 个因 YashanDB 缺少对应视图而标记为 N/A（返回 0 或 NULL）；v2.3 新增的 9 个 Nagios 适配指标全部可用，不影响整体监控功能。

---

## 目录结构

```
yas_zabbix/
├── scripts/
│   ├── yashandb_monitor.py      # 核心采集脚本（v2.3，支持 125 个指标）
│   └── yashandb_bulk.py         # 批量采集脚本（v2.3，调试/诊断用）
├── config/
│   └── yashandb_userparameter.conf.example   # Zabbix Agent 配置示例
├── template/
│   ├── yashandb_zabbix_template.xml          # Zabbix 7.4 导入模板（v2.3）
│   └── yashandb_zabbix_template_7.0.xml      # Zabbix 7.0 LTS 兼容模板（v2.3）
└── README.md
```

---

## 前置条件

### 1. 操作系统
- Linux（推荐）或 Windows

### 2. Python 环境
```bash
python3 --version   # 需要 Python 3.6+
```

### 3. 安装 YashanDB Python 驱动
```bash
# 从 YashanDB 官方获取 yaspy 安装包
pip install yashandb-python-driver

# 验证安装
python3 -c "import yaspy; print('OK')"
```

> **注意**：`yaspy` 需从 YashanDB 官方渠道获取，暂未发布到 PyPI。\
> 下载地址：[https://yashandb.com/downloads](https://yashandb.com/downloads)

### 4. 创建监控专用数据库账号（推荐）
```sql
-- 在 YashanDB 中执行（sys 用户下）
CREATE USER zabbix_monitor IDENTIFIED BY "MonitorPass_123";
GRANT CREATE SESSION TO zabbix_monitor;
GRANT SELECT ON V$INSTANCE TO zabbix_monitor;
GRANT SELECT ON V$DATABASE TO zabbix_monitor;
GRANT SELECT ON V$SESSION TO zabbix_monitor;
GRANT SELECT ON V$SQL TO zabbix_monitor;
GRANT SELECT ON V$SYSSTAT TO zabbix_monitor;
GRANT SELECT ON V$SESSTAT TO zabbix_monitor;
GRANT SELECT ON V$SYSTEM_EVENT TO zabbix_monitor;
GRANT SELECT ON V$SYSTEM_WAIT_CLASS TO zabbix_monitor;
GRANT SELECT ON V$BUFFER_POOL_STATISTICS TO zabbix_monitor;
GRANT SELECT ON V$VMSTAT TO zabbix_monitor;
GRANT SELECT ON V$REDOSTAT TO zabbix_monitor;
GRANT SELECT ON V$LOCK TO zabbix_monitor;
GRANT SELECT ON V$PARAMETER TO zabbix_monitor;
-- Datadog 兼容指标需要的新增权限
GRANT SELECT ON V$PROCESS TO zabbix_monitor;
GRANT SELECT ON V$SGA TO zabbix_monitor;
GRANT SELECT ON V$SGASTAT TO zabbix_monitor;
GRANT SELECT ON V$OSSTAT TO zabbix_monitor;
GRANT SELECT ON V$CPUSTAT TO zabbix_monitor;
-- 表空间
GRANT SELECT ON DBA_TABLESPACES TO zabbix_monitor;
GRANT SELECT ON DBA_DATA_FILES TO zabbix_monitor;
GRANT SELECT ON DBA_FREE_SPACE TO zabbix_monitor;
```

### 5. Zabbix Agent 2 已安装
```bash
zabbix_agent2 --version   # 需要 7.x
```

---

## 快速安装

### Linux

```bash
# 1. 克隆仓库
git clone https://gitee.com/yourname/yas_zabbix.git /etc/zabbix/scripts/yas_zabbix

# 2. 赋予执行权限
chmod +x /etc/zabbix/scripts/yas_zabbix/scripts/*.py

# 3. 复制 Agent 配置
cp /etc/zabbix/scripts/yas_zabbix/config/yashandb_userparameter.conf.example \
   /etc/zabbix/zabbix_agentd.d/yashandb.conf

# 4. 编辑配置，填入实际连接参数
vi /etc/zabbix/zabbix_agentd.d/yashandb.conf

# 5. 重启 Zabbix Agent
systemctl restart zabbix-agent2
```

### Windows

```powershell
# 1. 克隆仓库
git clone https://gitee.com/yourname/yas_zabbix.git "C:\zabbix\scripts\yas_zabbix"

# 2. 复制并编辑配置
copy "C:\zabbix\scripts\yas_zabbix\config\yashandb_userparameter.conf.example" `
     "C:\Program Files\Zabbix Agent 2\zabbix_agentd.d\yashandb.conf"

# 3. 编辑 yashandb.conf，取消注释 Windows 示例行并填入参数

# 4. 重启 Zabbix Agent 服务
Restart-Service "Zabbix Agent 2"
```

---

## 配置 Zabbix Agent

编辑 `config/yashandb_userparameter.conf.example`，取消注释并修改需要的指标行：

```ini
# Linux 示例
UserParameter=yashandb.db.status,/usr/bin/python3 /etc/zabbix/scripts/yas_zabbix/yashandb_monitor.py --host 127.0.0.1 --port 1688 --user zabbix_monitor --password "MonitorPass_123" --metric yashandb.db.status

# 带参数的表空间（$1 由 Zabbix LLD 自动传入表空间名）
UserParameter=yashandb.tablespace.pct_used[*],/usr/bin/python3 /etc/zabbix/scripts/yas_zabbix/yashandb_monitor.py --host 127.0.0.1 --port 1688 --user zabbix_monitor --password "MonitorPass_123" --metric "yashandb.tablespace.pct_used[$1]"
```

> **安全建议**：生产环境请使用 `--config` 参数指向外部配置文件，避免密码出现在命令行中：
> ```ini
> UserParameter=yashandb.db.status,/usr/bin/python3 /etc/zabbix/scripts/yas_zabbix/yashandb_monitor.py --config /etc/zabbix/scripts/yas_zabbix/config/yashandb.conf --host x --user x --password x --metric yashandb.db.status
> ```
> 配置文件格式（`/etc/zabbix/scripts/yas_zabbix/config/yashandb.conf`）：
> ```ini
> [yashandb]
> host = 127.0.0.1
> port = 1688
> user = zabbix_monitor
> password = MonitorPass_123
> ```

---

## 导入 Zabbix 模板

根据你的 Zabbix 版本选择对应模板文件：

| Zabbix 版本 | 模板文件 |
|------------|---------|
| **7.0 LTS**（推荐，主流生产环境） | `template/yashandb_zabbix_template_7.0.xml` |
| **7.4.x** | `template/yashandb_zabbix_template.xml` |

> **说明**：Zabbix 导入时会校验模板 XML 中的 `<version>` 字段，版本号高于当前 Zabbix 的模板无法导入。两个文件功能完全相同，仅版本标记不同。

导入步骤：
1. 登录 Zabbix Web UI
2. 进入 **配置 → 模板 → 导入**
3. 按上表选择对应版本的模板文件
4. 点击 **导入**
5. 将模板 **"YashanDB by Zabbix Agent"** 关联到目标主机
6. 在主机宏中配置连接参数（见下方宏配置）

---

## 监控指标说明

### 实例状态（yashandb.db.*）

| Zabbix Key | 说明 | 采集间隔 |
|-----------|------|---------|
| `yashandb.db.status` | 实例状态（1=正常/0=异常） | 60s |
| `yashandb.db.version` | 数据库版本号 | 3600s |
| `yashandb.db.uptime` | 启动时长（秒） | 300s |
| `yashandb.db.mode` | 运行模式（PRIMARY/STANDBY） | 300s |

### 会话（原生 + Datadog）

| Zabbix Key | 说明 | 来源 | 采集间隔 |
|-----------|------|------|---------|
| `yashandb.db.sessions.active` | 活跃会话数 | 原生 | 60s |
| `yashandb.db.sessions.total` | 总会话数 | 原生 | 60s |
| `yashandb.db.sessions.waiting` | 等待中会话数 | 原生 | 60s |
| `yashandb.db.sessions.max` | 最大会话限制 | 原生 | 3600s |
| `yashandb.active_background` | 活跃后台会话数 | Datadog | 60s |
| `yashandb.active_sessions` | 活跃会话总数 | Datadog | 60s |
| `yashandb.process_limit` | 进程限制使用率(%) | Datadog | 60s |
| `yashandb.session_count` | 会话总数 | Datadog | 60s |
| `yashandb.session_limit_usage` | 会话限制使用率(%) | Datadog | 60s |
| `yashandb.user_sessions` | 用户会话数 | Datadog | 60s |

### 内存

| Zabbix Key | 说明 | 来源 | 采集间隔 |
|-----------|------|------|---------|
| `yashandb.db.memory.buffer_pool_size` | Buffer Pool 总大小 | 原生 | 300s |
| `yashandb.db.memory.buffer_pool_used` | Buffer Pool 已使用 | 原生 | 300s |
| `yashandb.db.memory.buffer_pool_hit` | Buffer Pool 命中率(%) | 原生 | 300s |
| `yashandb.db.memory.vm_pool_size` | VM Pool 总大小 | 原生 | 300s |
| `yashandb.db.memory.vm_pool_used` | VM Pool 已使用 | 原生 | 300s |
| `yashandb.buffer_cachehit_ratio` | 缓冲区缓存命中率(%) | Datadog | 300s |
| `yashandb.cache_blocks_lost` | 丢失的缓存块数 | Datadog | 300s |
| `yashandb.physical_memory_gb` | 物理内存大小(GB) | Datadog | 3600s |
| `yashandb.shared_memory_size` | 共享内存大小(字节) | Datadog | 300s |
| `yashandb.shared_pool_free` | 共享池空闲内存百分比(%) | Datadog | 300s |

### PGA 进程内存（Datadog）

| Zabbix Key | 说明 | 采集间隔 |
|-----------|------|---------|
| `yashandb.process.pga_allocated_memory` | PGA 分配内存(字节) | 120s |
| `yashandb.process.pga_freeable_memory` | PGA 可释放内存(字节) | 120s |
| `yashandb.process.pga_max_memory` | PGA 当前最大内存(字节) | 120s |
| `yashandb.process.pga_used_memory` | PGA 已用内存(字节) | 120s |

### SQL 性能

| Zabbix Key | 说明 | 来源 | 采集间隔 |
|-----------|------|------|---------|
| `yashandb.db.sql.executions_per_sec` | 每秒执行次数 | 原生 | 60s |
| `yashandb.db.sql.avg_elapsed_ms` | 平均执行时长(ms) | 原生 | 120s |
| `yashandb.db.sql.slow_count` | 慢SQL数量(>1s) | 原生 | 120s |
| `yashandb.db.sql.parse_count` | 硬解析次数 | 原生 | 120s |
| `yashandb.hard_parses` | 硬解析次数 | Datadog | 120s |
| `yashandb.memory_sorts_ratio` | 内存排序比率(%) | Datadog | 120s |

### 表空间（自动发现 LLD）

| Key 原型 | 说明 |
|---------|------|
| `yashandb.tablespace.discovery` | 自动发现所有表空间 |
| `yashandb.tablespace.total[{#TS}]` | 指定表空间总大小（字节） |
| `yashandb.tablespace.used[{#TS}]` | 指定表空间已使用（字节） |
| `yashandb.tablespace.free[{#TS}]` | 指定表空间剩余空间（字节） |
| `yashandb.tablespace.pct_used[{#TS}]` | 指定表空间使用率（%） |

> Datadog 兼容的全库汇总指标：`yashandb.tablespace.in_use`（总使用率%）、`yashandb.tablespace.maxsize`、`yashandb.tablespace.size`、`yashandb.tablespace.used`、`yashandb.tablespace.offline`

### 物理/逻辑 I/O（Datadog）

| Zabbix Key | 说明 | 采集间隔 |
|-----------|------|---------|
| `yashandb.physical_reads` | 物理读取次数（DISK READS） | 60s |
| `yashandb.physical_writes` | 物理写入次数（DISK WRITES） | 60s |
| `yashandb.consistent_read_changes` | 一致性读变更次数 | 60s |
| `yashandb.db_block_changes` | 数据库块变更数 | 60s |
| `yashandb.logical_reads` | 逻辑读取次数 | 60s |

### Redo 日志

| Zabbix Key | 说明 | 来源 | 采集间隔 |
|-----------|------|------|---------|
| `yashandb.db.redo.flush_speed` | Redo 刷盘速度（字节/秒） | 原生 | 60s |
| `yashandb.db.redo.free_space` | Redo 空闲空间（字节） | 原生 | 60s |
| `yashandb.db.redo.checkpoint_lag` | 检查点落后量 | 原生 | 60s |
| `yashandb.redo_allocation_hit_ratio` | Redo 空间分配命中率(%) | Datadog | 60s |
| `yashandb.redo_generated` | Redo 生成速率（字节/秒） | Datadog | 60s |
| `yashandb.redo_writes` | Redo 写入次数 | Datadog | 60s |

### CPU、网络、索引（Datadog）

| Zabbix Key | 说明 | 采集间隔 |
|-----------|------|---------|
| `yashandb.host_cpu_utilization` | 主机 CPU 利用率(%) | 60s |
| `yashandb.num_cpus` | CPU 核心数 | 3600s |
| `yashandb.os_load` | 操作系统负载 | 60s |
| `yashandb.avg_synchronous_single_block_read_latency` | 平均单块读延迟(ms) | 120s |
| `yashandb.network_traffic_volume` | 每秒网络流量（字节） | 60s |
| `yashandb.branch_node_splits` | 分支节点分裂次数 | 120s |
| `yashandb.leaf_node_splits` | 叶节点分裂次数 | 120s |

### 事务（Datadog）

| Zabbix Key | 说明 | 采集间隔 |
|-----------|------|---------|
| `yashandb.dbwr_checkpoints` | DBWR 检查点完成数 | 120s |
| `yashandb.user_commits` | 用户提交次数 | 60s |
| `yashandb.user_rollbacks` | 用户回滚次数 | 60s |

### 全局缓存 RAC（Datadog，单机通常为 0）

| Zabbix Key | 说明 | 采集间隔 |
|-----------|------|---------|
| `yashandb.gc_average_cr_get_time` | GC 平均 CR 获取时间(ms) | 120s |
| `yashandb.gc_average_current_get_time` | GC 平均 current 块获取时间(ms) | 120s |

### 长事务与高可用（v2.1 新增，来源：YCM 监控指标对标，**实机验证**）

| Zabbix Key | 说明 | 采集间隔 |
|-----------|------|---------|
| `yashandb.db.long_transactions` | 超过3分钟活跃事务数（V$TRANSACTION.SID JOIN V$SESSION.SID，START_DATE） | 60s |
| `yashandb.db.ha.sync_delay` | 主备同步延迟（gap数量，V$ARCHIVE_GAP；V$STANDBY_LOG不存在） | 30s |
| `yashandb.db.redo.log_switches` | 近24h Redo 日志切换次数（V$ARCHIVED_LOG.FIRST_TIME；V$LOG/V$LOG_HISTORY不存在） | 300s |

> **v2.1 新增指标说明（实机验证，2026-04-10）**：
> - `long_transactions`：对标 YCM `yashandb_long_transactions`，通过 `V_$TRANSACTION` JOIN `V_$SESSION`（使用 **SID 字段**，非 Oracle 的 SES_ADDR/SADDR）统计 STATUS='ACTIVE' 且 START_DATE 距当前超过3分钟的事务数量。`START_DATE` 为 DATE 类型，`(SYSDATE - START_DATE)*86400` 直接计算秒数。
> - `ha.sync_delay`：对标 YCM `yashandb_sync_delay`，通过 `V_$ARCHIVE_GAP`（列：ID, LOW_SEQUENCE#, HIGH_SEQUENCE#）返回主备间归档序列号间隙数量。**注意：V_$STANDBY_LOG 在 YashanDB 23.4 中不存在**。单机或无间隙时返回 0。
> - `redo.log_switches`：对标 YCM Redo 切换频率，通过 `V_$ARCHIVED_LOG`（列：NAME, SEQUENCE#, FIRST_TIME...）统计 `FIRST_TIME >= SYSDATE-1` 的归档日志数量。**注意：V_$LOG / V_$LOG_HISTORY 在 YashanDB 23.4 中不存在**，使用 `V_$ARCHIVED_LOG` 替代。

### 等待事件（v2.2 新增，来源：New Relic nri-oracledb）

| Zabbix Key | 说明 | 采集间隔 |
|-----------|------|---------|
| `yashandb.db.wait_top_event` | TOP 等待事件名称（按 TIME_WAITED 排序） | 60s |
| `yashandb.db.waits_total` | 总会话等待次数（V$SYSTEM_EVENT 总计） | 60s |
| `yashandb.db.wait_time_total` | 总会话等待时间（秒） | 60s |
| `yashandb.db.wait_event_waits[{#WAIT_EVENT}]` | 指定等待事件次数（LLD） | 60s |
| `yashandb.db.wait_event_time[{#WAIT_EVENT}]` | 指定等待事件时间（秒，LLD） | 60s |

### SGA Buffer 与内存（v2.2 新增，来源：New Relic nri-oracledb）

| Zabbix Key | 说明 | 采集间隔 |
|-----------|------|---------|
| `yashandb.sga.buffer_busy_waits` | Buffer Busy Waits 次数（SGA 争用） | 60s |
| `yashandb.sga.free_buffer_waits` | Free Buffer Waits 次数 | 60s |
| `yashandb.sga.free_buffer_inspected` | Free Buffer Inspected 数量 | 120s |
| `yashandb.sga.fixed_size` | SGA Fixed Size 大小（字节，V$SGA） | 3600s |
| `yashandb.sga.redo_buffers` | Redo Buffers 大小（字节，V$SGA） | 3600s |
| `yashandb.sga.log_buffer_space_waits` | Log Buffer Space Waits 次数 | 60s |

### 物理 I/O 与磁盘（v2.2 新增，来源：New Relic nri-oracledb）

| Zabbix Key | 说明 | 采集间隔 |
|-----------|------|---------|
| `yashandb.disk.total_reads` | 物理读取总次数（V$FILESTAT SUM PHYRDS） | 60s |
| `yashandb.disk.total_writes` | 物理写入总次数（V$FILESTAT SUM PHYWRTS） | 60s |
| `yashandb.disk.total_read_time` | 物理读取总时间（秒，V$FILESTAT SUM READTIM） | 60s |
| `yashandb.disk.total_write_time` | 物理写入总时间（秒，V$FILESTAT SUM WRITETIM） | 60s |

### 会话增强（v2.2 新增）

| Zabbix Key | 说明 | 采集间隔 |
|-----------|------|---------|
| `yashandb.sessions.inactive` | 非活跃会话数 | 60s |
| `yashandb.sessions.background` | 后台会话数 | 60s |
| `yashandb.sessions.active_detail` | 活跃会话数（含详细来源说明） | 60s |

### Redo 增强（v2.2 新增）

| Zabbix Key | 说明 | 采集间隔 |
|-----------|------|---------|
| `yashandb.redo.waits` | Redo 日志等待次数（log file parallel write 等） | 60s |
| `yashandb.redo.switch_checkpoint` | Redo 切换触发检查点次数 | 300s |

### Top SQL 与 DB 常规（v2.2 新增）

| Zabbix Key | 说明 | 采集间隔 |
|-----------|------|---------|
| `yashandb.sql.top_buffer_gets` | 缓冲区获取最多的 SQL 模块名（V$SQLAREA） | 120s |
| `yashandb.sql.top_disk_reads` | 磁盘读取最多的 SQL 模块名（V$SQLAREA） | 120s |
| `yashandb.sql.count` | 共享池中 SQL 语句总数（V$SQLAREA COUNT） | 300s |
| `yashandb.db.current_logons` | 当前登录数（V$SYSSTAT LOGONS） | 60s |
| `yashandb.db.open_cursors` | 打开游标数（V$SQLAREA COUNT，替代 V$OPEN_CURSOR） | 60s |
| `yashandb.db.user_limit_pct` | 用户会话限制使用率(%) | 60s |
| `yashandb.db.process_limit_pct` | 进程限制使用率(%) | 60s |
| `yashandb.db.session_limit_pct` | 会话限制使用率(%) | 60s |

### 表空间增强（v2.2 新增）

| Zabbix Key | 说明 | 采集间隔 |
|-----------|------|---------|
| `yashandb.tablespace.offline_count` | 离线表空间数量 | 60s |
| `yashandb.tablespace.datafile_offline_count` | 离线数据文件数量 | 60s |

### 归档日志与锁（v2.2 新增）

| Zabbix Key | 说明 | 采集间隔 |
|-----------|------|---------|
| `yashandb.archived_log.count` | 近24h 归档日志数量（V$ARCHIVED_LOG） | 300s |
| `yashandb.archived_log.first_time` | 最新归档日志 FIRST_TIME（Unix 时间戳） | 300s |
| `yashandb.lock.enqueue_locks` | Enqueue 锁数量（V$LOCK TYPE='TX'/'TM'） | 60s |
| `yashandb.lock.enqueue_requests` | Enqueue 锁请求次数 | 60s |
| `yashandb.archiver.failed` | 归档失败次数 | 60s |

### N/A 指标标记（v2.2 新增，返回 0 或 NULL）

| Zabbix Key | 原来源 | YashanDB 不可用原因 |
|-----------|------|---------------------|
| `yashandb.library_cache_hit_ratio` | V$LIBRARYCACHE | YashanDB 不存在此视图 |
| `yashandb.library_cache_reload_ratio` | V$LIBRARYCACHE | YashanDB 不存在此视图 |
| `yashandb.row_cache_hit_ratio` | V$ROWCACHE | YashanDB 不存在此视图 |
| `yashandb.rollback.gets` | V$ROLLSTAT | YashanDB 不存在此视图 |
| `yashandb.rollback.waits` | V$ROLLSTAT | YashanDB 不存在此视图 |
| `yashandb.rollback.ratio_wait` | V$ROLLSTAT | YashanDB 不存在此视图 |

> **数据来源**：New Relic Labs [nri-oracledb](https://github.com/newrelic/nri-oracledb)（v3.13.0），Go 语言实现，开源。指标设计参考 Oracle 动态性能视图（V$SYSTEM_EVENT / V$FILESTAT / V$SQLAREA / V$SGA 等）。

---

## 告警规则

| 触发器名称 | 级别 | 条件 |
|-----------|------|------|
| 实例不可用 | 灾难(DISASTER) | `yashandb.db.status = 0` |
| 数据库最近重启 | 警告(WARNING) | `yashandb.db.uptime < 300s` |
| Buffer Pool 命中率过低 | 警告(WARNING) | `命中率 < {$YASHANDB.BUFFER.HIT.MIN}` |
| 缓存命中率低 | 警告(WARNING) | `buffer_cachehit_ratio < {$YASHANDB.BUFFER.HIT.MIN}` |
| 共享池空闲内存不足 | 警告(WARNING) | `shared_pool_free < {$YASHANDB.SHARED_POOL_FREE.MIN}` |
| 慢 SQL 数量过多 | 警告(WARNING) | `slow_count > {$YASHANDB.SLOW_SQL.WARN}` |
| PGA 分配内存过高 | 警告(WARNING) | `pga_allocated_memory > {$YASHANDB.PGA_ALLOC.MAX}` |
| 磁盘排序过多 | 警告(WARNING) | `disk_sorts > 1000` |
| Redo 生成速率过高 | 警告(WARNING) | `redo_generated > {$YASHANDB.REDO_GEN.MAX}` |
| Redo 空间分配命中率低 | 警告(WARNING) | `redo_allocation_hit_ratio < 99%` |
| CPU 利用率过高 | 警告(WARNING) | `host_cpu_utilization > {$YASHANDB.CPU.UTIL.MAX}` |
| 单块读延迟过高 | 警告(WARNING) | `avg_synchronous_single_block_read_latency > 20ms` |
| 锁数量过多 | 警告(WARNING) | `lock.count > {$YASHANDB.LOCK.WARN}` |
| 存在阻塞会话 | 一般(AVERAGE) | `blocking_sessions > 0` |
| 进程限制使用率过高 | 警告(WARNING) | `process_limit > {$YASHANDB.PROCESS_LIMIT.WARN}` |
| 会话限制使用率过高 | 警告(WARNING) | `session_limit_usage > {$YASHANDB.SESSION_LIMIT.WARN}` |
| 检测到丢失写 | 高危(HIGH) | `cache_blocks_lost > 0` |
| 存在离线表空间 | 高危(HIGH) | `tablespace.offline > 0` |
| 表空间使用率严重 | 高危(HIGH) | `使用率 > {$YASHANDB.TABLESPACE.CRIT}` |
| 表空间使用率告警 | 警告(WARNING) | `使用率 > {$YASHANDB.TABLESPACE.WARN}` |
| **存在长事务**（v2.1） | 警告(WARNING) | `long_transactions >= {$YASHANDB.LONG_TXN.WARN}` |
| **长事务数量过多**（v2.1） | 一般(AVERAGE) | `long_transactions >= {$YASHANDB.LONG_TXN.HIGH}` |
| **主备同步延迟过高**（v2.1） | 警告(WARNING) | `ha.sync_delay >= {$YASHANDB.HA_DELAY.WARN}` |
| **主备同步延迟严重**（v2.1） | 高危(HIGH) | `ha.sync_delay >= {$YASHANDB.HA_DELAY.HIGH}` |
| **Redo 切换过于频繁**（v2.1） | 警告(WARNING) | `redo.log_switches > {$YASHANDB.LOG_SWITCH.WARN}` |
| **Buffer Busy Waits 突增**（v2.2） | 警告(WARNING) | `sga.buffer_busy_waits.change > 100` |
| **Log Buffer Space Waits 突增**（v2.2） | 警告(WARNING) | `sga.log_buffer_space_waits.change > 50` |
| **非活跃会话过多**（v2.2） | 一般(AVERAGE) | `sessions.inactive > 50` |
| **高 Buffer Gets SQL 执行**（v2.2） | 警告(WARNING) | `sql.top_buffer_gets != 'UNKNOWN' AND length(sql.top_buffer_gets) > 0` |
| **进程限制使用率过高**（v2.2） | 警告(WARNING) | `db.process_limit_pct > {$YASHANDB.PROCESS_LIMIT.WARN}` |
| **会话限制使用率过高**（v2.2） | 警告(WARNING) | `db.session_limit_pct > {$YASHANDB.SESSION_LIMIT.WARN}` |
| **存在离线数据文件**（v2.2） | 高危(HIGH) | `tablespace.datafile_offline_count > 0` |
| **Enqueue 锁请求过多**（v2.2） | 警告(WARNING) | `lock.enqueue_requests > 5` |
| **归档进程失败**（v2.2） | 高危(HIGH) | `archiver.failed.change > 0` |
| **存在无效数据库对象**（v2.3） | 警告(WARNING) | `db.invalid_objects > 0` |
| **存在无效索引**（v2.3） | 警告(WARNING) | `db.invalid_indexes > 0` |
| **陈旧统计信息过多**（v2.3） | 信息(INFO) | `db.stale_statistics > 10` |
| **软解析比率偏低**（v2.3） | 警告(WARNING) | `db.soft_parse_ratio < 95` |
| **表空间将在 30 天内耗尽**（v2.3） | 高危(HIGH) | `db.tablespace_remaining_days > 0 AND db.tablespace_remaining_days < 30` |
| **表空间已满**（v2.3） | 灾难(DISASTER) | `db.tablespace_remaining_days = 0` |
| **数据文件容量使用率超 90%**（v2.3） | 高危(HIGH) | `db.datafile_max_usage_pct > 90` |

---

## 常用宏配置

在 Zabbix 主机或模板宏中配置以下参数：

| 宏名称 | 默认值 | 说明 |
|-------|--------|------|
| `{$YASHANDB.HOST}` | `127.0.0.1` | YashanDB 主机地址 |
| `{$YASHANDB.PORT}` | `1688` | YashanDB 端口 |
| `{$YASHANDB.USER}` | `sys` | 监控账号 |
| `{$YASHANDB.PASSWORD}` | _(空)_ | 监控账号密码（密文存储） |
| `{$YASHANDB.SCRIPT_DIR}` | `/etc/zabbix/scripts/yas_zabbix` | 脚本目录 |
| `{$YASHANDB.PYTHON}` | `/usr/bin/python3` | Python 路径 |
| `{$YASHANDB.BUFFER.HIT.MIN}` | `90` | Buffer 命中率告警阈值(%) |
| `{$YASHANDB.SHARED_POOL_FREE.MIN}` | `20` | 共享池空闲内存最低阈值(%) |
| `{$YASHANDB.TABLESPACE.WARN}` | `80` | 表空间告警阈值(%) |
| `{$YASHANDB.TABLESPACE.CRIT}` | `90` | 表空间严重告警阈值(%) |
| `{$YASHANDB.SLOW_SQL.WARN}` | `10` | 慢SQL告警阈值 |
| `{$YASHANDB.LOCK.WARN}` | `20` | 锁数量告警阈值 |
| `{$YASHANDB.PROCESS_LIMIT.WARN}` | `80` | 进程限制使用率告警(%) |
| `{$YASHANDB.SESSION_LIMIT.WARN}` | `80` | 会话限制使用率告警(%) |
| `{$YASHANDB.CPU.UTIL.MAX}` | `90` | CPU 利用率最高阈值(%) |
| `{$YASHANDB.PGA_ALLOC.MAX}` | `10737418240` | PGA 分配内存告警阈值(字节) |
| `{$YASHANDB.REDO_GEN.MAX}` | `10485760` | Redo 生成速率告警(字节/秒) |
| `{$YASHANDB.LONG_TXN.WARN}` | `1` | 长事务告警阈值（事务数，1=有即告警） |
| `{$YASHANDB.LONG_TXN.HIGH}` | `5` | 长事务严重阈值（事务数） |
| `{$YASHANDB.HA_DELAY.WARN}` | `1` | 主备同步延迟告警阈值（gap 数量，1=有即告警） |
| `{$YASHANDB.HA_DELAY.HIGH}` | `5` | 主备同步延迟严重阈值（gap 数量） |
| `{$YASHANDB.LOG_SWITCH.WARN}` | `50` | 近24h Redo 日志切换告警阈值（次） |

---

## 手动测试

```bash
# 测试连接并获取实例状态
python3 scripts/yashandb_monitor.py \
  --host 127.0.0.1 --port 1688 \
  --user zabbix_monitor --password MonitorPass_123 \
  --metric yashandb.db.status

# 测试 Datadog 兼容指标
python3 scripts/yashandb_monitor.py \
  --host 127.0.0.1 --port 1688 \
  --user sys --password YourPass \
  --metric yashandb.buffer_cachehit_ratio

# 测试表空间使用率（指定表空间名）
python3 scripts/yashandb_monitor.py \
  --host 127.0.0.1 --port 1688 \
  --user sys --password YourPass \
  --metric "yashandb.tablespace.pct_used[SYSTEM]"

# 批量采集所有 125 个指标（诊断用）
python3 scripts/yashandb_bulk.py \
  --host 127.0.0.1 --port 1688 \
  --user sys --password YourPass \
  --json

# 通过 Zabbix Agent 测试（需先配置 UserParameter）
zabbix_agentd -t yashandb.db.status
zabbix_agentd -t yashandb.buffer_cachehit_ratio
zabbix_agentd -t "yashandb.tablespace.pct_used[SYSTEM]"
```

---

## 自动化测试

本项目使用 pytest 进行自动化测试，测试文件位于 `tests/` 目录。

### 安装测试依赖

```bash
pip install pytest
```

集成测试还需安装 yaspy：

```bash
pip install yashandb-python-driver
```

### 运行测试

```bash
# 仅单元测试（无需数据库，约 10 秒）
pytest tests/ -v -m "not integration"

# 包含集成测试（需 Docker 运行 + YAS_PASSWORD 环境变量）
set YAS_PASSWORD=yourpassword
pytest tests/ -v --live-db

# 运行单个测试文件
pytest tests/test_monitor_metrics.py -v
pytest tests/test_monitor_cli.py -v
pytest tests/test_bulk.py -v
```

### 测试覆盖范围

| 测试 | 内容 | 依赖 |
|------|------|------|
| `test_monitor_metrics.py` | 所有 75 个指标的路由、类型检查、异常处理 | 无 |
| `test_monitor_cli.py` | CLI 参数解析、配置加载、METRIC_HELP 与 dispatch 一致性 | 无 |
| `test_monitor_integration.py` | 所有指标在真实 YashanDB 上执行 | Docker + yaspy |
| `test_bulk.py` | BULK_METRICS 列表完整性 | 无 |

详细说明见 `tests/README.md`。

---

## YashanDB 适配说明

以下信息来自 YashanDB 23.4.7.100 实机测试（详见 `analyze/datadog_yashandb_final.md`）：

### 1. 视图命名规则

Oracle 的 `V$XXX` → YashanDB 的 **`V$XXX`**（直接兼容，无需改写）：

| Oracle | YashanDB | 状态 |
|--------|----------|------|
| `V$SESSION` | `V$SESSION` | ✅ |
| `V$SYSSTAT` | `V$SYSSTAT` | ✅ |
| `V$PARAMETER` | `V$PARAMETER` | ✅ |
| `V$OSSTAT` | `V$OSSTAT` | ✅ |
| `V$SYSTEM_EVENT` | `V$SYSTEM_EVENT` | ✅ |
| `V$BUFFER_POOL_STATISTICS` | `V$BUFFER_POOL_STATISTICS` | ✅ |
| `V$SGA` | `V$SGA` | ✅（替代 V$SGAINFO） |
| `V$SGASTAT` | `V$SGASTAT` | ✅ |
| `V$PROCESS` | `V$PROCESS` | ✅ |
| `V$ASM_DISKGROUP` | **不存在** | ❌ |
| `V$DATAGUARD_STATS` | **不存在** | ❌ |
| `V$DATABASE_BLOCK_CORRUPTION` | **不存在** | ❌ |
| `V$LIBRARYCACHE` | **不存在** | ❌ |
| `V$ROWCACHE` | **不存在** | ❌ |
| `V$PGASTAT` | **不存在** | ❌ |
| `V$SYS_TIME_MODEL` | **不存在** | ❌ |
| `V$RESOURCE_CONSUMER_GROUP` | **不存在** | ❌ |
| `V$TEMP_SPACE_HEADER` | **不存在** | ❌ |

### 2. V_$SYSSTAT 统计项命名

YashanDB 使用**大写无括号**的统计项名称（与 Oracle 不同）：

| Oracle | YashanDB V$SYSSTAT | 状态 |
|--------|---------------------|------|
| `physical reads` | `DISK READS` | ✅ |
| `physical writes` | `DISK WRITES` | ✅ |
| `user commits` | `COMMITS` | ✅ |
| `user rollbacks` | `ROLLBACKS` | ✅ |
| `consistent gets` | `CONSISTENT GETS` | ✅ |
| `db block gets` | `DB BLOCK GETS` | ✅ |
| `execute count` | `EXECUTE COUNT` | ✅ |
| `redo size` | `REDO SIZE` | ✅ |
| `parse count (hard)` | `PARSE COUNT (HARD)` | ✅ |
| `parse count (total)` | **不存在** | ❌ |
| `physical read bytes` | **不存在** | ❌ |
| `physical reads direct` | **不存在** | ❌ |

### 3. YashanDB 特有视图

| 视图 | 说明 | 替代的 Oracle 功能 |
|------|------|-------------------|
| `V$SGA` | SGA 各组件大小 | 替代 `V$SGAINFO` |
| `V$SGASTAT` | SGA 详细统计（POOL + NAME + BYTES） | 共享池统计 |
| `V$OSSTAT` | OS 统计（NUM_CPUS, PHYSICAL_MEMORY_BYTES, LOAD） | 系统资源统计 |

---

## Nagios check_oracle_health 适配指标（v2.3）

来源：[ConSol check_oracle_health](https://github.com/lausser/check_oracle_health)，v3.1.2.3，共 50+ 种 `--mode`。

以下 Nagios 指标已适配到 YashanDB 23.4：

| Nagios mode | 对应指标 | 数据来源 | 说明 |
|------------|---------|---------|------|
| `invalid-objects` | `db.invalid_objects` | DBA_OBJECTS | STATUS='INVALID' 对象数 |
| `invalid-objects`（索引） | `db.invalid_indexes` | DBA_INDEXES | STATUS='INVALID' 索引数 |
| `stale-statistics` | `db.stale_statistics` | DBA_TAB_STATISTICS | STALE_STATS='YES' 表数 |
| `soft-parse-ratio` | `db.soft_parse_ratio` | V$SYSSTAT | 基于 SESSION CURSOR CACHE HITS |
| `tablespace-remaining-time` | `db.tablespace_remaining_days` | DBA_TABLESPACE_USAGE_METRICS + DBA_DATA_FILES | 增长趋势预测 |
| `datafiles-existing` | `db.datafile_max_usage_pct` | DBA_DATA_FILES | MAXBYTES 使用率 |

**不支持（YashanDB 无对应功能）：**
- `rman-backup-problems` — 无 RMAN 相关视图
- `flash-recovery-area-*` — YashanDB 无 FRA 概念
- `seg-top10-*` — 无历史段统计视图
- `roll-*`、`enqueue-*`、`latch-*` — 已有基础覆盖（v2.2 enqueue locks/requests）

---

## N/A 指标说明

以下指标在 YashanDB 中无对应功能。**Datadog Oracle 兼容**：46 个不包含；**New Relic 适配**：6 个已包含但返回 0 或 NULL（含在 125 指标总数中）：

| 类别 | 指标 | 原因 |
|------|------|------|
| 会话 | `active_background_on_cpu`, `active_sessions_on_cpu` | V$SESSION 无 STATE 列 |
| 会话 | `logons`, `session.inactive_seconds` | 无 LOGONS 统计项 / 无 LAST_CALL_ET 列 |
| SQL 解析 | `execute_without_parse`, `parse_failures`, `total_parse_count` | 无 PARSE COUNT (TOTAL)；`soft_parse_ratio` 已在 v2.3 实现 |
| 缓存 | `cache_blocks_corrupt`, `library_cachehit_ratio`, `pga_cache_hit`, `row_cache_hit_ratio` | 对应视图不存在 |
| PGA | `process.pga_maximum_memory` | V$PGASTAT 不存在 |
| 物理 I/O | 所有 `*_bytes`, `*_io_requests`, `*_direct*` 指标 | YashanDB 无这些统计项 |
| 逻辑读 | `consistent_read_gets`, `db_block_gets` | V$SYSSTAT 无对应名称 |
| 排序 | `long_table_scans`, `rows_per_sort` | 无 SORTS (ROWS) / TABLE SCANS (LONG) |
| 事务 | `enqueue_deadlocks`, `enqueue_timeouts` | 无此统计项 |
| CPU | `database_cpu_time_ratio`, `database_wait_time_ratio`, `service_response_time` | V$SYS_TIME_MODEL 不存在 |
| 表空间 | `temp_space_used` | V$TEMP_SPACE_HEADER 不存在 |
| ASM | `asm_diskgroup.*`（全部3个） | YashanDB 无 ASM 功能 |
| Data Guard | `data_guard.*`（全部2个） | V$DATAGUARD_STATS 不存在 |
| Resource Manager | `resource_manager.*`（全部2个） | V$RSRC_CONSUMER_GROUP 无 CPU 列 |
| RAC | `gc_cr_block_received`, `gc_current_block_received` | 无此统计项 |

---

## FAQ

**Q: 连接报错 `ImportError: No module named 'yaspy'`**
A: YashanDB Python 驱动未安装，请从官网下载并安装：`pip install yashandb-python-driver`

**Q: 连接报错 `Connection refused`**
A: 检查 YashanDB 监听端口（默认 1688）是否开放，防火墙是否放行。

**Q: 表空间发现不到数据**
A: 确认监控账号拥有 `SELECT ON DBA_TABLESPACES`、`DBA_DATA_FILES`、`DBA_FREE_SPACE` 权限。

**Q: Zabbix Agent 返回 `ZBX_NOTSUPPORTED`**
A: 手动执行脚本查看错误信息：
```bash
python3 scripts/yashandb_monitor.py --host 127.0.0.1 --port 1688 \
  --user sys --password YourPass --metric yashandb.db.sessions.active
```
查看 stderr 输出中的具体错误。

**Q: Datadog 兼容指标返回 0 或 NULL**
A: 部分指标（如 `gc_average_cr_get_time`）在单机环境下正常返回 0，不是故障。若确认指标在 YashanDB 中不存在，请参考上方 N/A 指标说明。

**Q: 如何监控 HA 多节点 YashanDB？**
A: 修改 `--host` 为多节点格式（YashanDB DSN 支持）：
```
--host "192.168.1.10:1688,192.168.1.11:1688"
```

**Q: 密码中含有特殊字符怎么处理？**
A: YashanDB 驱动中 `/`、`@`、`\` 需转义。建议使用 `--config` 配置文件方式，避免命令行转义问题。

---

## 参考文档

- Datadog Oracle 指标文档：`../analyze/datadog-oracle-metrics.md`
- YashanDB Datadog 兼容性测试报告：`../analyze/datadog_yashandb_final.md`
- New Relic nri-oracledb 源码：[https://github.com/newrelic/nri-oracledb](https://github.com/newrelic/nri-oracledb)（v3.13.0）
- 测试脚本：`../analyze/test_v5.py`

---

## License

MIT License

---

## 贡献

欢迎提交 Issue 和 PR。如发现新的 YashanDB 监控视图或需要增加指标，请在 Issue 中说明。

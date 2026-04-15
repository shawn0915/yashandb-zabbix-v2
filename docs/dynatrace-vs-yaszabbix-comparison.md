# Dynatrace Oracle vs YashanDB Zabbix 监控指标对比

> 更新：v2.4 已补充 `library_cache_hit_ratio`，`invalid_objects`/`stale_statistics` 已在 v2.3 实现（2026-04-11）

> 基于 Dynatrace Oracle Database Extension（2026-02-09 文档）vs yas_zabbix v2.3（121 指标）

---

## 一、指标覆盖重叠部分

两者共同覆盖的核心指标：

| 类别 | Dynatrace | yas_zabbix |
|------|-----------|------------|
| **实例状态** | `oracle.status` | `yashandb.db.status` |
| **运行时间** | `oracle.uptime` | `yashandb.db.uptime` |
| **版本** | `oracle.db_status` | `yashandb.db.version` |
| **活动会话** | `oracle.sessions.active` | `yashandb.active_sessions` |
| **阻塞会话** | `oracle.sessions.blocked` | `yashandb.db.lock.blocking_sessions` |
| **总会话数** | `oracle.sessions.all` | `yashandb.session_count` |
| **死锁** | `oracle.sessions.deadlocks` | `yashandb.db.lock.count`（锁数量） |
| **表空间使用率** | `oracle.tablespaces.usage` | `yashandb.tablespace.in_use` |
| **表空间总/已用/空闲** | `oracle.tablespaces.*` | `yashandb.tablespace.total/used/free` |
| **PGA 已用** | `oracle.memory.pga.used` | `yashandb.process.pga_used_memory` |
| **PGA 分配** | `oracle.memory.pga.allocated` | `yashandb.process.pga_allocated_memory` |
| **PGA 目标** | `oracle.memory.pga.pgaAggregateTarget` | `yashandb.process.pga_max_memory`（近似） |
| **共享池空闲%** | `oracle.memory.sga.cacheBuffer.sharedPoolFree` | `yashandb.shared_pool_free` |
| **物理读取** | `oracle.memory.physicalReads` | `yashandb.physical_reads` |
| **物理写入** | `oracle.memory.io.bytesWritten` | `yashandb.physical_writes` |
| **逻辑读取** | `oracle.memory.sessionLogicalReads` | `yashandb.logical_reads` |
| **内存排序** | `oracle.memory.memorySorts` | `yashandb.memory_sorts_ratio` |
| **磁盘排序** | `oracle.memory.diskSorts` | `yashandb.disk_sorts` |
| **CPU 核心数** | `oracle.cpu.cores` | `yashandb.num_cpus` |
| **CPU 使用率** | `oracle.cpu.foregroundTotal` | `yashandb.host_cpu_utilization` |
| **Redo 生成** | `oracle.memory.sga.redoBuffer.redoSizeIncrease` | `yashandb.redo_generated` |
| **Redo 写入次数** | `oracle.memory.sga.redoBuffer.redoWriteTime` | `yashandb.redo_writes` |
| **会话利用率** | `oracle.limits.sessions_utilization` | `yashandb.session_limit_usage` |
| **进程利用率** | `oracle.limits.processes_utilization` | `yashandb.process_limit` |
| **Buffer 命中率** | `oracle.memory.libraryCacheHitRatio` | `yashandb.buffer_cachehit_ratio` |
| **DB Time** | `oracle.queries.dbTime` | `yashandb.db.sql.executions_per_sec`（间接） |
| **DB CPU** | `oracle.queries.cpuTime` | `yashandb.db.stat[CPU used by this session]` |
| **SQL 解析** | `oracle.queries.sqlParse` | `yashandb.hard_parses` |
| **用户调用** | `oracle.sessions.userCalls` | `yashandb.sorts_per_user_call`（间接） |
| **等待事件次数** | `oracle.wait.events.count` | `yashandb.db.wait.total_waits` |
| **等待事件时间** | `oracle.wait.events.time` | `yashandb.db.wait.time_waited_ms` |
| **网络流量** | — | `yashandb.network_traffic_volume` |
| **Redo 刷盘速度** | — | `yashandb.db.redo.flush_speed` |
| **Redo 空闲空间** | — | `yashandb.db.redo.free_space` |
| **索引分裂** | — | `yashandb.branch/leaf_node_splits` |
| **长事务** | — | `yashandb.db.long_transactions` |
| **HA 同步延迟** | `oracle.dataguard.seqDifference` | `yashandb.db.ha.sync_delay` |
| **数据文件状态** | `oracle.datafile.status` | `yashandb.tablespace.offline` |

---

## 二、Dynatrace 有、yas_zabbix 缺失的指标

### 🔴 高优先级（推荐补充）

| 指标 | Dynatrace Key | 说明 |
|------|--------------|------|
| **数据块损坏检测** | `oracle.datafile.corrupted_blocks` | V$DATABASE_BLOCK_CORRUPTION，防止静默数据损坏 |
| **ASM 磁盘组使用率** | `oracle.asm.disk_group.usage` | ASM 环境下磁盘组容量监控 |
| **ASM 磁盘组总/空闲空间** | `oracle.asm.disk_group.free_mb/total_mb` | ASM 磁盘组空间 |
| **ASM 单盘读写次数** | `oracle.asm.disk.reads/writes.count` | 定位热点盘 |
| **库缓存命中率** | `oracle.memory.libraryCacheHitRatio` | 评估 SQL 重用率 |
| **DB Block Gets（缓存）** | `oracle.memory.dbBlockGetsFromCache` | 缓冲区缓存效率细分 |
| **Consistent Gets（缓存）** | `oracle.memory.consistentGetsFromCache` | 一致读缓存效率细分 |
| **直接物理读取** | `oracle.memory.physicalReadsDirect` | 绕过缓存的直接读取 |
| **物理读取进缓存** | `oracle.memory.physicalReadsCache` | 进入缓冲区缓存的物理读取 |
| **快速恢复区（FRA）使用率** | `oracle.fra.usage` | Flash Recovery Area 利用率 |
| **FRA 限制/已用/可回收** | `oracle.fra.*` | FRA 容量管理 |
| **等待事件 Top20 明细** | `oracle.wait.events.count/time` | 按事件名细分的等待统计 |
| **归档目标错误数** | `oracle.dataguard.archiveDestErrStatus` | Data Guard 健康度 |

### 🟡 中等优先级

| 指标 | Dynatrace Key | 说明 |
|------|--------------|------|
| **RAC 实例间延迟** | `oracle.rac.instance_ping` | RAC 集群节点网络健康 |
| **RAC 互连流量** | `oracle.rac.interconnects` | 集群内部通信 |
| **Top-N 最耗时 SQL** | `oracle.topN.queries` | 捕获最消耗资源的 SQL（注意敏感数据） |
| **连接管理时间** | `oracle.queries.connectionManagement` | 连接建立/断开开销 |
| **PL/SQL 执行时间** | `oracle.queries.plSqlExec` | 存储过程性能 |
| **SQL 执行时间** | `oracle.queries.sqlExec` | SQL 层执行耗时 |
| **DB Time / DB CPU** | `oracle.queries.dbTime/cpuTime` | 整体负载量化 |
| **Checkpoint 完成数** | `oracle.io.checkpoints` | 检查点频率监控 |
| **NOLOGGING 活动** | `oracle.dataguard.nologgingActivity` | Data Guard 潜在数据丢失风险 |
| **备份状态/耗时/压缩比** | `oracle.backup.*` | RMAN 备份作业监控 |
| **PDB 多租户信息** | `oracle.pdb-*` | 可插拔数据库容量 |

---

## 三、yas_zabbix 有、Dynatrace 缺失的指标

| 指标 | 说明 | Dynatrace 对应 |
|------|------|--------------|
| `yashandb.db.version` | 数据库版本号 | 无（Dynatrace 只报告状态） |
| `yashandb.db.redo.flush_speed` | Redo 刷盘速度（字节/秒） | 无直接对应 |
| `yashandb.db.redo.checkpoint_lag` | 检查点落后量 | 无直接对应 |
| `yashandb.db.redo.log_switches` | Redo 日志切换次数 | 无直接对应 |
| `yashandb.db.long_transactions` | 超过 3 分钟的长事务 | 无直接对应 |
| `yashandb.db.lock.count` | 当前锁数量 | 无直接对应（只有死锁数） |
| `yashandb.cache_blocks_lost` | 缓存块丢失（Lost Write 检测） | 无直接对应 |
| `yashandb.invalid_objects` | 无效对象数量 | 无 |
| `yashandb.stale_statistics` | 陈旧统计信息表数 | 无 |
| `yashandb.tablespace_remaining_days` | 表空间耗尽预测天数 | 无 |
| `yashandb.datafile_max_usage_pct` | 数据文件最大容量使用率 | 无 |
| `yashandb.soft_parse_ratio` | 软解析比率 | 无 |
| `yashandb.dbms_stats_available` | DBMS_STATS 包可用性 | 无 |
| `yashandb.gc_average_cr/current_get_time` | 全局缓存获取时间 | 无（YashanDB 特有） |
| `yashandb.branch/leaf_node_splits` | 索引分裂次数 | 无 |
| `yashandb.avg_synchronous_single_block_read_latency` | 单块读延迟 | 无直接对应 |
| `yashandb.sql.top_buffer_gets/executions` | Top SQL（按 buffer gets / 执行次数） | Dynatrace 有 TopN，但功能集不同 |

---

## 四、结论与补充建议

### 覆盖度评估

- **基础指标**：两者覆盖度约 70% 重叠（会话、内存、I/O、表空间等核心指标）
- **高可用**：都有 Data Guard 相关指标，但 Dynatrace 更细（归档目标状态、NOLOGGING）
- **存储**：Dynatrace 有 ASM 详细监控和 FRA；yas_zabbix 有数据文件容量和表空间预测
- **性能诊断**：Dynatrace 有 Top SQL 和库缓存命中率；yas_zabbix 有 Top SQL 和慢 SQL
- **健康检查**：yas_zabbix 独有无效对象、陈旧统计、损坏块检测
- **备份**：Dynatrace 有完整 RMAN 作业监控；yas_zabbix 无
- **RAC**：Dynatrace 有节点间延迟监控；yas_zabbix 无

### 建议补充到 yas_zabbix 的指标（按优先级）

1. **`yashandb.datafile.corrupted_blocks`** — V$DATABASE_BLOCK_CORRUPTION，核心安全指标
2. **`yashandb.library_cache_hit_ratio`** — 库缓存命中率
3. **`yashandb.wait_events.top`** — 按等待事件名细分的 Top 等待（可复用现有 V$SESSION_EVENT 数据）
4. **`yashandb.asm.disk_group.*`** — ASM 磁盘组使用率/空间（仅 YashanDB 使用 ASM 时需要）
5. **`yashandb.fra.usage`** — 快速恢复区使用率
6. **`yashandb.invalid_objects`** — 无效对象检测（已有代码，可升级为独立指标）
7. **`yashandb.stale_statistics`** — 陈旧统计信息（已有代码，可升级为独立指标）

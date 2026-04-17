# yashandb-zabbix-v2 项目介绍

全网搜了一下如何用 Zabbix 监控崖山数据库 YashanDB，内容比较很少，所以我准备研究的这个项目：YashanDB 与 Zabbix 的监控适配方案。很多企业内部已经部署了 Zabbix 集中监控平台，虽然 YCM 更专业更懂 YashanDB，但接入统一监控平台更便于管理。

## 01. 作品简介：yashandb-zabbix-v2 是什么

这个项目的相关文件已上传到 GitHub 上的 https://github.com/shawn0915/yashandb-zabbix-v2

yashandb-zabbix-v2 是一个专门为 YashanDB 崖山数据库打造的 Zabbix 监控插件。

核心定位：通过 Zabbix Agent UserParameter 机制，使用 YashanDB 官方提供的 Skills 技能包让 AI IDE 自行安装 Python 驱动（yaspy）连接数据库，实现企业级监控覆盖。

适配版本：
- YashanDB 23.4 LTS
- Zabbix 7.0 LTS / 7.4.x

### 指标命名空间设计

该项目总计 125 个可用监控指标，覆盖 28 个监控维度。

设计项目时，参考了 YCM、Zabbix for Oracle、Datadog、New Relic、Dynatrace、Nagios 等项目。

| 命名空间 | 指标数量 | 说明 |
|---------|---------|------|
| yashandb.db.*（原生） | 33 | v1.0 原有指标 + v2.1 新增长事务/HA/Redo切换 |
| yashandb.*（Datadog Oracle 兼容） | 42 | 与 Datadog Oracle 监控指标兼容 |
| yashandb.db.*（New Relic 适配） | 41 | 适配 New Relic nri-oracledb 监控指标 |
| Nagios 适配（v2.3 新增） | 9 | 适配 check_oracle_health 模式 |

从第三方视角来看，这个项目最大的亮点是**多命名空间兼容设计**。它不只是简单地把 YashanDB 的监控数据抛给 Zabbix，而是同时兼容了 Datadog 和 New Relic 的指标命名规范。

## 02. 在 WorkBuddy 中使用的提示词

笔者这次尝试用腾讯的 WorkBuddy AI 助手来辅助整个适配过程。作为一款面向职场的 AI Agent 桌面工作台，WorkBuddy 在处理这类技术文档和代码生成任务时表现相当不错。

以下是我实际使用过的几组核心提示词，仅供参考：

### 提示词一：项目架构梳理

```
请帮我分析 YashanDB 数据库的监控架构，需要涵盖：
1. 单机、分布式集群、共享集群三种部署形态的监控差异
2. 需要采集的核心动态视图（V$INSTANCE, V$SESSION, V$SQL 等）
3. 与 Oracle 监控视图的差异点
4. 输出一份适合 Zabbix 监控插件设计的指标清单
```

### 提示词二：SQL 查询生成

```
我需要为 YashanDB 编写监控 SQL，请根据以下要求生成：
- 目标：获取 Buffer Pool 命中率
- 可用视图：V$BUFFER_POOL_STATISTICS, V$SYSSTAT
- 注意 YashanDB 使用大写无括号的统计项名称（如 DISK READS）
- 输出完整的 SQL 语句，包含注释说明
```

### 提示词三：Zabbix 模板生成

```
请帮我生成 Zabbix 监控项的 XML 配置片段：
- 监控项名称：yashandb.db.buffer_pool_hit
- 类型：Zabbix Agent
- 键值：yashandb.db.buffer_pool_hit
- 数据类型：数字（浮点数）
- 单位：%
- 更新间隔：300秒
- 需要包含触发器表达式：命中率低于90%时告警
```

### 提示词四：异常处理建议

```
YashanDB 中以下 Oracle 视图不存在，请提供替代方案：
- V$LIBRARYCACHE（库缓存）
- V$ROWCACHE（行缓存）
- V$PGASTAT（PGA 统计）
- V$SYS_TIME_MODEL（时间模型）

请针对每个缺失的视图，说明：
1. 该视图原本用于监控什么指标
2. YashanDB 是否有等效视图
3. 如果没有，建议如何 workaround
```

### 提示词五：代码审查

```
请审查以下 Python 监控脚本，关注：
1. 数据库连接是否有资源泄漏风险
2. 异常处理是否完善
3. SQL 注入防护是否到位
4. 性能优化建议
```

使用 WorkBuddy 处理这些提示词的整体感受是：响应速度快，技术理解准确，代码生成质量高。特别是在处理 YashanDB 与 Oracle 的视图差异时，AI 能够快速定位到具体的替代方案，省去了大量查阅文档的时间。

## 03. 功能介绍：125 个监控指标全解析

这个项目最让笔者惊喜的是其监控覆盖的完整性。下面按照监控维度逐一拆解：

### 3.1 实例状态监控（4 项）

| 监控项 | Zabbix Key | 采集间隔 |
|-------|-----------|---------|
| 实例状态 | yashandb.db.status | 60s |
| 运行时长 | yashandb.db.uptime | 300s |
| 数据库版本 | yashandb.db.version | 3600s |
| 运行模式 | yashandb.db.mode | 300s |

实例状态是最基础的监控，返回值 0 表示异常，1 表示正常。配合运行时长可以检测数据库是否发生过非计划重启。

### 3.2 会话与连接监控（13 项）

```sql
-- 活跃会话数查询示例
SELECT COUNT(*) FROM V$SESSION WHERE STATUS = 'ACTIVE';
```

| 类别 | 原生指标 | Datadog 兼容 | 说明 |
|-----|---------|-------------|------|
| 活跃会话 | yashandb.db.sessions.active | yashandb.active_sessions | 当前正在执行的会话 |
| 总会话 | yashandb.db.sessions.total | yashandb.session_count | 包含空闲会话 |
| 等待会话 | yashandb.db.sessions.waiting | - | 处于等待状态的会话 |
| 后台会话 | - | yashandb.active_background | 后台进程会话数 |

### 3.3 缓存与内存监控（16 项）

Buffer Pool 命中率是核心指标之一：

```sql
-- YashanDB Buffer Pool 命中率计算
SELECT 
  ROUND((1 - (a.VALUE / (a.VALUE + b.VALUE))) * 100, 2) AS hit_ratio
FROM 
  V$SYSSTAT a,  -- DISK READS
  V$SYSSTAT b   -- CONSISTENT GETS + DB BLOCK GETS
WHERE 
  a.NAME = 'DISK READS'
  AND b.NAME = 'CONSISTENT GETS';
```

注意：YashanDB 的 `V$SYSSTAT` 使用大写无括号命名（如 `DISK READS`），与 Oracle 的 `physical reads` 不同，这是适配时需要特别注意的点。

### 3.4 表空间监控（自动发现 LLD）

表空间监控支持 Zabbix 的低级发现（LLD）机制，可以自动发现所有表空间并创建对应的监控项：

| Key 原型 | 说明 |
|---------|------|
| yashandb.tablespace.discovery | 自动发现所有表空间 |
| yashandb.tablespace.total | 指定表空间总大小（字节） |
| yashandb.tablespace.used | 指定表空间已使用（字节） |
| yashandb.tablespace.pct_used | 指定表空间使用率（%） |

### 3.5 长事务与高可用监控

这是笔者实测后觉得非常实用的三个新增指标：

| 监控项 | Zabbix Key | 说明 |
|-------|-----------|------|
| 长事务数 | yashandb.db.long_transactions | 超过3分钟的活跃事务数 |
| 主备延迟 | yashandb.db.ha.sync_delay | 主备间归档序列号间隙数量 |
| Redo 切换 | yashandb.db.redo.log_switches | 近24小时 Redo 日志切换次数 |

长事务监控的实现很有意思。YashanDB 没有 Oracle 的 `SES_ADDR` 字段，需要通过 `V$TRANSACTION` JOIN `V$SESSION` 的 `SID` 字段来关联：

```sql
-- 长事务查询（YashanDB 特有实现）
SELECT COUNT(*) 
FROM V$TRANSACTION t
JOIN V$SESSION s ON t.SID = s.SID  -- 注意：用 SID 而非 SES_ADDR
WHERE s.STATUS = 'ACTIVE' 
  AND (SYSDATE - t.START_DATE) * 86400 > 180;  -- 3分钟
```

### 3.6 Nagios 兼容指标

v2.3 版本引入了 Nagios check_oracle_health 的适配，以下是已实现的 9 个指标：

| Nagios Mode | 对应指标 | 数据来源 |
|------------|---------|---------|
| invalid-objects | db.invalid_objects | DBA_OBJECTS |
| invalid-objects | db.invalid_indexes | DBA_INDEXES |
| stale-statistics | db.stale_statistics | DBA_TAB_STATISTICS |
| soft-parse-ratio | db.soft_parse_ratio | V$SYSSTAT |
| tablespace-remaining-time | db.tablespace_remaining_days | DBA_TABLESPACE_USAGE_METRICS |
| datafiles-existing | db.datafile_max_usage_pct | DBA_DATA_FILES |

### 3.7 告警规则配置

项目中预置了 20+ 条告警规则，覆盖常见故障场景：

| 触发器名称 | 级别 | 条件 |
|-----------|------|------|
| 实例不可用 | 灾难 | yashandb.db.status = 0 |
| Buffer Pool 命中率过低 | 警告 | 命中率 < 90% |
| 存在长事务 | 警告 | long_transactions >= 1 |
| 主备同步延迟过高 | 警告 | ha.sync_delay >= 1 |
| 表空间使用率严重 | 高危 | 使用率 > 90% |
| 存在阻塞会话 | 一般 | blocking_sessions > 0 |

## 04. 历史会话：版本演进之路

从 GitHub 的提交历史来看，这个项目经历了多个重要版本的迭代：

### v1.0 基础版本（2026-03）

- 实现 33 个原生监控指标
- 覆盖实例状态、会话、SQL 性能、缓存、Redo 日志等基础维度
- 建立 yashandb.db.* 命名空间

### v2.0 Datadog 兼容（2026-03）

- 新增 42 个 Datadog Oracle 兼容指标
- 引入 yashandb.* 命名空间
- 实现表空间自动发现（LLD）

### v2.1 高可用增强（2026-04-10）

- 新增长事务监控（long_transactions）
- 新增主备同步延迟监控（ha.sync_delay）
- 新增 Redo 日志切换频率监控（redo.log_switches）
- 所有新增指标均经过实机验证

### v2.2 New Relic 适配（2026-04-12）

- 新增 41 个 New Relic nri-oracledb 兼容指标
- 新增等待事件监控（按事件和等待类分组）
- 新增 SGA Buffer 监控
- 新增 Top SQL 多维度监控
- 标记 6 个 N/A 指标（YashanDB 无对应视图）

### v2.3 Nagios 适配（2026-04-15）

- 新增 9 个 Nagios check_oracle_health 兼容指标
- 新增无效对象监控
- 新增陈旧统计信息监控
- 新增软解析比率监控
- 新增表空间耗尽时间预测

### 技术演进亮点

从版本演进可以看出作者的技术思路非常清晰：

1. 先打基础：v1.0 先把 YashanDB 自身的监控能力覆盖完整
2. 兼容生态：v2.0 开始兼容主流监控平台的指标规范，降低迁移成本
3. 企业级增强：v2.1 开始关注高可用场景，长事务、主备延迟都是生产环境的核心关注点
4. 持续完善：v2.2 和 v2.3 不断补充边缘场景，让监控覆盖更加完整

## 05. 快速上手：部署指南

如果你也想试试这个监控方案，以下是笔者整理的快速部署步骤：

### 5.1 前置条件

```bash
# 检查 Python 版本（需要 3.6+）
python3 --version

# 安装 YashanDB Python 驱动
pip install yashandb-python-driver

# 验证安装
python3 -c "import yaspy; print('OK')"
```

### 5.2 创建监控账号

```sql
-- 在 YashanDB 中执行（sys 用户下）
CREATE USER zabbix_monitor IDENTIFIED BY "MonitorPass_123";
GRANT CREATE SESSION TO zabbix_monitor;
GRANT SELECT ON V$INSTANCE TO zabbix_monitor;
GRANT SELECT ON V$DATABASE TO zabbix_monitor;
GRANT SELECT ON V$SESSION TO zabbix_monitor;
GRANT SELECT ON V$SQL TO zabbix_monitor;
GRANT SELECT ON V$SYSSTAT TO zabbix_monitor;
GRANT SELECT ON V$BUFFER_POOL_STATISTICS TO zabbix_monitor;
GRANT SELECT ON DBA_TABLESPACES TO zabbix_monitor;
GRANT SELECT ON DBA_DATA_FILES TO zabbix_monitor;
GRANT SELECT ON DBA_FREE_SPACE TO zabbix_monitor;
```

### 5.3 安装监控脚本

```bash
# 克隆仓库
git clone https://github.com/shawn0915/yashandb-zabbix-v2.git /etc/zabbix/scripts/yas_zabbix

# 赋予执行权限
chmod +x /etc/zabbix/scripts/yas_zabbix/scripts/*.py

# 复制 Agent 配置
cp /etc/zabbix/scripts/yas_zabbix/config/yashandb_userparameter.conf.example \
   /etc/zabbix/zabbix_agentd.d/yashandb.conf

# 编辑配置，填入实际连接参数
vi /etc/zabbix/zabbix_agentd.d/yashandb.conf

# 重启 Zabbix Agent
systemctl restart zabbix-agent2
```

### 5.4 导入 Zabbix 模板

| Zabbix 版本 | 模板文件 |
|------------|---------|
| 7.0 LTS | template/yashandb_zabbix_template_7.0.xml |
| 7.4.x | template/yashandb_zabbix_template.xml |

导入步骤：登录 Zabbix Web UI → 配置 → 模板 → 导入 → 选择对应版本的模板文件。

### 5.5 手动测试

```bash
# 测试连接并获取实例状态
python3 scripts/yashandb_monitor.py \
  --host 127.0.0.1 --port 1688 \
  --user zabbix_monitor --password MonitorPass_123 \
  --metric yashandb.db.status

# 测试表空间使用率（指定表空间名）
python3 scripts/yashandb_monitor.py \
  --host 127.0.0.1 --port 1688 \
  --user sys --password YourPass \
  --metric "yashandb.tablespace.pct_used[SYSTEM]"
```

## 06. YashanDB 与 Oracle 的视图差异

在实际适配过程中，笔者发现 YashanDB 虽然高度兼容 Oracle，但在部分动态视图上仍有差异。以下是关键差异点汇总：

### 6.1 不存在的 Oracle 视图

| Oracle 视图 | YashanDB 状态 | 替代方案 |
|------------|--------------|---------|
| V$LIBRARYCACHE | ❌ 不存在 | 标记为 N/A |
| V$ROWCACHE | ❌ 不存在 | 标记为 N/A |
| V$PGASTAT | ❌ 不存在 | 使用 V$PROCESS 替代 |
| V$SYS_TIME_MODEL | ❌ 不存在 | 标记为 N/A |
| V$RESOURCE_LIMIT | ❌ 不存在 | 使用 V$PARAMETER+V$PROCESS 估算 |
| V$DATAGUARD_STATS | ❌ 不存在 | 标记为 N/A |

### 6.2 V$SYSSTAT 统计项命名差异

| Oracle | YashanDB | 状态 |
|-------|---------|------|
| physical reads | DISK READS | ✅ 可用 |
| physical writes | DISK WRITES | ✅ 可用 |
| user commits | COMMITS | ✅ 可用 |
| user rollbacks | ROLLBACKS | ✅ 可用 |
| parse count (hard) | PARSE COUNT (HARD) | ✅ 可用 |
| parse count (total) | 不存在 | ❌ 不可用 |

### 6.3 YashanDB 特有视图

| 视图 | 说明 | 替代的 Oracle 功能 |
|-----|------|------------------|
| V$SGA | SGA 各组件大小 | 替代 V$SGAINFO |
| V$SGASTAT | SGA 详细统计 | 共享池统计 |
| V$OSSTAT | OS 统计 | 系统资源统计 |


## 总结：选型建议与技术趋势

通过这段时间对 yashandb-zabbix-v2 项目的深入研究，结合笔者十余年的 DBA 经验，总结以下几点建议：

1. 国产化监控方案值得投入：YashanDB 作为国产数据库的优秀代表之一，其监控生态正在快速完善。这个 Zabbix 插件的 125 个监控指标已经能够覆盖绝大多数生产场景。

2. 多命名空间设计是亮点：同时兼容原生、Datadog、New Relic 三种指标规范，大大降低了从 Oracle 迁移到 YashanDB 的监控迁移成本。

3. 注意视图差异：虽然 YashanDB 高度兼容 Oracle，但在部分动态视图上仍有差异。建议在投产前进行充分的指标验证。

4. AI 辅助开发提效明显：使用 WorkBuddy 这类 AI 助手辅助监控插件开发，可以将开发周期缩短 30% 以上，特别是在处理 SQL 查询生成和代码审查环节。

5. 需要持续迭代更新：随着实践案例增加和 YashanDB 23.5 版本发布，该项目也需要继续迭代更新。后续还可以增加多渠道高级，使用 YashanClaw 或者其他 Agent 进行日常巡检、生成日报月报等。

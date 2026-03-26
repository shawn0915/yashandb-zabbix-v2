# yas_zabbix

> YashanDB 数据库 Zabbix 监控插件
>
> **适配版本：YashanDB 23.4 LTS + Zabbix 7.4.x**

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
- [FAQ](#faq)

---

## 功能简介

本插件通过 **Zabbix Agent UserParameter** 机制，使用 YashanDB 官方 Python 驱动（`yaspy`）连接数据库，采集以下维度的监控指标：

| 类别 | 指标数量 | 说明 |
|------|----------|------|
| 实例状态 | 4 | 存活状态、版本、启动时长、运行模式 |
| 会话管理 | 4 | 活跃/总/等待会话数、最大会话限制 |
| 内存 | 5 | Buffer Pool 大小/使用/命中率，VM Pool |
| Redo 日志 | 3 | 刷盘速度、空闲空间、检查点落后量 |
| SQL 性能 | 4 | 执行次数、平均时长、慢 SQL、解析次数 |
| 等待事件 | 3 | TOP 等待事件、总等待次数/时间 |
| 锁 | 2 | 锁数量、阻塞会话数 |
| 表空间（LLD）| 4 × N | 每个表空间的总/已用/剩余/使用率 |

---

## 目录结构

```
yas_zabbix/
├── scripts/
│   ├── yashandb_monitor.py      # 核心采集脚本（单指标模式）
│   └── yashandb_bulk.py         # 批量采集脚本（调试/诊断用）
├── config/
│   └── yashandb_userparameter.conf.example   # Zabbix Agent 配置示例
├── template/
│   └── yashandb_zabbix_template.xml          # Zabbix 导入模板
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

> **注意**：`yaspy` 需从 YashanDB 官方渠道获取，暂未发布到 PyPI。  
> 下载地址：[https://yashandb.com/downloads](https://yashandb.com/downloads)

### 4. 创建监控专用数据库账号（推荐）
```sql
-- 在 YashanDB 中执行
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

编辑 `config/yashandb_userparameter.conf.example`，取消注释并修改：

```ini
# Linux 示例
UserParameter=yashandb.db.status,/usr/bin/python3 /etc/zabbix/scripts/yas_zabbix/yashandb_monitor.py --host 127.0.0.1 --port 1688 --user zabbix_monitor --password "MonitorPass_123" --metric db.status

UserParameter=yashandb.db.version,/usr/bin/python3 /etc/zabbix/scripts/yas_zabbix/yashandb_monitor.py --host 127.0.0.1 --port 1688 --user zabbix_monitor --password "MonitorPass_123" --metric db.version

UserParameter=yashandb.sessions.active,/usr/bin/python3 /etc/zabbix/scripts/yas_zabbix/yashandb_monitor.py --host 127.0.0.1 --port 1688 --user zabbix_monitor --password "MonitorPass_123" --metric db.sessions.active

# 带参数的表空间（$1 由 Zabbix LLD 自动传入表空间名）
UserParameter=yashandb.tablespace.pct_used[*],/usr/bin/python3 /etc/zabbix/scripts/yas_zabbix/yashandb_monitor.py --host 127.0.0.1 --port 1688 --user zabbix_monitor --password "MonitorPass_123" --metric "db.tablespace.pct_used[$1]"
```

> **安全建议**：生产环境请使用 `--config` 参数指向外部配置文件，避免密码出现在命令行中：
> ```ini
> UserParameter=yashandb.db.status,/usr/bin/python3 /etc/zabbix/scripts/yas_zabbix/yashandb_monitor.py --config /etc/zabbix/scripts/yas_zabbix/config/yashandb.conf --host x --user x --password x --metric db.status
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

1. 登录 Zabbix Web UI
2. 进入 **配置 → 模板 → 导入**
3. 选择文件：`template/yashandb_zabbix_template.xml`
4. 点击 **导入**
5. 将模板 **"YashanDB by Zabbix Agent"** 关联到目标主机
6. 在主机宏中配置连接参数（见下方宏配置）

---

## 监控指标说明

### 实例状态

| Zabbix Key | 说明 | 采集间隔 |
|-----------|------|---------|
| `yashandb.db.status` | 实例状态（1=正常/0=异常） | 60s |
| `yashandb.db.version` | 数据库版本号 | 3600s |
| `yashandb.db.uptime` | 启动时长（秒） | 300s |
| `yashandb.db.mode` | 运行模式（PRIMARY/STANDBY） | 300s |

### 会话

| Zabbix Key | 说明 | 采集间隔 |
|-----------|------|---------|
| `yashandb.sessions.active` | 活跃会话数 | 60s |
| `yashandb.sessions.total` | 总会话数 | 60s |
| `yashandb.sessions.waiting` | 等待中会话数 | 60s |
| `yashandb.sessions.max` | 最大会话限制 | 3600s |

### 内存

| Zabbix Key | 说明 | 采集间隔 |
|-----------|------|---------|
| `yashandb.memory.buffer_pool_size` | Buffer Pool 总大小 | 300s |
| `yashandb.memory.buffer_pool_used` | Buffer Pool 已使用 | 300s |
| `yashandb.memory.buffer_pool_hit` | Buffer Pool 命中率(%) | 300s |
| `yashandb.memory.vm_pool_size` | VM Pool 总大小 | 300s |
| `yashandb.memory.vm_pool_used` | VM Pool 已使用 | 300s |

### 表空间（自动发现 LLD）

通过 `yashandb.tablespace.discovery` 自动发现所有表空间，并为每个表空间创建：

| Key 原型 | 说明 |
|---------|------|
| `yashandb.tablespace.total[{#TS}]` | 总大小（字节） |
| `yashandb.tablespace.used[{#TS}]` | 已使用（字节） |
| `yashandb.tablespace.free[{#TS}]` | 剩余空间（字节） |
| `yashandb.tablespace.pct_used[{#TS}]` | 使用率（%） |

### SQL 性能

| Zabbix Key | 说明 | 采集间隔 |
|-----------|------|---------|
| `yashandb.sql.executions_per_sec` | 每秒执行次数 | 60s |
| `yashandb.sql.avg_elapsed_ms` | 平均执行时长(ms) | 120s |
| `yashandb.sql.slow_count` | 慢SQL数量(>1s) | 120s |
| `yashandb.sql.parse_count` | SQL解析次数 | 120s |

---

## 告警规则

模板内置以下告警触发器：

| 触发器名称 | 级别 | 条件 |
|-----------|------|------|
| 实例不可用 | 灾难(DISASTER) | `db.status = 0` |
| 数据库最近重启 | 警告(WARNING) | `uptime < 300s` |
| Buffer Pool 命中率过低 | 警告(WARNING) | `命中率 < {$YASHANDB.BUFFER.HIT.MIN}` |
| 慢 SQL 数量过多 | 警告(WARNING) | `慢SQL数 > {$YASHANDB.SLOW_SQL.WARN}` |
| 锁数量过多 | 警告(WARNING) | `锁数 > {$YASHANDB.LOCK.WARN}` |
| 存在阻塞会话 | 一般(AVERAGE) | `blocking_sessions > 0` |
| 表空间使用率告警 | 警告(WARNING) | `使用率 > {$YASHANDB.TABLESPACE.WARN}` |
| 表空间使用率严重 | 高危(HIGH) | `使用率 > {$YASHANDB.TABLESPACE.CRIT}` |

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
| `{$YASHANDB.TABLESPACE.WARN}` | `80` | 表空间告警阈值(%) |
| `{$YASHANDB.TABLESPACE.CRIT}` | `90` | 表空间严重告警阈值(%) |
| `{$YASHANDB.SLOW_SQL.WARN}` | `10` | 慢SQL告警阈值 |
| `{$YASHANDB.LOCK.WARN}` | `20` | 锁数量告警阈值 |

---

## 手动测试

```bash
# 测试连接并获取实例状态
python3 scripts/yashandb_monitor.py \
  --host 127.0.0.1 --port 1688 \
  --user zabbix_monitor --password MonitorPass_123 \
  --metric db.status

# 测试表空间使用率（指定表空间名）
python3 scripts/yashandb_monitor.py \
  --host 127.0.0.1 --port 1688 \
  --user zabbix_monitor --password MonitorPass_123 \
  --metric "db.tablespace.pct_used[SYSTEM]"

# 批量采集所有指标（诊断用）
python3 scripts/yashandb_bulk.py \
  --host 127.0.0.1 --port 1688 \
  --user zabbix_monitor --password MonitorPass_123 \
  --json

# 通过 Zabbix Agent 测试（需先配置 UserParameter）
zabbix_agentd -t yashandb.db.status
zabbix_agentd -t yashandb.sessions.active
zabbix_agentd -t "yashandb.tablespace.pct_used[SYSTEM]"
```

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
  --user sys --password YourPass --metric db.sessions.active
```
查看 stderr 输出中的具体错误。

**Q: 如何监控 HA 多节点 YashanDB？**  
A: 修改 `--host` 为多节点格式（YashanDB DSN 支持）：
```
--host "192.168.1.10:1688,192.168.1.11:1688"
```

**Q: 密码中含有特殊字符怎么处理？**  
A: YashanDB 驱动中 `/`、`@`、`\` 需转义。建议使用 `--config` 配置文件方式，避免命令行转义问题。

---

## License

MIT License

---

## 贡献

欢迎提交 Issue 和 PR。如发现新的 YashanDB 监控视图或需要增加指标，请在 Issue 中说明。

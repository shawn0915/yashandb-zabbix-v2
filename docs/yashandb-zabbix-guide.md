# YashanDB Zabbix 监控系统从零搭建完整指南

> **版本**：v3.3（2026-04-13，移除 7 个 N/A 指标 + 同步文档）
> **适配**：YashanDB 23.4 LTS + Zabbix 7.0/7.4 + Zabbix Agent 7.0/7.4
> **方法**：基于 WorkBuddy AI Agent 辅助运维，涵盖 agent-browser、zabbix_api、浏览器自动化等技能

---

## 目录

1. [系统概览与架构设计](#1-系统概览与架构设计)
2. [环境准备](#2-环境准备)
3. [Docker 快速启动 YashanDB](#3-docker-快速启动-yashandb)
4. [Docker 快速启动 Zabbix Server + Web](#4-docker-快速启动-zabbix-server--web)
5. [Zabbix Agent 部署与 Zabbix API 认证](#5-zabbix-agent-部署与-zabbix-api-认证)
6. [监控指标采集脚本](#6-监控指标采集脚本)
7. [Zabbix 模板导入与主机配置](#7-zabbix-模板导入与主机配置)
8. [Dashboard 创建与 Zabbix 7.x API 关键坑](#8-dashboard-创建与-zabbix-7x-api-关键坑)
9. [WorkBuddy Agent 运维技巧](#9-workbuddy-agent-运维技巧)
10. [压测验证与故障排查](#10-压测验证与故障排查)
11. [版本历史](#11-版本历史)
12. [Rocky Linux 10 完整部署指南](#12-rocky-linux-10-完整部署指南)
13. [全部监控指标清单](#13-全部监控指标清单)
14. [告警阈值建议](#13-全部监控指标清单)（见第13章）

---

## 1. 系统概览与架构设计

### 1.1 整体架构

```
Windows 宿主机 (PowerShell)
│
├── Docker Desktop (WSL2)
│   ├── yas_oracle (YashanDB 23.4.7.100)    :1688
│   ├── zabbix-server (Alpine-7.4.9)          :10051
│   ├── zabbix-web    (Alpine-7.4.9)          :8080
│   └── yas-zabbix-agent (CentOS-7.0.25)      :10050
│
└── WSL Ubuntu
    └── MySQL 8.4                             :3308 (zabbix 数据库)
```

**数据流**：
```
YashanDB (:1688)
  ↓  SQL 查询 (yaspy / libyascli.so)
yas-zabbix-agent (:10050)  ← Zabbix Agent2 7.0.25
  ↓  Zabbix Sender Protocol (:10051)
zabbix-server (:10051)     ← Zabbix Server 7.4.9
  ↓  MySQL (:3308)
zabbix-web (:8080)         ← 用户访问
```

### 1.2 核心组件版本

| 组件 | 版本 | 镜像/来源 |
|------|------|---------|
| YashanDB | 23.4.7.100 | `docker.1ms.run/yasdb/yashandb:23.4.7.100` |
| Zabbix Server | 7.4.9 | `zabbix/zabbix-server-mysql:alpine-7.4-latest` |
| Zabbix Web | 7.4.9 | `zabbix/zabbix-web-nginx-mysql:alpine-7.4-latest` |
| Zabbix Agent (Docker) | 7.0.25 | `yas-zabbix-agent:v2.5`（CentOS Stream 9 自定义镜像） |
| Zabbix Agent (Rocky 10) | 7.4.9 | `zabbix/7.4/rhel/10/x86_64` RPM |
| Python 驱动 | yaspy 1.2.0 | `git+https://github.com/yashan-technologies/yashandb-python` |
| MySQL (Zabbix DB) | 8.4 | WSL 内建，端口 3308 |

> **Agent 与 Server 版本兼容性**：Agent 7.0 与 Server 7.4 完全兼容（协议向后兼容），版本号无需完全一致。

### 1.3 项目结构

```
yas_zabbix/                    # 监控插件核心仓库
├── scripts/
│   ├── yashandb_monitor.py     # 核心采集脚本（v2.5，133 指标）
│   └── yashandb_bulk.py        # 批量采集脚本（诊断用）
├── config/
│   └── yashandb_userparameter.conf.example
├── template/
│   ├── yashandb_zabbix_template.xml       # Zabbix 7.4
│   └── yashandb_zabbix_template_7.0.xml   # Zabbix 7.0 LTS
└── tests/

yas_zabbix_deploy/             # 部署脚本仓库
├── Dockerfile.yas-zabbix-agent-centos   # Agent 镜像定义
├── agent-entrypoint-centos.sh           # Agent 容器启动脚本
├── wrapper.sh                            # LD_LIBRARY_PATH 注入（核心）
├── deploy-all.ps1                        # Docker 一键部署（PowerShell）
├── verify-all.ps1                        # Docker 验证脚本
├── config/
│   └── yashandb_userparameter_docker.conf  # Docker 版 UserParameter
└── rocky10/                              # Rocky Linux 10 原生部署
    ├── deploy-rocky.sh
    ├── verify-rocky.sh
    └── README.md

analyze/                      # 研究分析报告目录
├── zabbix-server-web-startup.md
├── dynatrace-vs-yaszabbix-comparison.md
├── rebuild_dashboards_v6.py  # Dashboard 创建脚本（含 Bearer Token 修复）
└── [100+ 调试脚本 _*.py]
```

---

## 2. 环境准备

### 2.1 前置要求

| 依赖 | 要求 |
|------|------|
| Docker Desktop | 已安装，WSL2 后端，内存 ≥ 8GB |
| WSL2 | 已启用（`wsl --install`） |
| WSL MySQL | 8.4，端口 3308，对外可访问 |
| 磁盘 | 至少 10 GB 可用 |

### 2.2 创建 Zabbix 数据库

在 WSL MySQL 中执行（只需一次）：

```sql
CREATE DATABASE IF NOT EXISTS zabbix CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
CREATE USER IF NOT EXISTS 'zabbix'@'%' IDENTIFIED BY 'Zabbix2026';
CREATE USER IF NOT EXISTS 'zabbix'@'localhost' IDENTIFIED BY 'Zabbix2026';
GRANT ALL PRIVILEGES ON zabbix.* TO 'zabbix'@'%';
GRANT ALL PRIVILEGES ON zabbix.* TO 'zabbix'@'localhost';
FLUSH PRIVILEGES;
```

### 2.3 创建 Docker 网络

```powershell
docker network create zabbix-net
```

### 2.4 确认 YashanDB SYS 用户密码

YashanDB Docker 容器默认 `SYS_PASSWD=Cod-2022`。启动后确认：

```powershell
docker logs yas_oracle --tail 5
```

---

## 3. Docker 快速启动 YashanDB

### 3.1 一键启动（PowerShell）

```powershell
# 在 PowerShell 中执行
docker run -d `
    --name yas_oracle `
    --restart unless-stopped `
    --network zabbix-net `
    -p 1688:1688 `
    -v C:\Users\DELL\yashan_oracle:/home/yashan/.yasboot `
    -v yas_oracle_data:/data/yashan `
    -e SYS_PASSWD=Cod-2022 `
    docker.1ms.run/yasdb/yashandb:23.4.7.100
```

> **首次启动**：等待约 60 秒初始化（数据库初始化 + Oracle 兼容模式启动）

### 3.2 等待并验证

```powershell
# 等待初始化（每5秒检查一次）
for ($i=0; $i -lt 20; $i++) {
    $s = docker exec yas_oracle bash -c "echo 'SELECT 1;' | yasql sys/Cod-2022" 2>$null
    if ($s) { Write-Host "YashanDB 已就绪"; break }
    Write-Host "等待初始化... ($i/20)"
    Start-Sleep 5
}
```

### 3.3 提取 C 驱动库

yas-zabbix-agent 需要 libyascli.so 等库文件，通过 Docker 卷共享：

```powershell
# 停止 yas_oracle，提取库文件到 Docker 卷
docker stop yas_oracle
docker volume create yas_agent_libs

docker run --rm `
    -v yas_agent_libs:/data alpine sh -c "
        mkdir -p /data/lib &&
        docker cp yas_oracle:/opt/yashandb/yashandb_yasdb_home/lib/. /data/lib/ &&
        ls /data/lib/ | grep -i yas
    "

docker start yas_oracle
```

> **关键**：卷 `yas_agent_libs` 挂载到 `/opt/yashandb/yashandb_yasdb_home:ro`（只读），避免容器销毁后库文件丢失。

---

## 4. Docker 快速启动 Zabbix Server + Web

### 4.1 Zabbix Server

```powershell
docker run -d `
    --name zabbix-server `
    --restart unless-stopped `
    --network zabbix-net `
    -p 10051:10051 `
    -e DB_SERVER_HOST=host.docker.internal `
    -e DB_SERVER_PORT=3308 `
    -e MYSQL_DATABASE=zabbix `
    -e MYSQL_USER=zabbix `
    -e MYSQL_PASSWORD=Zabbix2026 `
    -e MYSQL_ROOT_PASSWORD=Shawn2026 `
    zabbix/zabbix-server-mysql:alpine-7.4-latest
```

### 4.2 Zabbix Web

```powershell
docker run -d `
    --name zabbix-web `
    --restart unless-stopped `
    --network zabbix-net `
    -p 8080:8080 `
    -e DB_SERVER_HOST=host.docker.internal `
    -e DB_SERVER_PORT=3308 `
    -e MYSQL_DATABASE=zabbix `
    -e MYSQL_USER=zabbix `
    -e MYSQL_PASSWORD=Zabbix2026 `
    -e ZBX_SERVER_HOST=zabbix-server `
    -e PHP_TZ=Asia/Shanghai `
    zabbix/zabbix-web-nginx-mysql:alpine-7.4-latest
```

### 4.3 验证 Web UI

```powershell
# 等待 Web 初始化（约 30 秒）
Start-Sleep 30

# 验证
curl http://localhost:8080/zabbix.php?action=dashboard.view
```

访问 http://localhost:8080，用户名 `Admin`，密码 `zabbix`。

---

## 5. Zabbix Agent 部署与 Zabbix API 认证

### 5.1 构建 yas-zabbix-agent 镜像

> **镜像内容**：CentOS Stream 9 + Zabbix Agent2 7.0.25 + Python 3.9 + yaspy 1.2.0

```powershell
cd C:\Users\DELL\WorkBuddy\Claw\yas_zabbix_deploy
docker build --no-cache `
    -f Dockerfile.yas-zabbix-agent-centos `
    -t yas-zabbix-agent:v2.5 .
```

### 5.2 启动 Agent

```powershell
docker run -d `
    --name yas-zabbix-agent `
    --network zabbix-net `
    -v yas_agent_libs:/opt/yashandb/yashandb_yasdb_home:ro `
    -e YASDB_HOST=yas_oracle `
    -e YASDB_PORT=1688 `
    -e YASDB_USER=sys `
    -e YASDB_PASSWORD=Cod-2022 `
    -e ZBX_SERVER_HOST=zabbix-server `
    -e ZBX_HOSTNAME=yas-zabbix-agent `
    yas-zabbix-agent:v2.5
```

### 5.3 环境变量说明

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `YASDB_HOST` | `yas_oracle` | YashanDB 容器名或 IP |
| `YASDB_PORT` | `1688` | YashanDB 端口 |
| `YASDB_USER` | `sys` | 连接用户名 |
| `YASDB_PASSWORD` | `Cod-2022` | 连接密码 |
| `ZBX_SERVER_HOST` | `zabbix-server` | Zabbix Server 主机名 |
| `ZBX_HOSTNAME` | `yas-zabbix-agent` | Zabbix Agent 标识名 |

### 5.4 Zabbix 7.x API 认证（关键修复）

> **重大变化**：Zabbix 7.x 废弃了 JSON-RPC `auth` 字段，改为 HTTP `Authorization: Bearer <token>` header。

**问题现象**：Zabbix 7.x 调用 `dashboard.create`、`widget.create` 等 API 时返回错误。

**修复方案**：对 `zabbix_api` 库打补丁（文件：`/home/shawnyan/.local/lib/python3.9/site-packages/zabbix_api.py`）。

核心修改：

```python
# 修复 1: do_request() - 添加 Bearer Token header，删除 auth 字段
def do_request(self, method, params):
    data = {"jsonrpc": "2.0", "method": method, "params": params, "id": self._requestid}
    if self.auth_token:
        headers["Authorization"] = f"Bearer {self.auth_token}"
        # 不再把 auth_token 放入 JSON body
    # ...

# 修复 2: api_version() - 先 Bearer auth，失败则 fallback 无 auth
def api_version(self):
    try:
        v = self._do_request({"jsonrpc": "2.0", "method": "apiinfo.version",
                               "params": {}, "id": 0}, auth_token=None)
        # 可能失败，fallback
    except:
        pass

# 修复 3: version_compare() - 处理 None 返回值
def version_compare(self, ver):
    if ver is None:
        return 1  # 假设 >= 7.x
    # ...

# 修复 4: login() - 不依赖 api_version() 版本判断
def login(self, user, password):
    self.auth_token = None
    try:
        resp = self._do_request({
            "jsonrpc": "2.0", "method": "user.login",
            "params": {"username": user, "password": password}, "id": 0
        })
        self.auth_token = resp["result"]
    except:
        pass
```

备份：`zabbix_api.py.bak9`

---

## 6. 监控指标采集脚本

### 6.1 核心脚本结构

`yashandb_monitor.py` 是所有指标的单一入口，接收 `--metric` 参数返回对应值：

```bash
# 基础用法
python3 yashandb_monitor.py --config yashandb.ini --metric db.status
# 输出: 1

python3 yashandb_monitor.py --config yashandb.ini --metric "tablespace.pct_used[SYSTEM]"
# 输出: 72.75

# 批量采集（诊断用）
python3 yashandb_bulk.py --config yashandb.ini --json
```

### 6.2 指标分类（v2.5，133 个）

| 类别 | 数量 | 代表指标 |
|------|------|---------|
| 实例状态 | 4 | `db.status`, `db.version`, `db.uptime`, `db.mode` |
| 会话 | 12 | `active_sessions`, `sessions.active`, `sessions.inactive`, `sessions.waiting` |
| SQL 性能 | 9 | `db.sql.executions_per_sec`, `db.sql.slow_count`, `db.sql.parse_count` |
| 内存/SGA/PGA | 16 | `buffer_cachehit_ratio`, `shared_pool_free`, `pga_allocated_memory` |
| 表空间（LLD） | 10+ | `tablespace.discovery`, `tablespace.pct_used[{#TS}]` |
| 等待事件（LLD） | 8+ | `db.wait_event_waits[{#WAIT_EVENT}]`, `db.wait_event_time[{#WAIT_EVENT}]` |
| Redo 日志 | 8 | `db.redo.flush_speed`, `redo_generated`, `redo.waits` |
| 锁 | 4 | `db.lock.count`, `lock.enqueue_locks`, `lock.enqueue_requests` |
| 物理/逻辑 I/O | 8 | `physical_reads`, `disk.total_reads`, `disk.total_writes` |
| CPU/网络 | 5 | `host_cpu_utilization`, `num_cpus`, `network_traffic_volume` |
| 长事务/HA | 3 | `db.long_transactions`, `ha.sync_delay`, `redo.log_switches` |
| SGA 缓冲区 | 6 | `sga.buffer_busy_waits`, `sga.fixed_size`, `sga.redo_buffers` |
| 对象/统计 | 8 | `db.invalid_objects`, `db.stale_statistics`, `db.soft_parse_ratio` |
| 归档日志 | 3 | `archived_log.count`, `archiver.failed` |
| 其他 | 20+ | `sql.count`, `sql.top_buffer_gets`, `gc_average_cr_get_time` |

### 6.3 wrapper.sh — LD_LIBRARY_PATH 注入（核心原理）

**问题**：zabbix_agentd fork 子进程执行 UserParameter 时，子进程不继承父进程环境变量（包括 `LD_LIBRARY_PATH`）。

**症状**：`YAS-20001 load yacli library error` 或 `symbol not found`。

**解决方案**：每次 UserParameter 调用通过 `wrapper.sh` 执行，在脚本内重新注入：

```bash
#!/bin/bash
# wrapper.sh
YASDB_LIB_PATH="${YASDB_LIB_PATH:-/opt/yashandb/yashandb_yasdb_home/lib}"
export LD_LIBRARY_PATH="${YASDB_LIB_PATH}:${LD_LIBRARY_PATH}"
exec python3 /etc/zabbix/scripts/yashandb/yashandb_monitor.py \
    --config /etc/zabbix/scripts/yashandb/yashandb.ini "$@"
```

**架构**：
```
zabbix_agentd (PID 17)
    │
    └── fork: /bin/bash /etc/zabbix/scripts/yashandb/wrapper.sh --metric db.status
                │
                └── wrapper.sh
                        │
                        └── export LD_LIBRARY_PATH (重新注入!)
                                │
                                └── python3 yashandb_monitor.py --config yashandb.ini
                                        │
                                        └── yaspy.connect() ──→ YashanDB :1688
```

### 6.4 UserParameter 配置

**Docker 版**（`config/yashandb_userparameter_docker.conf`）：

```ini
UserParameter=yashandb.db.status,/bin/bash /etc/zabbix/scripts/yashandb/wrapper.sh --metric db.status
UserParameter=yashandb.db.version,/bin/bash /etc/zabbix/scripts/yashandb/wrapper.sh --metric db.version
UserParameter=yashandb.active_sessions,/bin/bash /etc/zabbix/scripts/yashandb/wrapper.sh --metric active_sessions

# 表空间 LLD（$1 由 Zabbix 传入表空间名）
UserParameter=yashandb.tablespace.pct_used[*],/bin/bash /etc/zabbix/scripts/yashandb/wrapper.sh --metric 'tablespace.pct_used[$1]'
```

> **重要**：不要用 `${#VAR}` 语法（会被 shell 误解析为变量长度操作符），用 `$1` 或 `[*]` + POSIX 标准格式。

---

## 7. Zabbix 模板导入与主机配置

### 7.1 导入模板

1. 下载模板文件：
   - Zabbix 7.4 → `yas_zabbix/template/yashandb_zabbix_template.xml`
   - Zabbix 7.0 → `yas_zabbix/template/yashandb_zabbix_template_7.0.xml`

2. 登录 Zabbix Web：`http://localhost:8080`
   - 用户名：`Admin`
   - 密码：`zabbix`

3. **Configuration → Templates → Import** 上传模板

### 7.2 创建主机

1. **Configuration → Hosts → Create host**
   - Host name: `yas-zabbix-agent`
   - Groups: `Linux servers`（或新建 `YashanDB`）
   - Agent interface: `yas-zabbix-agent`，端口 `10050`

2. **Templates**：链接 `YashanDB by Zabbix Agent`

3. 等待自动发现（表空间 LLD、等待事件 LLD、V$SYSSTAT LLD）

### 7.3 验证指标采集

```powershell
# 在 zabbix-server 容器内用 zabbix_get 测试
docker exec zabbix-server zabbix_get -s yas-zabbix-agent -p 10050 -k "yashandb.db.status"
# 期望输出: 1

docker exec zabbix-server zabbix_get -s yas-zabbix-agent -p 10050 -k "yashandb.db.version"
# 期望输出: Enterprise Edition Release 23.4.7.100 x86_64

docker exec zabbix-server zabbix_get -s yas-zabbix-agent -p 10050 -k "yashandb.tablespace.discovery"
# 期望输出: {"data":[{"{#TS}":"SYSTEM"},...]}
```

---

## 8. Dashboard 创建与 Zabbix 7.x API 关键坑

### 8.1 创建 4 个 Dashboard

| Dashboard | ID | 链接 |
|-----------|-----|------|
| YashanDB 概览 | 462 | http://localhost:8080/zabbix.php?action=dashboard.view&dashboardid=462 |
| YashanDB 性能 | 463 | http://localhost:8080/zabbix.php?action=dashboard.view&dashboardid=463 |
| YashanDB 会话 | 464 | http://localhost:8080/zabbix.php?action=dashboard.view&dashboardid=464 |
| YashanDB 存储 | 465 | http://localhost:8080/zabbix.php?action=dashboard.view&dashboardid=465 |

Dashboard 创建脚本：`analyze/rebuild_dashboards_v6.py`

### 8.2 Graph Widget 字段类型（实测验证）

| 字段 | type | 说明 |
|------|------|------|
| `ds.items` | 1 (String) | JSON 序列化后的数据系列数组 |
| `ds.type` | 0 (Integer) | 绘图类型：0=Line, 1=Points, 2=Staircase, 3=Bar |
| `rf_rate` | 0 (Integer) | 刷新间隔秒数 |
| `source` | 0 (Integer) | 数据源：0=Auto, 1=History, 2=Trends |
| `stacked` | 0 (Integer) | 堆叠模式 |
| `show_legend` | 0 (Integer) | 显示图例 |
| 颜色值 | 纯 6 位 hex，不带 `#` | 如 `1E88E5` |

> **常见错误**：`ds.stype`（错误）→ 应为 `ds.type`（正确）

### 8.3 ds 字段必须 flat 展开

**错误格式**（JSON 字符串）：
```python
{"type": "1", "name": "ds.items",    "value": "[{...}]"}  # ❌
{"type": "0", "name": "ds.type",      "value": 0}           # ❌
```

**正确格式**（flat 字段）：
```python
{"type": "4", "name": "ds.0.itemids.0",       "value": "<itemid>"}  # ITEM类型
{"type": "1", "name": "ds.0.color.0",          "value": "1E88E5"}
{"type": "0", "name": "ds.0.type",              "value": 0}           # Line
{"type": "0", "name": "ds.0.stacked",           "value": 0}
{"type": "0", "name": "ds.0.transparency",      "value": 5}
{"type": "0", "name": "ds.0.dataset_type",      "value": 0}           # SINGLE_ITEM
{"type": "1", "name": "ds.0.hosts.0",           "value": ""}
{"type": "1", "name": "ds.0.items.0",           "value": ""}
```

### 8.4 time_period 字段 — 关键坑（修复过程）

**错误做法 v1**：`{"reference": "dashboard", "type": 0}`
- PHP 反序列化时 `data_source` 判断失败，触发 from/to 验证

**错误做法 v2**：`{"from": "now-1h", "to": "now"}`
- PHP 仍会触发验证错误

**最终正确做法**：完全不设置 `time_period` 字段
- Widget 自动继承 Dashboard 的时间范围（默认 "Last 1 hour"）
- 任何显式设置 time_period 的值都会触发 PHP 验证错误

```python
# ✅ 正确：不要设置 time_period 字段
# ❌ 错误：str_field("time_period.0", json.dumps({"reference": "dashboard", "type": 0}))
# ❌ 错误：str_field("time_period.0", json.dumps({"from": "now-1h", "to": "now"}))
```

### 8.5 Widget "not fully configured" 根因

Dashboard 定义引用了不存在的 item key（如 `yashandb.db.qps`、`yashandb.session.inactive` 等），导致 Widget 报配置不完整。

**关键替代映射**：
| 错误的 key | 正确的 key |
|-----------|-----------|
| `yashandb.db.qps` | `yashandb.db.sql.executions_per_sec` |
| `yashandb.db.tps` | `yashandb.user_commits` |
| `yashandb.session.inactive` | `yashandb.sessions.inactive` |
| `yashandb.session.active` | `yashandb.active_sessions` |
| `yashandb.db.io.read_rate` | `yashandb.disk.total_reads` |
| `yashandb.tablespace.total_size` | `yashandb.tablespace.size` |
| `yashandb.redo.switches` | `yashandb.db.redo.log_switches` |

---

## 9. WorkBuddy Agent 运维技巧

### 9.1 使用 agent-browser 自动化运维

**安装**：
```bash
uvx browser-use install
```

**常用命令**：
```bash
# 打开页面
agent-browser open http://localhost:8080/zabbix.php?action=dashboard.view&dashboardid=462

# 截图
agent-browser screenshot

# 截图到指定路径
agent-browser screenshot ./dashboard-462.png --full

# 点击元素（按元素序号）
agent-browser click @e3

# 填表单
agent-browser fill @e2 "Admin"
agent-browser fill @e3 "zabbix"
agent-browser click @e4  # 登录按钮
```

### 9.2 Zabbix API 自动化脚本

创建 Python 脚本 `analyze/zabbix_query.py`：

```python
import sys
sys.path.insert(0, '/home/shawnyan/.local/lib/python3.9/site-packages')
from zabbix_api import ZabbixAPI

ZBX_URL = "http://localhost:8080/api_jsonrpc.php"
ZBX_USER = "Admin"
ZBX_PASS = "zabbix"

zapi = ZabbixAPI(ZBX_URL, timeout=30)
zapi.login(ZBX_USER, ZBX_PASS)

# 查询所有 Dashboard
dashboards = zapi.dashboard.get({"output": ["dashboardid", "name"]})
for d in dashboards:
    print(f"ID={d['dashboardid']}  {d['name']}")

# 查询主机的所有 items
items = zapi.item.get({
    "host": "yas-zabbix-agent",
    "output": ["itemid", "key_", "name", "status"]
})
print(f"共 {len(items)} 个监控项")

zapi.logout()
```

### 9.3 YashanDB 连接验证

```powershell
# Agent 容器内验证
docker exec yas-zabbix-agent bash -c "
    LD_LIBRARY_PATH=/opt/yashandb/yashandb_yasdb_home/lib
    python3 -c \"
import yaspy
c = yaspy.connect(dsn='yas_oracle:1688', user='sys', password='Cod-2022')
cur = c.cursor()
cur.execute(\"SELECT SYSDATE, VERSION FROM V\\\$INSTANCE\")
print(cur.fetchone())
\"
"
```

### 9.4 一键验证脚本（PowerShell）

```powershell
# 验证所有容器状态
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"

# 验证 Agent
docker exec zabbix-server zabbix_get -s yas-zabbix-agent -p 10050 -k agent.ping
docker exec zabbix-server zabbix_get -s yas-zabbix-agent -p 10050 -k "yashandb.db.status"
docker exec zabbix-server zabbix_get -s yas-zabbix-agent -p 10050 -k "yashandb.buffer_cachehit_ratio"
docker exec zabbix-server zabbix_get -s yas-zabbix-agent -p 10050 -k "yashandb.tablespace.discovery"

# 查看日志
docker logs zabbix-web --tail 10
docker logs yas-zabbix-agent --tail 10
```

### 9.5 重建 Agent 容器（代码更新后）

```powershell
# 更新 yashandb_monitor.py 到部署目录
Copy-Item "C:\Users\DELL\WorkBuddy\Claw\yas_zabbix\scripts\yashandb_monitor.py" `
    "C:\Users\DELL\WorkBuddy\Claw\yas_zabbix_deploy\scripts\yashandb_monitor.py" -Force

# 重建镜像
cd C:\Users\DELL\WorkBuddy\Claw\yas_zabbix_deploy
docker build -f Dockerfile.yas-zabbix-agent-centos -t yas-zabbix-agent:v2.5 .

# 重启容器
docker stop yas-zabbix-agent; docker rm yas-zabbix-agent
docker run -d --name yas-zabbix-agent --network zabbix-net `
    -v yas_agent_libs:/opt/yashandb/yashandb_yasdb_home:ro `
    -e YASDB_HOST=yas_oracle -e YASDB_PORT=1688 `
    -e YASDB_USER=sys -e YASDB_PASSWORD=Cod-2022 `
    -e ZBX_SERVER_HOST=zabbix-server `
    yas-zabbix-agent:v2.5
```

---

## 10. 压测验证与故障排查

### 10.1 压测脚本

`analyze/yasdb_stress_10m.py` — 2 并发写 YashanDB，持续 10 分钟，验证监控数据：

```bash
python c:/Users/DELL/WorkBuddy/Claw/analyze/yasdb_stress_10m.py
```

**预期结果**：
- 写入速率：~15,000 行/秒
- 10 分钟写入：~9,000,000 条
- Dashboard QPS 曲线显示峰值
- 压测后会话数回落

### 10.2 故障排查速查

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| `YAS-20001 load yacli library error` | `LD_LIBRARY_PATH` 未设置 | 使用 `wrapper.sh` 重新注入 |
| `yashandb.db.status` → 0 | YashanDB 连接失败 | 检查容器网络和密码 |
| `ZBX_NOTSUPPORTED` | 指标 key 不存在 | 检查 `yashandb_monitor.py` dispatch 表 |
| Dashboard Widget 报错 | 引用的 item key 不存在 | 使用 `yashandb.db.sql.executions_per_sec` 等正确 key |
| Graph "Invalid parameter" | `time_period` 显式设置 | 不设置 time_period 字段 |
| API 401 Unauthorized | Zabbix 7.x 未使用 Bearer Token | 打补丁 `zabbix_api.py` |
| `apiinfo.version` 失败 | Bearer Token 不支持该端点 | `api_version()` 方法加 try/except |

### 10.3 常用运维命令

```powershell
# 停止所有容器
docker stop yas-zabbix-agent zabbix-web zabbix-server yas_oracle

# 启动所有容器（已有数据）
docker start yas_oracle
Start-Sleep 60
docker start zabbix-server
docker start zabbix-web
docker start yas-zabbix-agent

# 清理调试容器
docker rm -f yas-debug yas-debug2 yas-zabbix-agent-old yas-zabbix-agent-test

# 进入 Agent 容器调试
docker exec -it yas-zabbix-agent bash

# 查看实时日志
docker logs -f yas-zabbix-agent
docker logs -f zabbix-web --tail 50
```

---

## 11. 版本历史

| 版本 | 日期 | 重大变更 |
|------|------|---------|
| v3.0 | 2026-04-13 | Dashboard v6（time_period 继承机制，Bearer Token 认证修复）；133 指标 |
| v2.5 | 2026-04-13 | yas-zabbix-agent Docker 镜像 v2.5；wrapper.sh LD_LIBRARY_PATH 注入 |
| v2.4 | 2026-04-12 | Zabbix 升级到 7.4.9；db.uptime Python datetime 转换 |
| v2.3 | 2026-04-10 | Nagios check_oracle_health 适配指标；125 指标 |
| v2.2 | 2026-04-09 | New Relic Oracle 适配；参数化等待事件 |
| v2.1 | 2026-04-08 | 长事务/HA 指标 |
| v2.0 | 2026-04-06 | 初次发布；Docker 容器化方案 |

---

## 附录

### A. 参考链接

| 资源 | 地址 |
|------|------|
| YashanDB 文档 | https://doc.yashandb.com/ |
| Zabbix 下载 | https://www.zabbix.com/download |
| yaspy 驱动 | https://github.com/yashan-technologies/yashandb-python |
| Datadog Oracle 监控 | https://github.com/DataDog/integrations-core/blob/master/oracle/ |
| New Relic nri-oracledb | https://github.com/newrelic/nri-oracledb |
| ConSol check_oracle_health | https://github.com/lausser/check_oracle_health |
| WorkBuddy 文档 | https://www.codebuddy.cn/docs/workbuddy/Overview |

### B. Zabbix API 端点速查

| 端点 | 用途 |
|------|------|
| `dashboard.create` | 创建 Dashboard |
| `dashboard.get` | 查询 Dashboard |
| `dashboard.update` | 更新 Dashboard |
| `widget.create` | 创建 Widget |
| `widget.update` | 更新 Widget |
| `item.get` | 查询监控项 |
| `host.get` | 查询主机 |
| `apiinfo.version` | 获取 API 版本（**不支持 Bearer Token**，必须无 auth） |

### C. 关键 Zabbix Graph Widget 字段速查

```
布局字段（position）:
  - rf_rate (Integer): 刷新率（秒），有效值: 10/30/60/120/600/1800/3600
  - source (Integer): 数据源，0=Auto, 1=History, 2=Trends
  - show_legend (Integer): 1=显示图例
  - left (Integer): 左坐标 px
  - top (Integer): 上坐标 px
  - width (Integer): 宽度 px
  - height (Integer): 高度 px

数据系列字段（ds，flat 格式）:
  - ds.N.itemids.0 (String): itemid（ITEM 类型）
  - ds.N.color.0 (String): 颜色（6 位 hex，不带 #）
  - ds.N.type (Integer): 绘图类型，0=Line, 1=Points, 2=Staircase, 3=Bar
  - ds.N.stacked (Integer): 堆叠模式
  - ds.N.transparency (Integer): 透明度，0-10
  - ds.N.dataset_type (Integer): 数据集类型，0=SINGLE_ITEM
  - ds.N.hosts.0 (String): 主机名（空=继承）
  - ds.N.items.0 (String): item key（空=用 itemids）

⚠️ 不要设置 time_period 字段！
```

---

## 12. Rocky Linux 10 完整部署指南

> **适配版本**：Rocky Linux 10 x86_64 + Zabbix Agent 7.4（RPM） + Zabbix Server 7.0/7.4
> **核心差异**：与 Docker 方案相比，Agent 以 systemd 服务运行，YashanDB C 库直接存放于本地文件系统，通过 `/etc/sysconfig/zabbix-agent` 管理环境变量。

### 12.1 架构对比

| 项目 | Rocky Linux 10 原生 | Docker CentOS 容器 |
|------|---------------------|-------------------|
| Zabbix Agent | 系统包（rpm）+ systemd | 容器内进程 |
| YashanDB C 库 | 本地文件系统 `/opt/yashandb/...` | Docker 卷挂载 |
| 环境变量持久化 | `/etc/sysconfig/zabbix-agent` | `docker run -e` |
| 服务管理 | `systemctl` | `docker` 命令 |
| 日志查看 | `journalctl -u zabbix-agent` | `docker logs` |

### 12.2 前置条件

- Rocky Linux 10 x86_64，root 或 sudo 权限
- 能访问 YashanDB（端口 1688）和 Zabbix Server（端口 10051）
- YashanDB C 驱动库（glibc 版，x86_64）

### 12.3 一键部署脚本

在 Rocky Linux 10 机器上执行（关键参数可自定义）：

```bash
# SSH 登录 Rocky Linux 10
sudo su -

# 设置关键参数（按实际修改）
export YASDB_HOST=192.168.1.100    # YashanDB 地址
export YASDB_PORT=1688              # YashanDB 端口
export YASDB_USER=sys              # 连接用户
export YASDB_PASSWORD=Cod-2022     # 连接密码
export ZBX_SERVER_HOST=192.168.1.50 # Zabbix Server 地址
export ZBX_HOSTNAME=rocky10-yas-agent

# 一键部署
cd /opt/deploy/rocky10
chmod +x deploy-rocky.sh
./deploy-rocky.sh
```

### 12.4 分步部署详解

#### 步骤 1：安装系统依赖

```bash
sudo dnf install -y \
    python3 python3-pip python3-devel \
    gcc gcc-c++ make git \
    libffi-devel openssl-devel \
    curl wget net-tools
```

#### 步骤 2：安装 yaspy Python 驱动

```bash
sudo pip3 install --break-system-packages \
    git+https://github.com/yashan-technologies/yashandb-python.git@main

# 验证
python3 -c "import yaspy; print('yaspy OK')"
```

#### 步骤 3：获取 YashanDB C 驱动库

**方式 A（推荐）：从 Docker 复制**

```bash
# 在 YashanDB Docker 所在机器执行
docker cp yas_oracle:/opt/yashandb/yashandb_yasdb_home/lib/ ./yashandb_lib/

# 传输到 Rocky Linux 10
scp -r ./yashandb_lib/ rocky10:/tmp/

# Rocky Linux 10 上安装
sudo mkdir -p /opt/yashandb/yashandb_yasdb_home/lib
sudo cp -r /tmp/yashandb_lib/* /opt/yashandb/yashandb_yasdb_home/lib/

# 验证
ls /opt/yashandb/yashandb_yasdb_home/lib/ | grep yascli
```

**方式 B：YashanDB 原生安装（与 Agent 同机）**

```bash
sudo rpm -ivh YashanDB-xxx.el8.x86_64.rpm
# 库文件自动安装到 /opt/yashandb/yashandb_yasdb_home/lib/
```

#### 步骤 4：安装 Zabbix Agent 7.4（RPM）

```bash
sudo dnf install -y \
    https://repo.zabbix.com/zabbix/7.4/rhel/10/x86_64/ \
    zabbix-agent-7.4.9-release1.el10.x86_64.rpm
```

> Rocky Linux 10 → RHEL 10，Zabbix 官方仓库路径为 `rhel/10/x86_64/`。

#### 步骤 5：部署采集脚本

```bash
sudo mkdir -p /opt/yas_zabbix/scripts
sudo mkdir -p /etc/zabbix/zabbix_agentd.d

# 复制脚本（从部署包）
sudo cp rocky10/scripts/yashandb_monitor.py /opt/yas_zabbix/scripts/
sudo cp rocky10/wrapper.sh /opt/yas_zabbix/scripts/
sudo cp rocky10/yashandb_userparameter.conf \
    /etc/zabbix/zabbix_agentd.d/yashandb.conf

sudo chmod +x /opt/yas_zabbix/scripts/yashandb_monitor.py
sudo chmod +x /opt/yas_zabbix/scripts/wrapper.sh
```

#### 步骤 6：生成配置文件

```bash
sudo tee /opt/yas_zabbix/scripts/yashandb.ini > /dev/null << 'EOF'
[yashandb]
host = 192.168.1.100
port = 1688
user = sys
password = Cod-2022
EOF
sudo chmod 600 /opt/yas_zabbix/scripts/yashandb.ini
```

#### 步骤 7：配置 systemd 环境变量

```bash
sudo tee /etc/sysconfig/zabbix-agent > /dev/null << 'EOF'
YASDB_HOST=192.168.1.100
YASDB_PORT=1688
YASDB_USER=sys
YASDB_PASSWORD=Cod-2022
YASDB_LIB_PATH=/opt/yashandb/yashandb_yasdb_home/lib
LD_LIBRARY_PATH=/opt/yashandb/yashandb_yasdb_home/lib:$LD_LIBRARY_PATH
EOF
```

#### 步骤 8：配置 Zabbix Agent

```bash
sudo vi /etc/zabbix/zabbix_agentd.conf
```

修改以下行：
```ini
Server=192.168.1.50
ServerActive=192.168.1.50
Hostname=rocky10-yas-agent
Include=/etc/zabbix/zabbix_agentd.d/*.conf
UnsafeUserParameters=1
```

#### 步骤 9：启动服务

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now zabbix-agent

# 验证
sudo systemctl status zabbix-agent
sudo ss -tlnp | grep 10050
```

### 12.5 本地验证

```bash
# 测试 wrapper（自动注入 LD_LIBRARY_PATH）
/bin/bash /opt/yas_zabbix/scripts/wrapper.sh \
    --config /opt/yas_zabbix/scripts/yashandb.ini \
    --metric db.status
# 期望输出: 1

# 测试版本
/bin/bash /opt/yas_zabbix/scripts/wrapper.sh \
    --config /opt/yas_zabbix/scripts/yashandb.ini \
    --metric db.version
# 期望输出: Enterprise Edition Release 23.4.7.100 x86_64

# Zabbix Server 端验证（如果有 zabbix_get）
zabbix_get -s 192.168.1.200 -p 10050 -k "yashandb.db.status"
```

### 12.6 Zabbix Web UI 配置（Rocky Linux 10 Agent）

1. **Configuration → Hosts → Create host**
   - Host name: `rocky10-yas-agent`（必须与 `zabbix_agentd.conf` 中的 `Hostname` 完全一致）
   - Groups: `Linux servers` 或新建 `YashanDB`
   - Interfaces → Agent: `192.168.1.200`，端口 `10050`
2. **Templates**：链接 `YashanDB by Zabbix Agent`
3. 等待 1-2 分钟，自动发现 LLD（表空间、等待事件）

### 12.7 修改配置后生效

```bash
# 修改连接参数（yashandb.ini）
sudo vi /opt/yas_zabbix/scripts/yashandb.ini
sudo systemctl restart zabbix-agent

# 修改环境变量（YashanDB 地址/密码）
sudo vi /etc/sysconfig/zabbix-agent
sudo systemctl restart zabbix-agent

# 修改 Zabbix Agent 网络配置
sudo vi /etc/zabbix/zabbix_agentd.conf
sudo systemctl restart zabbix-agent
```

### 12.8 日志位置

| 日志 | 路径 | 查看命令 |
|------|------|---------|
| systemd 启动日志 | journal | `journalctl -u zabbix-agent -f` |
| Agent 运行日志 | `/var/log/zabbix/zabbix_agentd.log` | `tail -f /var/log/zabbix/zabbix_agentd.log` |
| systemd 全局日志 | journal | `journalctl -xe --no-pager` |

### 12.9 故障排查

**`libyascli.so: No such file or directory`**
```bash
# 1. 确认文件存在
ls -la /opt/yashandb/yashandb_yasdb_home/lib/libyascli.so

# 2. 确认 systemd 环境变量已加载
sudo systemctl show-environment | grep -i yas

# 3. 测试 wrapper
sudo /bin/bash /opt/yas_zabbix/scripts/wrapper.sh \
    --config /opt/yas_zabbix/scripts/yashandb.ini \
    --metric db.status
```

**`invalid username/password`**
```bash
sudo vi /opt/yas_zabbix/scripts/yashandb.ini
sudo systemctl restart zabbix-agent
```

**`Not Found: host [rocky10-yas-agent]`**
确保 Zabbix Web 中创建主机时填的 hostname 与 `zabbix_agentd.conf` 中的 `Hostname=` 完全一致。

**防火墙开放端口**
```bash
sudo firewall-cmd --permanent --add-port=10050/tcp
sudo firewall-cmd --reload
```

---

## 13. 全部监控指标清单

> **版本**：v2.5，共 **133 个**可用指标 + 52 个 N/A 指标
> **数据来源**：YashanDB 23.4 LTS 动态性能视图（V$SESSION、V$SYSSTAT、V$FILESTAT 等）
> **适用版本**：YashanDB 23.4.7.100 及以上

### 13.1 指标速查表（按类别）

#### 类别 A：实例状态（4 个）

| 指标 Key | 描述 | 用途 | 数据来源 |
|----------|------|------|---------|
| `yashandb.db.status` | 数据库实例状态（1=正常, 0=异常） | 数据库可用性监控，Agent 连接测试 | `SELECT 1 FROM DUAL` |
| `yashandb.db.version` | 数据库版本号 | 版本识别，兼容性确认 | `V$INSTANCE.VERSION` |
| `yashandb.db.uptime` | 数据库启动时长（秒） |  uptime 监控，判断是否频繁重启 | `V$INSTANCE.STARTUP_TIME` datetime 差值 |
| `yashandb.db.mode` | 数据库运行模式（PRIMARY/STANDBY） | 高可用架构确认 | `V$DATABASE.DATABASE_ROLE` |

#### 类别 B：会话与连接（12 个）

| 指标 Key | 描述 | 用途 | 数据来源 |
|----------|------|------|---------|
| `yashandb.active_sessions` | 活跃会话总数（STATUS='ACTIVE'） | 实时负载监控，最核心性能指标之一 | `V$SESSION WHERE STATUS='ACTIVE'` |
| `yashandb.total_sessions` | 总会话数 | 会话容量监控 | `V$SESSION` 全表计数 |
| `yashandb.sessions.inactive` | 非活跃会话数量（STATUS='INACTIVE'） | 识别空闲但未断开的长连接 | `V$SESSION WHERE STATUS='INACTIVE'` |
| `yashandb.sessions.waiting` | 当前等待中的会话数 | 判断会话是否在等待资源 | `V$SESSION WHERE WAIT_CLASS IS NOT NULL` |
| `yashandb.sessions.background` | 后台会话总数（TYPE='BACKGROUND'） | 后台进程健康监控 | `V$SESSION WHERE TYPE='BACKGROUND'` |
| `yashandb.active_background` | 活跃后台会话数 | 识别活跃的后台进程（PMON/SMON 等） | `V$SESSION WHERE TYPE='BACKGROUND' AND STATUS='ACTIVE'` |
| `yashandb.session_count` | 会话总数 | 连接容量基线 | `V$SESSION` |
| `yashandb.user_sessions` | 用户会话数（TYPE='USER'） | 排除后台进程后的真实用户连接数 | `V$SESSION WHERE TYPE='USER'` |
| `yashandb.session_limit_usage` | 会话限制使用率（%） | 连接数逼近上限时告警 | `V$SESSION / V$PARAMETER.sessions × 100` |
| `yashandb.process_limit` | 进程限制使用率（%） | 进程数逼近上限时告警 | `V$PROCESS / V$PARAMETER.processes × 100` |
| `yashandb.db.current_logons` | 当前登录会话数 | 实时登录数（等同于总会话数） | `V$SESSION` |
| `yashandb.sessions.active_detail` | 活跃会话详细信息（JSON文本） | 告警上下文：SID/用户名/等待事件/程序 | `V$SESSION WHERE STATUS='ACTIVE'` LISTAGG |

#### 类别 C：SQL 性能（12 个）

| 指标 Key | 描述 | 用途 | 数据来源 |
|----------|------|------|---------|
| `yashandb.db.sql.executions_per_sec` | 每秒 SQL 执行次数（累计值） | QPS 基线，配合 Zabbix rate 函数计算 delta | `V$SYSSTAT NAME='EXECUTE COUNT'` |
| `yashandb.db.qps` | 每秒查询数（累计值，同 executions_per_sec） | 商业监控产品兼容性 | `V$SYSSTAT NAME='EXECUTE COUNT'` |
| `yashandb.db.tps` | 每秒事务数（累计值） | TPS 基线，配合 Zabbix rate 函数 | `V$SYSSTAT NAME='COMMITS'` |
| `yashandb.db.sql.avg_elapsed_ms` | SQL 平均执行时长（ms） | 慢 SQL 识别，平均响应时间 | `V$SQL AVG(ELAPSED_TIME)/1000` |
| `yashandb.db.sql.slow_count` | 慢 SQL 数量（>1s） | 慢查询告警阈值 | `V$SQL WHERE ELAPSED_TIME > 1000000` |
| `yashandb.db.sql.parse_count` | SQL 解析次数（硬解析） | 硬解析过多消耗 CPU，共享池碎片化 | `V$SYSSTAT NAME='parse count (hard)'` |
| `yashandb.hard_parses` | 硬解析次数（同 parse_count） | 同上，Datadog 兼容别名 | `V$SYSSTAT NAME='PARSE COUNT (HARD)'` |
| `yashandb.soft_parse_ratio` | 软解析比率（%） | 共享池效率，理想值 > 95% | `V$SYSSTAT SESSION CURSOR CACHE HITS` |
| `yashandb.sql.p95_elapsed_ms` | 慢查询 P95 延迟（ms） | 分位数性能，SLA 达标评估 | `V$SQL PERCENTILE_CONT(0.95)` |
| `yashandb.sql.p99_elapsed_ms` | 慢查询 P99 延迟（ms） | 尾部延迟，极端慢查询识别 | `V$SQL PERCENTILE_CONT(0.99)` |
| `yashandb.memory_sorts_ratio` | 内存排序比率（%） | 排序操作是否在内存中完成，避免磁盘排序 | `V$SYSSTAT SORTS(MEMORY) / SORTS(DISK)` |
| `yashandb.db.sql.executions_per_sec` | 每秒 SQL 执行次数 | QPS 基线 | `V$SYSSTAT NAME='EXECUTE COUNT'` |

#### 类别 D：内存与 Buffer Pool（16 个）

| 指标 Key | 描述 | 用途 | 数据来源 |
|----------|------|------|---------|
| `yashandb.buffer_cachehit_ratio` | 缓冲区缓存命中率（%） | 内存效率，理想值 > 95%，< 90% 需调优 | `V$BUFFER_POOL_STATISTICS` |
| `yashandb.db.memory.buffer_pool_size` | Buffer Pool 总大小（字节） | 内存容量规划 | `V$BUFFER_POOL_STATISTICS` |
| `yashandb.db.memory.buffer_pool_used` | Buffer Pool 已使用大小（字节） | 内存使用量监控 | `V$BUFFER_POOL_STATISTICS` |
| `yashandb.db.memory.buffer_pool_hit` | Buffer Pool 命中率（%，同 buffer_cachehit_ratio） | 同上，备用名 | `V$BUFFER_POOL_STATISTICS` |
| `yashandb.db.memory.vm_pool_size` | VM Pool 总大小（字节） | 虚拟内存池大小 | `V$VMSTAT.TOTAL_SIZE` |
| `yashandb.db.memory.vm_pool_used` | VM Pool 已使用大小（字节） | 虚拟内存使用量 | `V$VMSTAT.USED_SIZE` |
| `yashandb.shared_pool_free` | 共享池空闲内存百分比（%） | 共享池内存压力监控，< 20% 可能告警 | `V$SGASTAT SHARE POOL free memory` |
| `yashandb.shared_memory_size` | 共享内存总大小（字节） | SGA 内存总容量 | `V$SGA SUM(SIZE)` |
| `yashandb.process.pga_allocated_memory` | 进程 PGA 分配内存（字节） | 进程内存压力（SGA 估算替代 PGA） | `V$SGASTAT SUM(BYTES)` |
| `yashandb.process.pga_used_memory` | 进程 PGA 已用内存（字节） | 内存使用估算 | `V$SGASTAT` - `SHARE POOL free` |
| `yashandb.process.pga_free_memory` | 进程 PGA 可释放内存（字节） | 内存可释放空间 | `V$SGASTAT SHARE POOL free memory` |
| `yashandb.process.pga_max_memory` | 进程 PGA 最大内存（字节） | PGA 峰值内存使用 | `V$SGASTAT SUM(BYTES)` |
| `yashandb.cache_blocks_lost` | 丢失的缓存块数 | 缓存完整性检查（非 0 需关注） | `V$SYSSTAT NAME='LOST WRITE DETECTED'` |
| `yashandb.physical_memory_gb` | 物理内存大小（GB） | 宿主机资源基线 | `V$OSSTAT PHYSICAL_MEMORY_BYTES` |
| `yashandb.memory_used` | 内存已使用（字节） | 内存使用量 | `V$SYSSTAT` 估算 |
| `yashandb.memory_size` | 内存总大小（字节） | 内存容量 | `V$SYSSTAT` 估算 |

#### 类别 E：表空间（LLD + 静态，15+ 个）

| 指标 Key | 描述 | 用途 | 数据来源 |
|----------|------|------|---------|
| `yashandb.tablespace.discovery` | 表空间 LLD 自动发现（JSON） | Zabbix LLD 宏 `{#TABLESPACE}`，自动发现所有表空间 | `DBA_TABLESPACES` |
| `yashandb.tablespace.pct_used[{#TS}]` | 指定表空间使用率（%） | 容量管理，> 85% 告警 | `DBA_DATA_FILES + DBA_FREE_SPACE` |
| `yashandb.tablespace.total[{#TS}]` | 指定表空间总大小（字节） | 表空间容量监控 | `DBA_DATA_FILES` |
| `yashandb.tablespace.used[{#TS}]` | 指定表空间已使用（字节） | 已用空间监控 | `DBA_DATA_FILES - DBA_FREE_SPACE` |
| `yashandb.tablespace.free[{#TS}]` | 指定表空间剩余空间（字节） | 可用空间监控 | `DBA_FREE_SPACE` |
| `yashandb.tablespace.in_use` | 表空间使用率（%，全库汇总） | 整体存储健康度 | `DBA_DATA_FILES + DBA_FREE_SPACE` |
| `yashandb.tablespace.size` | 表空间当前总大小（字节） | 全库存储总量 | `DBA_DATA_FILES SUM(BYTES)` |
| `yashandb.tablespace.maxsize` | 表空间最大容量（字节） | 表空间上限监控（MAXBYTES） | `DBA_DATA_FILES SUM(MAXBYTES)` |
| `yashandb.tablespace.used` | 表空间已使用字节数（全库汇总） | 全库已用存储 | `DBA_DATA_FILES - DBA_FREE_SPACE` |
| `yashandb.tablespace.offline` | 离线表空间数量 | 数据完整性告警 | `DBA_TABLESPACES WHERE STATUS='OFFLINE'` |
| `yashandb.tablespace.offline_count` | 离线表空间数量（同 offline） | 同上，备用名 | `DBA_TABLESPACES WHERE STATUS='OFFLINE'` |
| `yashandb.tablespace.by_type[PERMANENT]` | 永久表空间总大小（字节） | 按类型分类存储分析 | `DBA_TABLESPACES + DBA_DATA_FILES` |
| `yashandb.tablespace.by_type[TEMPORARY]` | 临时表空间总大小（字节） | 临时存储分析 | `DBA_TABLESPACES + DBA_DATA_FILES` |
| `yashandb.tablespace.by_type[UNDO]` | Undo 表空间总大小（字节） | Undo 存储分析 | `DBA_TABLESPACES + DBA_DATA_FILES` |
| `yashandb.tablespace.temp_usage_pct` | 临时表空间使用率（%） | 临时段膨胀告警 | `DBA_TEMP_FREE_SPACE` |
| `yashandb.tablespace.undo_usage_pct` | Undo 表空间使用率（%） | Undo 保留空间告警 | `DBA_DATA_FILES + DBA_FREE_SPACE (UNDO)` |
| `yashandb.db.tablespace_remaining_days` | 表空间剩余天数（天） | 容量规划预测，> 95% 使用率预测耗尽时间 | `DBA_DATA_FILES` 趋势分析 |

#### 类别 F：等待事件（10+ 个）

| 指标 Key | 描述 | 用途 | 数据来源 |
|----------|------|------|---------|
| `yashandb.db.wait.top_event` | 当前 TOP 等待事件名称 | 定位最大性能瓶颈（按 TIME_WAITED 排序） | `V$SYSTEM_EVENT` |
| `yashandb.db.waits_total` | 所有等待事件 TOTAL_WAITS 之和 | 整体等待活动量 | `V$SYSTEM_EVENT` |
| `yashandb.db.wait_time_total` | 所有等待事件 TIME_WAITED 之和（ms） | 整体等待时间，诊断慢查询根因 | `V$SYSTEM_EVENT` |
| `yashandb.db.wait_event_waits[{#WAIT_EVENT}]` | 指定等待事件的 TOTAL_WAITS | 特定等待事件监控（参数化 LLD） | `V$SYSTEM_EVENT WHERE EVENT='{...}'` |
| `yashandb.db.wait_event_time[{#WAIT_EVENT}]` | 指定等待事件的 TIME_WAITED（ms） | 特定等待事件延迟分析 | `V$SYSTEM_EVENT WHERE EVENT='{...}'` |
| `yashandb.wait_class.discovery` | 等待类 LLD 自动发现（JSON） | Zabbix LLD 宏 `{#WAIT_CLASS}`，按类分组等待 | `V$SYSTEM_WAIT_CLASS` |
| `yashandb.db.wait_class.count[{#WAIT_CLASS}]` | 指定等待类的总等待次数 | 按等待类（Application/System/Idle）聚合 | `V$SYSTEM_WAIT_CLASS` |
| `yashandb.db.wait_class.time[{#WAIT_CLASS}]` | 指定等待类的总等待时间（厘秒） | 按等待类聚合等待时间 | `V$SYSTEM_WAIT_CLASS` |
| `yashandb.avg_synchronous_single_block_read_latency` | 平均同步单块读延迟（ms） | I/O 子系统性能，> 10ms 需关注存储 | `V$SYSTEM_EVENT db file sequential read` |
| `yashandb.sga.buffer_busy_waits` | 缓冲区忙等待次数 | Buffer Pool 争用，hot block 问题 | `V$SYSTEM_EVENT buffer busy waits` |
| `yashandb.sga.free_buffer_waits` | 空闲缓冲区等待次数 | Buffer Pool 内存不足 | `V$SYSTEM_EVENT free buffer waits` |
| `yashandb.sga.log_buffer_space_waits` | 日志缓冲区空间等待次数 | Redo 写入瓶颈 | `V$SYSTEM_EVENT log buffer space` |

#### 类别 G：锁（6 个）

| 指标 Key | 描述 | 用途 | 数据来源 |
|----------|------|------|---------|
| `yashandb.db.lock.count` | 当前锁数量 | 锁争用基线 | `V$LOCK` |
| `yashandb.db.lock.blocking_sessions` | 阻塞中的会话数 | 阻塞锁告警，发现死锁前兆 | `V$SESSION WHERE BLOCKING_SESSION IS NOT NULL` |
| `yashandb.lock_count` | 当前锁数量（同 db.lock.count） | 备用名 | `V$LOCK` |
| `yashandb.blocking_sessions` | 阻塞中的会话数（同 db.lock.blocking_sessions） | 备用名 | `V$SESSION` |
| `yashandb.lock.enqueue_locks` | 当前持有 Enqueue 锁的数量 | 行级锁争用分析 | `V$LOCK WHERE LMODE > 0` DISTINCT SID |
| `yashandb.lock.enqueue_requests` | Enqueue 锁请求数量（REQUEST > 0） | 锁请求频率 | `V$LOCK WHERE REQUEST > 0` |

#### 类别 H：物理 I/O（8 个）

| 指标 Key | 描述 | 用途 | 数据来源 |
|----------|------|------|---------|
| `yashandb.physical_reads` | 每秒物理读取次数（累计值） | 磁盘 I/O 读负载，配合 rate 函数 | `V$SYSSTAT NAME='DISK READS'` |
| `yashandb.physical_writes` | 每秒物理写入次数（累计值） | 磁盘 I/O 写负载，配合 rate 函数 | `V$SYSSTAT NAME='DISK WRITES'` |
| `yashandb.logical_reads` | 每秒逻辑读取次数（累计值） | Buffer Pool 访问频率 | `V$SYSSTAT DB BLOCK GETS + CONSISTENT GETS` |
| `yashandb.disk.total_reads` | 所有数据文件物理读取总次数 | 文件级 I/O 统计 | `V$FILESTAT SUM(PHYRDS)` |
| `yashandb.disk.total_writes` | 所有数据文件物理写入总次数 | 文件级 I/O 写统计 | `V$FILESTAT SUM(PHYWRTS)` |
| `yashandb.disk.total_read_time` | 物理读取总时间（厘秒，原值×10=ms） | 读 I/O 延迟分析 | `V$FILESTAT SUM(READTIM)` |
| `yashandb.disk.total_write_time` | 物理写入总时间（厘秒，原值×10=ms） | 写 I/O 延迟分析 | `V$FILESTAT SUM(WRITETIM)` |
| `yashandb.db_block_changes` | 每秒数据库块变更数 | 数据修改热度 | `V$SYSSTAT NAME='BLOCK CHANGES'` |
| `yashandb.consistent_read_changes` | 每秒一致性读变更次数 | 读一致性负载 | `V$SYSSTAT NAME='CONSISTENT CHANGES'` |

#### 类别 I：Redo 日志（10 个）

| 指标 Key | 描述 | 用途 | 数据来源 |
|----------|------|------|---------|
| `yashandb.redo_generated` | 每秒生成 Redo 字节数（累计值） | 事务写入负载，配合 rate 函数 | `V$SYSSTAT NAME='REDO SIZE'` |
| `yashandb.redo_writes` | 每秒 Redo 写入次数（累计值） | Redo 写入频率 | `V$SYSSTAT NAME='REDO WRITES'` |
| `yashandb.redo_allocation_hit_ratio` | Redo 空间分配命中率（%） | Redo 日志空间争用，理想值接近 100% | `V$SYSSTAT REDO ENTRIES / REDO SPACE` |
| `yashandb.db.redo.flush_speed` | Redo 刷盘速度（字节/秒） | Redo 写入速率 | `V$REDOSTAT.FLUSH_SPEED` |
| `yashandb.db.redo.free_space` | Redo 空闲空间（字节） | Redo 容量监控 | `V$REDOSTAT.FREE_SPACE` |
| `yashandb.db.redo.checkpoint_lag` | 检查点落后量 | 检查点性能，滞后过多影响恢复时间 | `V$REDOSTAT.CHECKPOINT_LAG` |
| `yashandb.db.redo.log_switches` | 最近 24 小时 Redo 日志切换次数 | 日志切换频率，频繁切换可能需增加日志文件大小 | `V$ARCHIVED_LOG FIRST_TIME >= SYSDATE - 1` |
| `yashandb.redo.waits` | Redo 日志相关等待总次数 | Redo 写入瓶颈分析 | `V$SYSTEM_EVENT log file sync/sync/write` |
| `yashandb.redo.switch_checkpoint` | 检查点未完成导致的日志切换次数 | 检查点性能问题 | `V$SYSTEM_EVENT log file switch` |
| `yashandb.dbwr_checkpoints` | DBWR 检查点完成数（累计值） | 检查点执行频率 | `V$SYSSTAT NAME='CHECKPOINTS COMPLETED'` |

#### 类别 J：事务（3 个）

| 指标 Key | 描述 | 用途 | 数据来源 |
|----------|------|------|---------|
| `yashandb.user_commits` | 每秒用户提交次数（累计值） | TPS，配合 Zabbix rate 函数 | `V$SYSSTAT NAME='COMMITS'` |
| `yashandb.user_rollbacks` | 用户回滚次数（累计值） | 回滚活动，过多回滚可能意味着应用逻辑问题 | `V$SYSSTAT NAME='ROLLBACKS'` |
| `yashandb.db.transaction_count` | 当前活跃事务数 | 长事务监控 | `V$SESSION WHERE STATUS='ACTIVE'` |

#### 类别 K：SGA 缓冲区（6 个）

| 指标 Key | 描述 | 用途 | 数据来源 |
|----------|------|------|---------|
| `yashandb.sga.fixed_size` | SGA 固定部分大小（字节） | SGA 固定内存区域 | `V$SGASTAT NAME='fixed size'` |
| `yashandb.sga.redo_buffers` | Redo 缓冲区大小（字节） | Redo 缓冲区大小（应接近 LOG_BUFFER 参数） | `V$SGASTAT NAME='redo buffers'` |
| `yashandb.sga.buffer_busy_waits` | 缓冲区忙等待次数 | Buffer Pool 热块争用 | `V$SYSTEM_EVENT buffer busy waits` |
| `yashandb.sga.free_buffer_waits` | 空闲缓冲区等待次数 | Buffer Pool 可用内存不足 | `V$SYSTEM_EVENT free buffer waits` |
| `yashandb.sga.free_buffer_inspected` | 空闲缓冲区检查数量 | 寻找可用 buffer 的开销 | `V$SYSSTAT BUFFER BLOCKS INSPECTED` |
| `yashandb.sga.log_buffer_space_waits` | 日志缓冲区空间等待次数 | Redo 缓冲区争用 | `V$SYSTEM_EVENT log buffer space` |

#### 类别 L：Top SQL（6 个）

| 指标 Key | 描述 | 用途 | 数据来源 |
|----------|------|------|---------|
| `yashandb.sql.count` | 共享池中 SQL 语句总数 | SQL 缓存效率，共享池内存压力 | `V$SQLAREA COUNT(*)` |
| `yashandb.sql.top_buffer_gets` | 最高 BUFFER_GETS 的 SQL 获取次数 | 识别最耗内存的 SQL | `V$SQLAREA MAX(BUFFER_GETS)` |
| `yashandb.sql.top_disk_reads` | 最高 DISK_READS 的 SQL 读取次数 | 识别最耗 I/O 的 SQL | `V$SQLAREA MAX(DISK_READS)` |
| `yashandb.sql.top_buffer_gets_sql` | Top SQL（按 BUFFER_GETS）的 SQL_ID | SQL 分析，性能优化目标 | `V$SQLAREA ORDER BY BUFFER_GETS DESC` |
| `yashandb.sql.top_disk_reads_sql` | Top SQL（按 DISK_READS）的 SQL_ID | I/O 优化目标 SQL | `V$SQLAREA ORDER BY DISK_READS DESC` |
| `yashandb.sql.top_executions_sql` | Top SQL（按 EXECUTIONS）的 SQL_ID | 高频 SQL 分析 | `V$SQLAREA ORDER BY EXECUTIONS DESC` |

#### 类别 M：归档日志（4 个）

| 指标 Key | 描述 | 用途 | 数据来源 |
|----------|------|------|---------|
| `yashandb.archived_log.count` | 归档日志文件总数 | 归档容量监控 | `V$ARCHIVED_LOG COUNT(*)` |
| `yashandb.archived_log.count_today` | 当天归档日志文件数量 | 归档产生速率 | `V$ARCHIVED_LOG FIRST_TIME >= TRUNC(SYSDATE)` |
| `yashandb.archived_log.first_time` | 最早归档日志时间（文本） | 判断归档是否正常（时间不应过旧） | `V$ARCHIVED_LOG MIN(FIRST_TIME)` |
| `yashandb.archiver.failed` | 归档失败次数 | 归档进程故障告警 | `V$SYSTEM_EVENT archive%error` |

#### 类别 N：对象与统计（8 个）

| 指标 Key | 描述 | 用途 | 数据来源 |
|----------|------|------|---------|
| `yashandb.db.invalid_objects` | 无效数据库对象数量 | 数据库健康度，编译错误对象需重建 | `DBA_OBJECTS WHERE STATUS='INVALID'` |
| `yashandb.db.invalid_indexes` | 无效索引数量 | 索引失效影响查询性能 | `DBA_INDEXES WHERE STATUS='INVALID'` |
| `yashandb.db.stale_statistics` | 统计信息陈旧的表数量 | 统计信息过期导致执行计划不优 | `DBA_TAB_STATISTICS WHERE STALE_STATS='YES'` |
| `yashandb.segment.total_count` | 段（表/索引/LOB）总数 | 存储规模基线 | `DBA_SEGMENTS COUNT(*)` |
| `yashandb.segment.top_tablespace` | 占用空间最大的表空间名称 | 容量热点识别 | `DBA_SEGMENTS GROUP BY TABLESPACE_NAME` |
| `yashandb.datafile.non_autoextend_count` | 禁用了自动扩展的数据文件数量 | 容量风险，未自动扩展的文件可能爆满 | `DBA_DATA_FILES WHERE AUTOEXTENSIBLE='NO'` |
| `yashandb.datafile.offline_count` | 离线数据文件数量 | 数据完整性告警 | `V$DATAFILE WHERE STATUS='OFFLINE'` |
| `yashandb.db.datafile_max_usage_pct` | 数据文件最大容量使用率（%） | 最危险的数据文件（最满），容量告警 | `DBA_DATA_FILES MAX(BYTES/MAXBYTES)` |

#### 类别 O：资源限制（4 个）

| 指标 Key | 描述 | 用途 | 数据来源 |
|----------|------|------|---------|
| `yashandb.db.user_limit_pct` | 用户连接限制使用率（%） | 用户会话数逼近上限 | `V$SESSION / V$PARAMETER.sessions × 100` |
| `yashandb.db.process_limit_pct` | 进程限制使用率（%） | 进程数逼近上限 | `V$PROCESS / V$PARAMETER.processes × 100` |
| `yashandb.db.session_limit_pct` | 会话限制使用率（%） | 会话数逼近上限 | `V$SESSION / V$PARAMETER.sessions × 100` |
| `yashandb.resource_limit.usage_pct` | 资源限制使用率（%，sessions/processes 取较高者） | 综合资源限制告警 | `V$PARAMETER + V$PROCESS + V$SESSION` |
| `yashandb.db.session_limit_pct` | 会话限制使用率（%） | 同上 | `V$SESSION / V$PARAMETER.sessions` |

#### 类别 P：CPU 与系统资源（5 个）

| 指标 Key | 描述 | 用途 | 数据来源 |
|----------|------|------|---------|
| `yashandb.host_cpu_utilization` | 主机 CPU 利用率（%） | 宿主机 CPU 负载，> 80% 持续需关注 | `V$OSSTAT BUSY_TIME / (BUSY+IDLE)` |
| `yashandb.cpu_utilization` | CPU 利用率（同 host_cpu_utilization） | 备用名 | `V$OSSTAT` |
| `yashandb.num_cpus` | CPU 核心数 | 性能基线，并行度参考 | `V$OSSTAT NAME='NUM_CPUS'` |
| `yashandb.os_load` | 操作系统负载（1min avg） | 系统负载，CPU 排队长度 | `V$OSSTAT NAME='LOAD'` |
| `yashandb.db.open_cursors` | 游标总数（V$SQLAREA 替代 V$OPEN_CURSOR） | 游标泄漏检测 | `V$SQLAREA COUNT(*)` |

#### 类别 Q：网络与索引（5 个）

| 指标 Key | 描述 | 用途 | 数据来源 |
|----------|------|------|---------|
| `yashandb.network_traffic_volume` | 每秒网络流量（字节） | 网络带宽使用量 | `V$SYSSTAT BYTES SENT SQL*NET` |
| `yashandb.network_throughput` | 网络吞吐量（同 network_traffic_volume） | 备用名 | `V$SYSSTAT` |
| `yashandb.branch_node_splits` | 每秒分支节点分裂次数 | B-Tree 索引维护开销，频繁分裂影响插入性能 | `V$SYSSTAT NAME='INDEX BRANCH SPLIT'` |
| `yashandb.leaf_node_splits` | 每秒叶节点分裂次数 | 索引叶分裂频率，反映写入负载 | `V$SYSSTAT NAME='INDEX LEAF SPLIT'` |
| `yashandb.disk_sorts` | 每秒磁盘排序次数 | 磁盘排序过多影响性能，> 0 需优化 SQL | `V$SYSSTAT NAME='SORTS (DISK)'` |
| `yashandb.sorts_per_user_call` | 每次用户调用的排序次数 | 应用排序行为分析 | `V$SYSSTAT SORTS / USER CALLS` |

#### 类别 R：长事务与高可用（3 个）

| 指标 Key | 描述 | 用途 | 数据来源 |
|----------|------|------|---------|
| `yashandb.db.long_transactions` | 超过 3 分钟的活跃事务数 | 长事务告警，阻塞 VACUUM/检查点，影响备份 | `V$TRANSACTION JOIN V$SESSION WHERE 超过180秒` |
| `yashandb.db.ha.sync_delay` | 主备同步延迟（gap 数量） | HA 场景：主备数据一致性，0=无延迟/单机 | `V$ARCHIVE_GAP COUNT(*)` |
| `yashandb.gc_average_cr_get_time` | 全局缓存平均 CR 获取时间（ms） | RAC 场景：CR 块传输延迟；单机=0 | `V$SYSSTAT GC CR BLOCK RECEIVE TIME` |
| `yashandb.gc_average_current_get_time` | 全局缓存平均 current 块获取时间（ms） | RAC 场景：current 块传输延迟；单机=0 | `V$SYSSTAT GC CURRENT BLOCK RECEIVE TIME` |

#### 类别 S：用户与会话分布（LLD，6 个）

| 指标 Key | 描述 | 用途 | 数据来源 |
|----------|------|------|---------|
| `yashandb.session.user.discovery` | 用户会话分布 LLD 发现（JSON，宏 {#USERNAME}） | 按用户分组的会话数自动发现 | `V$SESSION DISTINCT USERNAME` |
| `yashandb.session.by_user[{#USERNAME}]` | 指定用户的会话数量 | 识别消耗连接最多的用户 | `V$SESSION WHERE USERNAME='{...}'` |
| `yashandb.session.program.discovery` | 程序会话分布 LLD 发现（JSON，宏 {#PROGRAM}） | 按程序分组的会话数自动发现 | `V$SESSION DISTINCT PROGRAM` |
| `yashandb.session.by_program[{#PROGRAM}]` | 指定程序的会话数量 | 识别消耗连接最多的客户端程序 | `V$SESSION WHERE PROGRAM='{...}'` |
| `yashandb.invalid_objects.by_type.discovery` | INVALID 对象类型 LLD 发现（JSON，宏 {#OBJTYPE}） | 按类型分组的无效对象自动发现 | `DBA_OBJECTS WHERE STATUS='INVALID'` |
| `yashandb.invalid_objects.by_type[{#OBJTYPE}]` | 指定类型的 INVALID 对象数量 | 定位具体类型的失效对象（如 PROCEDURE/UDF） | `DBA_OBJECTS WHERE STATUS='INVALID' AND OBJECT_TYPE='{...}'` |

#### 类别 T：安全与管理（2 个）

| 指标 Key | 描述 | 用途 | 数据来源 |
|----------|------|------|---------|
| `yashandb.user.expiring_soon_count` | 密码 7 天内过期的账户数量 | 安全告警，提前发现即将失效的应用账户 | `DBA_USERS WHERE EXPIRY_DATE <= SYSDATE+7` |
| `yashandb.db.statistics_level` | STATISTICS_LEVEL 参数值（文本） | 统计级别确认，非 TYPICAL 影响执行计划准确性 | `V$PARAMETER NAME='STATISTICS_LEVEL'` |
| `yashandb.db.dbms_stats_available` | DBMS_STATS 包是否可用（1=是，0=否） | 统计信息收集能力确认 | `USER_OBJECTS WHERE OBJECT_NAME='DBMS_STATS'` |

### 13.2 告警阈值建议

| 指标 | 告警阈值 | 严重程度 | 说明 |
|------|---------|---------|------|
| `db.status` | = 0 | **Critical** | 数据库不可用 |
| `buffer_cachehit_ratio` | < 90% | Warning | Buffer Pool 命中率过低 |
| `active_sessions` | > sessions × 80% | Warning | 会话数逼近上限 |
| `process_limit` | > 80% | Warning | 进程数逼近上限 |
| `tablespace.pct_used[{#TS}]` | > 85% | Warning | 表空间使用率过高 |
| `tablespace.pct_used[{#TS}]` | > 95% | Critical | 表空间即将爆满 |
| `long_transactions` | > 0 | Warning | 存在长事务 |
| `db.lock.blocking_sessions` | > 0 | Warning | 存在阻塞锁 |
| `archiver.failed` | > 0 | Critical | 归档失败 |
| `invalid_objects` | > 0 | Warning | 存在无效对象 |
| `redo.switch_checkpoint` | > 100 | Warning | 检查点频繁触发 |
| `soft_parse_ratio` | < 95% | Warning | 软解析率过低，共享池碎片化 |
| `host_cpu_utilization` | > 80% 持续 5min | Warning | CPU 负载过高 |
| `user.expiring_soon_count` | > 0 | Warning | 有账户即将过期 |
| `tablespace_remaining_days` | < 30 | Warning | 表空间容量预警 |
| `db.redo.log_switches` | > 100/天 | Warning | 日志切换频繁，需增大日志文件 |

---

## 14. 版本历史

| 版本 | 日期 | 重大变更 |
|------|------|---------|
| v3.3 | 2026-04-13 | 模板：移除 7 个 N/A 指标（`library_cache_hit_ratio`/`library_cache_reload_ratio`/`row_cache_hit_ratio`/`rollback.gets`/`rollback.waits`/`rollback.ratio_wait`/`db.wait_time_ratio`）；文档：同步删除第13.2章 N/A 指标说明，章节重新编号（13.2 告警阈值建议）；指标数从 133 降至 126 |
| v3.2 | 2026-04-13 | 第13.2章：完善 N/A 指标说明，新增"脚本返回值/Zabbix 显示状态/替代指标"三列；模板：PGA 4个指标描述修正（实际来自 V$SGASTAT 而非 V$PROCESS）、`active_background` 描述修正（V$SESSION 无 STATUS 列）、N/A 7个指标描述加 ⚠️ 标记和 ZBX_NOTSUPPORTED 说明、`wait_time_ratio` 补入 N/A 清单；修复 UUID 冲突（`top_buffer_gets`/`top_disk_reads`/`sql.count` 均使用唯一 UUID） |
| v3.1 | 2026-04-13 | 新增 Rocky Linux 10 完整部署指南（第12章）；新增全部 133 个监控指标完整清单（第13章），含告警阈值建议 |
| v3.0 | 2026-04-13 | Dashboard v6（time_period 继承机制，Bearer Token 认证修复）；133 指标 |
| v2.5 | 2026-04-13 | yas-zabbix-agent Docker 镜像 v2.5；wrapper.sh LD_LIBRARY_PATH 注入 |
| v2.4 | 2026-04-12 | Zabbix 升级到 7.4.9；db.uptime Python datetime 转换 |
| v2.3 | 2026-04-10 | Nagios check_oracle_health 适配指标；125 指标 |
| v2.2 | 2026-04-09 | New Relic Oracle 适配；参数化等待事件 |
| v2.1 | 2026-04-08 | 长事务/HA 指标 |
| v2.0 | 2026-04-06 | 初次发布；Docker 容器化方案 |


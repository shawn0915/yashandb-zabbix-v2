# Zabbix Server + Web Docker 启动步骤

> 环境：Windows 宿主机 + WSL 内 MySQL 8.4（端口 3308）
> 版本：Zabbix Server/Web 7.4.9 (Alpine) + MySQL 8.4 + YashanDB Agent v2.5 (CentOS)
> 更新：2026-04-13（yas-zabbix-agent 升级至 v2.5，含 v2.5 全量指标）

---

## 架构说明

```
宿主机 Windows
  ├── MySQL 8.4 (WSL: 172.30.112.1:3308, database=zabbix)
  └── Docker Desktop
        ├── zabbix-server (Alpine, zabbix-net)    → 连接宿主机 MySQL
        ├── zabbix-web (Alpine, zabbix-net)        → 连接 zabbix-server + 宿主机 MySQL
        ├── yas_oracle (YashanDB 23.4.7.100)       → 被监控数据库
        └── yas-zabbix-agent (CentOS, zabbix-net)  → 采集 YashanDB 指标 → 上报 zabbix-server
```

> **网络说明**：zabbix-server、zabbix-web、yas-zabbix-agent 均在 `zabbix-net` 网络；
> yas_oracle 也挂在 zabbix-net（启动时加了 `--network zabbix-net`）

---

## 前提条件

**MySQL 数据库已就绪**（WSL 内）：
- Host: `172.30.112.1`
- Port: `3308`
- Database: `zabbix`
- User: `zabbix`
- Password: `Zabbix2026`

```sql
-- 在 WSL MySQL 中执行（只需一次）
CREATE DATABASE IF NOT EXISTS zabbix CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
CREATE USER IF NOT EXISTS 'zabbix'@'%' IDENTIFIED BY 'Zabbix2026';
GRANT ALL PRIVILEGES ON zabbix.* TO 'zabbix'@'%';
FLUSH PRIVILEGES;
```

**Docker 网络已创建**：
```powershell
docker network create zabbix-net
```

**YashanDB 驱动卷已就绪**（`yas_agent_libs`，从 yas_oracle 容器提取）：
```powershell
docker volume ls | findstr yas_agent_libs
# 应显示: local   yas_agent_libs
```

---

## 启动步骤

### 1. 清理旧容器（如有）

```powershell
docker stop zabbix-server zabbix-web yas-zabbix-agent 2>$null
docker rm   zabbix-server zabbix-web yas-zabbix-agent 2>$null
```

### 2. 启动 Zabbix Server

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

### 3. 启动 Zabbix Web

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

### 4. 启动 yas-zabbix-agent（YashanDB 监控 Agent v2.5）

> 前提：`yas_oracle` 容器已在 `zabbix-net` 网络中运行（YashanDB 23.4.7.100）
> 镜像：`yas-zabbix-agent:v2.5`（CentOS Stream 9 + Zabbix Agent 6.0.45 + Python 3.9 + yaspy 1.2.0）
> 密码：从 `yas_oracle` 容器环境变量 `SYS_PASSWD` 获取（当前为 `Cod-2022`）

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

**构建镜像**（如尚未构建，在 `analyze/` 目录下执行）：
```powershell
cd C:\Users\DELL\WorkBuddy\Claw\analyze
docker build --no-cache -f Dockerfile.yas-zabbix-agent-centos -t yas-zabbix-agent:v2.5 .
```

### 5. 等待初始化完成

```powershell
# 等待约 30 秒
Start-Sleep -Seconds 30

# 验证状态
docker ps --format "{{.Names}}: {{.Status}}" | findstr -i "zabbix\|yas"
```

---

## 验证

```powershell
# 检查容器状态
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | findstr -i "zabbix\|yas"

# Agent 日志确认
docker logs yas-zabbix-agent

# 从 Zabbix Server 拉取 YashanDB 指标（关键验证）
docker exec zabbix-server zabbix_get -s yas-zabbix-agent -p 10050 -k "agent.ping"
docker exec zabbix-server zabbix_get -s yas-zabbix-agent -p 10050 -k "yashandb.db.status"
docker exec zabbix-server zabbix_get -s yas-zabbix-agent -p 10050 -k "yashandb.db.version"
docker exec zabbix-server zabbix_get -s yas-zabbix-agent -p 10050 -k "yashandb.sessions.active"
docker exec zabbix-server zabbix_get -s yas-zabbix-agent -p 10050 -k "yashandb.tablespace.discovery"
```

预期输出：
```
agent.ping    → 1
db.status     → 1
db.version    → Enterprise Edition Release 23.4.7.100 x86_64
sessions.active → 26（会变动）
tablespace.discovery → {"data": [{"{#TS}": "SWAP"}, ...]}
```

**Web UI**: http://localhost:8080  
**默认账号**: Admin / zabbix

---

## Zabbix Web UI 接入 YashanDB 步骤

### 1. 导入模板

1. 登录 http://localhost:8080（Admin/zabbix）
2. 菜单：**配置 → 模板 → 导入**
3. 选择文件：`C:\Users\DELL\WorkBuddy\Claw\yas_zabbix\template\yashandb_zabbix_template_7.0.xml`
4. 全选导入选项，点击导入

### 2. 创建主机

1. 菜单：**配置 → 主机 → 创建主机**
2. 主机名：`yas-zabbix-agent`（必须与容器的 `ZBX_HOSTNAME` 一致）
3. 群组：选择或新建（如 `YashanDB`）
4. **Interfaces**：
   - 类型：Agent
   - IP：`yas-zabbix-agent`（使用容器名，Docker 内部 DNS 解析）
   - 端口：`10050`
5. **Templates**：搜索并关联 `YashanDB Monitor`
6. 保存

### 3. 验证监控

等待 1-2 分钟后，在 **监控 → 最新数据** 中筛选 host=yas-zabbix-agent，确认指标有数据。

---

## 一键重建脚本（含 Agent）

```powershell
# === rebuild-zabbix-full.ps1 ===
docker stop zabbix-server zabbix-web yas-zabbix-agent 2>$null
docker rm   zabbix-server zabbix-web yas-zabbix-agent 2>$null

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

Write-Host "等待初始化..."
Start-Sleep -Seconds 30
docker ps --format "table {{.Names}}`t{{.Status}}`t{{.Ports}}" | findstr -i "zabbix`|yas"
Write-Host ""
Write-Host "验证 Agent 连通性："
docker exec zabbix-server zabbix_get -s yas-zabbix-agent -p 10050 -k "agent.ping"
Write-Host "Web UI: http://localhost:8080 (Admin/zabbix)"
```

---

## 关键配置说明

| 参数 | 值 | 说明 |
|------|-----|------|
| `DB_SERVER_HOST` | `host.docker.internal` | 访问 Windows 宿主机上的 WSL MySQL |
| `DB_SERVER_PORT` | `3308` | WSL MySQL 监听端口 |
| `ZBX_SERVER_HOST` | `zabbix-server` | Web/Agent 通过 Docker 内部 DNS 访问 Server |
| `PHP_TZ` | `Asia/Shanghai` | 时区 |
| `ZBX_HOSTNAME` | `yas-zabbix-agent` | Agent 注册名，必须与 Zabbix Web 主机名一致 |
| `YASDB_PASSWORD` | `Cod-2022` | YashanDB sys 用户密码（yas_oracle 环境变量） |
| `10051` | Server 端口 | Zabbix Agent 主动连接此端口 |
| `8080` | Web 端口 | 浏览器访问此端口 |
| `10050` | Agent 被动端口 | zabbix_get / Zabbix Server 拉取数据 |

## yas-zabbix-agent 镜像说明

| 组件 | 版本 | 说明 |
|------|------|------|
| 基础镜像 | `zabbix/zabbix-agent:centos-6.0-latest` (CentOS Stream 9) | 与 YashanDB glibc 库兼容 |
| Python | 3.9.25 | 系统自带 |
| yaspy | 1.2.0 | YashanDB Python 驱动（含 C 扩展 yacapi） |
| Zabbix Agent | 6.0.45 | 稳定版 LTS |
| YashanDB 库 | libyascli.so（来自 yas_agent_libs 卷）| glibc 编译版，由 yas_oracle 容器提取 |

**关键设计**：
- `entrypoint.sh`：启动时注入 `LD_LIBRARY_PATH`、写 YashanDB 连接 ini、配置 Zabbix Agent Server/Include
- `wrapper.sh`：每次 UserParameter 调用时重新 export `LD_LIBRARY_PATH`（解决子进程不继承问题）
- 配置文件方式：密码通过 `yashandb.ini` 传递（不出现在进程列表中）

---

## MySQL 直导模板的关键修复（2026-04-11）

通过 MySQL 直接导入 Zabbix 模板时，**必须**在主机创建完成后更新 items 的 `interfaceid`：

```sql
-- 将 items 的 interfaceid 从 NULL 更新为主机真实接口
UPDATE items
SET interfaceid = (
    SELECT interfaceid FROM interface
    WHERE hostid = <hostid> AND type = 1 AND main = 1
)
WHERE hostid = <hostid> AND interfaceid IS NULL;
```

**原因**：Zabbix Server 的 pollers 通过 `interfaceid` 查找目标 IP:Port 进行数据采集。如果 `interfaceid` 为 NULL，Server 找不到主机地址，pollers 永远无法采集数据。API 创建 items 时会自动关联，但 MySQL 直导需要手动修复。




# YashanDB Docker 容器快速启动指南

> 适用版本：YashanDB 23.4.7.100
> 适用环境：Windows + Docker Desktop（WSL2 后端）
> 文档日期：2026-04-11

---

## 一、核心结论（必读）

**官方 Docker 镜像只支持原生 yashan 模式，容器启动时无法指定 Oracle/MySQL 兼容模式。**

兼容模式需要在容器运行后，通过 SQL 命令配置（见本文档第五节）。

---

## 二、启动前准备

### 2.1 清理旧容器和数据卷

```powershell
docker stop yas_oracle yas_mysql 2>$null
docker rm yas_oracle yas_mysql 2>$null
docker volume rm yas_oracle_data yas_mysql_data 2>$null
```

### 2.2 创建命名数据卷（绕过 NTFS 权限问题）

Docker Desktop 在 Windows 上的 bind mount 对 yashan 用户的权限处理有问题（CapEff=0，cap_dac_override 虽在 Bounding 中但无法使用，导致 yashan 用户读 NTFS 挂载文件报 Permission denied）。

**解决方案：数据存在 Docker 命名卷中（绕过 NTFS），yasboot 配置用 bind mount。**

```powershell
docker volume create yas_oracle_data
docker volume create yas_mysql_data
```

### 2.3 预创建 yasboot 配置目录

```powershell
mkdir C:\Users\DELL\yashan_oracle
mkdir C:\Users\DELL\yashan_mysql
```

---

## 三、启动容器

### 3.1 两条命令同时执行

```powershell
# 容器1：yas_oracle，端口 1688
docker run -d --name yas_oracle --restart unless-stopped `
  -p 1688:1688 `
  -v C:\Users\DELL\yashan_oracle:/home/yashan/.yasboot `
  -v yas_oracle_data:/data/yashan `
  -e SYS_PASSWD=Cod-2022 `
  docker.1ms.run/yasdb/yashandb:23.4.7.100

# 容器2：yas_mysql，端口 1690
docker run -d --name yas_mysql --restart unless-stopped `
  -p 1690:1688 `
  -v C:\Users\DELL\yashan_mysql:/home/yashan/.yasboot `
  -v yas_mysql_data:/data/yashan `
  -e SYS_PASSWD=Cod-2022 `
  docker.1ms.run/yasdb/yashandb:23.4.7.100
```

### 3.2 等待初始化完成

初始化大约需要 30~60 秒。

```powershell
# 等待 60 秒
Start-Sleep -Seconds 60

# 查看日志，看到以下输出表示成功：
# task completed, status: SUCCESS
# yashandb init success!

docker logs yas_oracle --tail 5
docker logs yas_mysql --tail 5
```

### 3.3 验证容器状态

```powershell
docker ps --format "{{.Names}}: {{.Status}}"
# 应显示：
# yas_oracle: Up xx seconds
# yas_mysql: Up xx seconds
```

---

## 四、连接验证

### 4.1 进入容器

```bash
# 进入 yas_oracle
docker exec -it yas_oracle bash -l

# 进入 yas_mysql
docker exec -it yas_mysql bash -l
```

进入后**先执行** `source /home/yashan/.bashrc`，再运行 yasql。

### 4.2 连接数据库

```bash
# 在容器内执行（先 source）
source /home/yashan/.bashrc

# 用 yasql 连接（127.0.0.1 而非 localhost）
yasql sys/Cod-2022@127.0.0.1:1688

# 简单查询验证
SELECT status FROM V$INSTANCE;
SELECT TO_CHAR(SYSDATE, 'YYYY-MM-DD HH24:MI:SS') FROM DUAL;
EXIT
```

### 4.3 从 Windows 宿主机连接

使用 Windows 安装的 yasql 客户端：

```
C:\Users\DELL\yashan\data\install\23.4.7.100\bin\yasql.exe
```

---

## 五、配置 MySQL 兼容模式（可选）

> 注意：以下操作在 yas_mysql 容器内执行。

### 5.1 生成 RSA 密钥对

```bash
source /home/yashan/.bashrc
cd /data/yashan/data

# 生成私钥
openssl genpkey -algorithm RSA -out mysqlkey/private_key.pem -pkeyopt rsa_keygen_bits:2048

# 生成公钥
openssl rsa -pubout -in mysqlkey/private_key.pem -out mysqlkey/public_key.pem
```

### 5.2 配置 service.ini

```bash
cd /data/yashan/data/db-1-1/config
cat > service.ini << 'EOF'
SERVICE1 = {library = yas_my, name = mysql, args = "URL=0.0.0.0:3306,RSA_PRIVATE_FILE=/data/yashan/data/mysqlkey/private_key.pem,RSA_PUBLIC_FILE=/data/yashan/data/mysqlkey/public_key.pem"}
EOF
```

### 5.3 设置 SQL_PLUGIN 并重启

```sql
-- 连接后执行
ALTER SYSTEM SET SQL_PLUGIN = 'MYSQL' SCOPE = SPFILE;
```

重启容器：

```powershell
docker restart yas_mysql
```

---

## 六、容器管理常用命令

```powershell
# 查看状态
docker ps

# 查看日志
docker logs yas_oracle --tail 20
docker logs yas_mysql --tail 20

# 进入容器
docker exec -it yas_oracle bash -l
docker exec -it yas_mysql bash -l

# 查看 yasdb 进程
docker exec yas_oracle bash -c 'ps aux | grep yasdb'

# 查看端口映射
docker port yas_oracle
docker port yas_mysql

# 重启
docker restart yas_oracle yas_mysql

# 停止
docker stop yas_oracle yas_mysql

# 完整删除重建
docker stop yas_oracle yas_mysql
docker rm yas_oracle yas_mysql
docker volume rm yas_oracle_data yas_mysql_data
```

---

## 七、已知问题与解决

### 7.1 Windows bind mount 权限问题

- **症状**：`Permission denied`（errno 13），即使 chmod 后仍无法读取配置文件
- **原因**：Docker Desktop (WSL2) 的 Linux VM 中 yashan 用户（uid=1000）在 NTFS 挂载上没有对应身份，cap_dac_override 无法使用
- **解决**：数据存 Docker 命名卷，不要用 bind mount 存数据文件

### 7.2 yasql 连接报 invalid symbol

- **原因**：PowerShell 中 `$` 和 `\` 转义问题
- **解决**：进入容器 bash 后执行，避免 PowerShell 传参

### 7.3 旧数据导致 reload 失败

- **症状**：`Detected existing data, will reload...`，但 /data/yashan/install 不存在
- **原因**：旧容器的 yasboot 配置残留在新 bind mount 目录中
- **解决**：清空 yasboot 目录后再重建容器
  ```powershell
  rmdir /s /q C:\Users\DELL\yashan_oracle
  rmdir /s /q C:\Users\DELL\yashan_mysql
  mkdir C:\Users\DELL\yashan_oracle
  mkdir C:\Users\DELL\yashan_mysql
  ```

### 7.4 官方文档说明

Docker 镜像仅支持原生 yashan 模式部署，兼容模式（Oracle/MySQL）需在数据库运行后配置。
参考：https://doc.yashandb.com/yashandb/23.4/zh/All-Manuals/Getting-Started/Quick-Start-with-YashanDB.html

#!/bin/bash
export PATH=/data/yashan/install/23.4.7.100/bin:$PATH
export LD_LIBRARY_PATH=/data/yashan/install/23.4.7.100/lib:$LD_LIBRARY_PATH

echo "=== Fix permissions ==="
chmod 755 /data/yashan/data/db-1-1/mysqlkey
ls -la /data/yashan/data/db-1-1/mysqlkey/
ls -la /data/yashan/data/db-1-1/config/service.ini

echo "=== Starting YashanDB ==="
yasboot process yasdb start -c yashandb
echo "Exit: $?"

echo "=== Waiting 10s for startup ==="
sleep 10

echo "=== Checking ports ==="
cat /proc/net/tcp | awk '{print $2}' | while read addr; do
  port=$(echo $addr | cut -d: -f2)
  printf "%d\n" 0x$port 2>/dev/null
done | sort -n | uniq

echo "=== Done ==="

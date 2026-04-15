#!/bin/bash
export PATH=/data/yashan/install/23.4.7.100/bin:$PATH
export LD_LIBRARY_PATH=/data/yashan/install/23.4.7.100/lib:$LD_LIBRARY_PATH
echo "Stopping YashanDB..."
yasboot process yasdb stop -c yashandb
echo "Exit: $?"
sleep 2
echo "Starting YashanDB..."
yasboot process yasdb start -c yashandb
echo "Exit: $?"
sleep 5
echo "Checking ports..."
cat /proc/net/tcp | awk '{print $2}' | while read addr; do
  port=$(echo $addr | cut -d: -f2)
  printf "%d\n" 0x$port 2>/dev/null
done | sort -n | uniq

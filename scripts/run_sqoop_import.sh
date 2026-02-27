#!/bin/bash

# Wait for services
sleep 10

# Sqoop Command
# Import from MySQL 'sales' table to HDFS
export HADOOP_OPTS="-Dmapreduce.framework.name=local -Dfs.defaultFS=hdfs://namenode:9000"

# Minimal Hadoop config for Sqoop container (fs.defaultFS)
cat >/tmp/core-site.xml <<'EOF'
<configuration>
  <property>
    <name>fs.defaultFS</name>
    <value>hdfs://namenode:9000</value>
  </property>
</configuration>
EOF
export HADOOP_CONF_DIR=/tmp

# Ensure classpath contains generated classes + Hadoop libs
export HADOOP_CLASSPATH="$(hadoop classpath --glob):/tmp/sqoop_classes"

mkdir -p /tmp/sqoop_classes
sqoop import \
  --bindir /tmp/sqoop_classes \
  --outdir /tmp/sqoop_classes \
  --class-name Sales \
  --driver com.mysql.cj.jdbc.Driver \
  --connect jdbc:mysql://mysql:3306/retail_db \
  --username root \
  --password root \
  --table sales \
  --target-dir /user/sqoop/sales \
  --delete-target-dir \
  --m 1

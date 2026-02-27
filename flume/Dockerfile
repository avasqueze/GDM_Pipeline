FROM eclipse-temurin:8-jdk

# Versions
ENV FLUME_VERSION=1.9.0
ENV HADOOP_VERSION=3.2.1

# Install dependencies
RUN apt-get update && apt-get install -y wget tar && rm -rf /var/lib/apt/lists/*

# Install Hadoop
RUN wget https://archive.apache.org/dist/hadoop/common/hadoop-$HADOOP_VERSION/hadoop-$HADOOP_VERSION.tar.gz -O /tmp/hadoop.tar.gz && \
    tar -xzf /tmp/hadoop.tar.gz -C /opt/ && \
    mv /opt/hadoop-$HADOOP_VERSION /opt/hadoop && \
    rm /tmp/hadoop.tar.gz

# Install Flume
RUN wget https://archive.apache.org/dist/flume/$FLUME_VERSION/apache-flume-$FLUME_VERSION-bin.tar.gz -O /tmp/flume.tar.gz && \
    tar -xzf /tmp/flume.tar.gz -C /opt/ && \
    mv /opt/apache-flume-$FLUME_VERSION-bin /opt/flume && \
    rm /tmp/flume.tar.gz

# Setup Environment
ENV HADOOP_HOME=/opt/hadoop
ENV FLUME_HOME=/opt/flume
ENV PATH=$PATH:$HADOOP_HOME/bin:$FLUME_HOME/bin
ENV HADOOP_CLASSPATH=$HADOOP_HOME/share/hadoop/common/lib/*:$HADOOP_HOME/share/hadoop/common/*:$HADOOP_HOME/share/hadoop/hdfs/lib/*:$HADOOP_HOME/share/hadoop/hdfs/*

# Remove conflicting slf4j from Flume (use Hadoop's or ensure no conflict)
# Also remove Guava to avoid NoSuchMethodError (hadoop uses newer guava)
RUN rm $FLUME_HOME/lib/slf4j-log4j12-*.jar && \
    rm $FLUME_HOME/lib/guava-*.jar

WORKDIR /opt/flume

CMD ["flume-ng", "agent"]

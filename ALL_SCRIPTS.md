# Explicación de los Scripts

### 1. `docker-compose.yml` (El Orquestador)

Este archivo es la columna vertebral de la infraestructura. Se encarga de descargar, configurar y conectar todos los servicios en una red virtual aislada.

* **Servicios base:** Despliega contenedores para Zookeeper (coordinación), Kafka (streaming), NameNode y DataNode (almacenamiento HDFS), y MySQL (base de datos relacional).
* **Servicios de ingesta y visualización:** Incluye contenedores específicos para Flume, Sqoop, Kafka UI y el Dashboard en Python.
* **Mapeo de puertos:** Define cómo la máquina host se comunica con los contenedores; por ejemplo, mapea el puerto interno 3306 de MySQL al puerto externo 13307 de tu computadora.

**File**: `docker-compose.yml`
```yaml
version: "3"

services:
  # --- COORDINTATION ---
  zookeeper:
    image: confluentinc/cp-zookeeper:7.3.0
    hostname: zookeeper
    container_name: zookeeper
    ports:
      - "22181:2181"
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181
      ZOOKEEPER_TICK_TIME: 2000

  # --- REAL-TIME: KAFKA ---
  kafka:
    image: confluentinc/cp-kafka:7.3.0
    hostname: kafka
    container_name: kafka
    depends_on:
      - zookeeper
    ports:
      - "19092:9092"
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: 'zookeeper:2181'
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: PLAINTEXT:PLAINTEXT,PLAINTEXT_HOST:PLAINTEXT
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092,PLAINTEXT_HOST://localhost:19092
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS: 0

  kafka-ui:
    image: provectuslabs/kafka-ui:latest
    container_name: kafka-ui
    ports:
      - "18080:8080"
    depends_on:
      - kafka
      - zookeeper
    environment:
      KAFKA_CLUSTERS_0_NAME: local
      KAFKA_CLUSTERS_0_BOOTSTRAPSERVERS: kafka:9092
      KAFKA_CLUSTERS_0_ZOOKEEPER: zookeeper:2181

  dashboard:
    image: python:3.9-slim
    container_name: dashboard
    volumes:
      - ./dashboard:/app
    working_dir: /app
    ports:
      - "18501:8501"
    command: sh -c "pip install streamlit pandas sqlalchemy pymysql plotly cryptography protobuf kafka-python kazoo && streamlit run app.py"
    depends_on:
      - mysql

  # --- STORAGE: HADOOP HDFS ---
  namenode:
    image: bde2020/hadoop-namenode:2.0.0-hadoop3.2.1-java8
    container_name: namenode
    volumes:
      - namenode_data:/hadoop/dfs/name
    environment:
      - CLUSTER_NAME=test
      - HDFS_CONF_dfs_permissions_enabled=false
    env_file:
      - ./hadoop.env
    ports:
      - "19870:9870"
      - "19000:9000"

  datanode:
    image: bde2020/hadoop-datanode:2.0.0-hadoop3.2.1-java8
    container_name: datanode
    volumes:
      - datanode_data:/hadoop/dfs/data
    environment:
      - HDFS_CONF_dfs_permissions_enabled=false
    env_file:
      - ./hadoop.env
    links:
      - namenode

  # --- DATABASE: MySQL ---
  mysql:
    image: mysql:8.0
    container_name: mysql
    environment:
      MYSQL_ROOT_PASSWORD: root
      MYSQL_DATABASE: retail_db
    ports:
      - "13307:3306"
    volumes:
      - mysql_data:/var/lib/mysql

  # --- LOG COLLECTION: FLUME ---
  flume:
    build:
      context: ./flume
      dockerfile: Dockerfile
    container_name: flume
    command: flume-ng agent -n agent -c /opt/flume-config -f /opt/flume-config/flume.conf -Dflume.root.logger=INFO,console
    environment:
      - FLUME_AGENT_NAME=agent
      - HADOOP_CONF_DIR=/opt/flume-config
    volumes:
      - ./conf/flume.conf:/opt/flume-config/flume.conf
      - ./conf/core-site.xml:/opt/flume-config/core-site.xml
      - ./logs:/var/log/app_logs
    depends_on:
      - namenode
      - kafka

  # --- ETL: SQOOP (Client Container) ---
  sqoop:
    image: dvoros/sqoop:latest
    container_name: sqoop
    volumes:
      - ./scripts:/scripts
      - ./mysql-connector-java-8.0.28.jar:/usr/local/sqoop/lib/mysql-connector-java-8.0.28.jar
    command: tail -f /dev/null
    depends_on:
      - namenode
      - datanode
      - mysql
    environment:
      - HADOOP_HOME=/usr/local/hadoop

volumes:
  namenode_data:
  datanode_data:
  mysql_data:
```

### 2. `dashboard/app.py` (La Capa de Consumo)

Esta es la aplicación web interactiva construida con Streamlit que actúa como la "Capa de Servicio" (Serving Layer).

* **Conexiones:** Utiliza `SQLAlchemy` para conectarse a MySQL y extraer la historia, y `kafka-python` para suscribirse al flujo de datos en vivo.
* **Pestaña "Historical Analysis":** Ejecuta una consulta SQL simple (`SELECT * FROM sales`) y utiliza la librería `plotly` para renderizar gráficos de barras y tortas basados en el tamaño de las ventas y los tipos de productos.
* **Pestaña "Real-Time Stream":** Se conecta al tópico de Kafka y extrae un lote de los mensajes más recientes cada vez que se actualiza, calculando el valor total de esas transacciones recientes.
* **Pestaña "System Health":** Utiliza la librería `kazoo` para conectarse a Zookeeper y verificar la cantidad de brokers y tópicos activos, además de hacer un ping a los puertos de los demás servicios.

**File**: `dashboard/app.py`
```python
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import plotly.express as px
import time
import json
from kafka import KafkaConsumer
from kazoo.client import KazooClient

# Page Config
st.set_page_config(page_title="Retail Analytics Dashboard", layout="wide", page_icon="📈")

# --- CSS / STYLING ---
st.markdown("""
<style>
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        text-align: center;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 2px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: #f0f2f6;
        border-radius: 4px 4px 0px 0px;
        gap: 1px;
        padding-top: 10px;
        padding-bottom: 10px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #e6f0ff;
        border-bottom: 2px solid #007bff;
    }
</style>
""", unsafe_allow_html=True)

# --- CONNECTIONS ---

@st.cache_resource
def get_db_connection():
    return create_engine('mysql+pymysql://root:root@mysql:3306/retail_db')

def get_kafka_consumer():
    try:
        consumer = KafkaConsumer(
            'transactions',
            bootstrap_servers=['kafka:9092'],
            auto_offset_reset='latest',
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            consumer_timeout_ms=1000 
        )
        return consumer
    except Exception as e:
        return None

def get_zookeeper_client():
    try:
        zk = KazooClient(hosts='zookeeper:2181')
        zk.start(timeout=5)
        return zk
    except Exception as e:
        return None

# --- TABS ---

st.title("🚀 Retail Big Data Analytics")
st.markdown("*Real-time insights powered by Hadoop, Kafka, and Spark ecosystem.*")

tab1, tab2, tab3 = st.tabs(["📊 Historical Analysis", "⚡ Real-Time Stream", "🔧 System Health"])

# --- TAB 1: HISTORICAL (MySQL) ---
with tab1:
    st.header("Historical Sales Analysis (Batch Data)")
    if st.button("Refresh Historical Data"):
        st.cache_data.clear()
    engine = get_db_connection()
    try:
        df = pd.read_sql("SELECT * FROM sales", engine)
        if not df.empty:
            c1, c2, c3, c4 = st.columns(4)
            total_sales = df['SALES'].sum()
            c1.metric("Total Revenue", f"${total_sales:,.2f}")
            c2.metric("Total Orders", len(df))
            c3.metric("Avg Deal Size", f"${df['SALES'].mean():,.2f}")
            c4.metric("Unique Customers", df['CUSTOMERNAME'].nunique())
            st.divider()
            row1_1, row1_2 = st.columns(2)
            with row1_1:
                st.subheader("Sales by Product Line")
                prod_data = df.groupby('PRODUCTLINE')['SALES'].sum().reset_index()
                fig_prod = px.bar(prod_data, x='PRODUCTLINE', y='SALES', color='SALES', color_continuous_scale='Viridis', title="Revenue per Product Line")
                st.plotly_chart(fig_prod, use_container_width=True)
            with row1_2:
                st.subheader("Deal Size Distribution")
                deal_counts = df['DEALSIZE'].value_counts().reset_index()
                deal_counts.columns = ['DEALSIZE', 'COUNT']
                fig_deal = px.pie(deal_counts, values='COUNT', names='DEALSIZE', title="Deal Size Segmentation", hole=0.4, color_discrete_sequence=px.colors.sequential.RdBu)
                st.plotly_chart(fig_deal, use_container_width=True)
            row2_1, row2_2 = st.columns(2)
            with row2_1:
                st.subheader("Top 10 Customers")
                cust_data = df.groupby('CUSTOMERNAME')['SALES'].sum().reset_index().sort_values('SALES', ascending=False).head(10)
                fig_cust = px.bar(cust_data, y='CUSTOMERNAME', x='SALES', orientation='h', title="Top Revenue Generating Customers")
                fig_cust.update_layout(yaxis_autorange="reversed")
                st.plotly_chart(fig_cust, use_container_width=True)
            with row2_2:
                st.subheader("Order Status Overview")
                status_counts = df['STATUS'].value_counts().reset_index()
                status_counts.columns = ['STATUS', 'COUNT']
                fig_stat = px.bar(status_counts, x='STATUS', y='COUNT', color='STATUS', title="Order Status Breakdown")
                st.plotly_chart(fig_stat, use_container_width=True)
        else:
            st.warning("No data found in MySQL. Please run Sqoop import.")
    except Exception as e:
        st.error(f"Database Connection Failed: {e}")

# --- TAB 2: REAL-TIME (Kafka) ---
with tab2:
    st.header("Live Transaction Stream (Kafka)")
    st.info("Fetching real-time transactions from 'transactions' topic...")
    col_k1, col_k2 = st.columns([3, 1])
    with col_k2:
        if st.button("Fetch Latest Stream"):
           st.rerun()
    consumer = get_kafka_consumer()
    if consumer:
        messages = []
        records = consumer.poll(timeout_ms=2000, max_records=20)
        for topic_partition, consumer_records in records.items():
            for record in consumer_records:
                messages.append(record.value)
        if messages:
            st.success(f"Captured {len(messages)} recent events.")
            df_stream = pd.DataFrame(messages)
            st.dataframe(df_stream, use_container_width=True)
            c_rt1, c_rt2 = st.columns(2)
            c_rt1.metric("Recent Total Value", f"${df_stream['amount'].sum():,.2f}")
            c_rt2.metric("Most Common Status", df_stream['status'].mode()[0] if not df_stream.empty else "N/A")
        else:
            st.info("No new messages found in this poll window. (Ensure Producer is running)")
        consumer.close()
    else:
        st.error("Could not connect to Kafka Broker at kafka:9092")

# --- TAB 3: SYSTEM HEALTH (Zookeeper) ---
with tab3:
    st.header("Cluster Health Monitoring")
    c_z1, c_z2 = st.columns(2)
    # 1. Zookeeper Status
    zk = get_zookeeper_client()
    with c_z1:
        st.subheader("Zookeeper Status")
        if zk and zk.connected:
            st.success("✅ Online (Connected to zookeeper:2181)")
            try:
                brokers_ids = zk.get_children("/brokers/ids")
                topics = zk.get_children("/brokers/topics")
                st.metric("Active Brokers", len(brokers_ids))
                st.metric("Active Topics", len(topics))
                with st.expander("View Active Topics"):
                    st.write(topics)
            except Exception as e:
                st.warning(f"Connected, but failed to read metadata: {e}")
            zk.stop()
            zk.close()
        else:
            st.error("❌ Offline (Could not connect to zookeeper:2181)")
    # 2. Service Port Checks
    with c_z2:
        st.subheader("Service Connectivity")
        import socket
        def check_port(host, port):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex((host, port))
                sock.close()
                return result == 0
            except:
                return False
        services = {
            "Namenode (HDFS)": ("namenode", 9870),
            "Datanode (HDFS)": ("datanode", 9864),
            "Kafka Broker": ("kafka", 9092),
            "MySQL": ("mysql", 3306)
        }
        for name, (host, port) in services.items():
            if check_port(host, port):
                st.markdown(f"**{name}**: :green[Online] ✅")
            else:
                st.markdown(f"**{name}**: :red[Offline] ❌")
```

### 3. `datagen/producer.py` (El Generador de Eventos)

Este script de Python simula el comportamiento de los clientes comprando en una tienda en tiempo real.

* **Generación de datos:** Crea diccionarios JSON aleatorios que incluyen un ID de orden, un monto, un estado de envío y un ID de cliente.
* **Doble salida:** Envía cada transacción al tópico `transactions` en Kafka para el procesamiento en tiempo real.
* **Simulación de Logs:** Simultáneamente, escribe esa misma transacción en un archivo de texto plano (`logs/app.log`) para simular los registros internos de un servidor web.
 
**File**: `datagen/producer.py`
```python
import time
import json
import random
from kafka import KafkaProducer
import logging

# Setup Logging (for Flume)
logging.basicConfig(
    filename='logs/app.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)

def get_producer():
    producer = None
    for i in range(10):
        try:
            producer = KafkaProducer(
                bootstrap_servers=['localhost:19092'],
                value_serializer=lambda x: json.dumps(x).encode('utf-8')
            )
            print("Connected to Kafka!")
            return producer
        except Exception as e:
            print(f"Waiting for Kafka... {e}")
            time.sleep(5)
    return None

def generate_transactions():
    producer = get_producer()
    if not producer:
        print("Failed to connect to Kafka producer.")
        return

    statuses = ['ORDERED', 'SHIPPED', 'DELIVERED', 'CANCELLED']
    
    print("Starting data generation...")
    try:
        while True:
            # Create a dummy transaction
            transaction = {
                'order_id': random.randint(10000, 99999),
                'amount': round(random.uniform(10.0, 500.0), 2),
                'status': random.choice(statuses),
                'customer_id': random.randint(1, 1000)
            }
            
            # Send to Kafka (Real-time path)
            producer.send('transactions', value=transaction)
            print(f"Sent to Kafka: {transaction}")
            
            # Write to Log (Flume path)
            logging.info(f"Transaction Processed: {transaction}")
            
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("Stopping generator.")

if __name__ == "__main__":
    generate_transactions()
```

### 4. `datagen/setup_db.py` (El Sembrador de la Capa Batch)

Este archivo se ejecuta una sola vez al inicio del proyecto para simular que la empresa ya tiene años de historia acumulada.

* **Procesamiento con Pandas:** Lee un archivo local llamado `sales_data_sample.csv` y limpia los nombres de las columnas para asegurar compatibilidad con la base de datos.
* **Inserción masiva:** Utiliza el método `to_sql` para crear la tabla `sales` dentro del contenedor de MySQL e insertar todos los registros del CSV de forma automática.

**File**: `datagen/setup_db.py`
```python
import pandas as pd
from sqlalchemy import create_engine
import time

def seeding():
    # Load CSV
    print("Loading CSV...")
    try:
        df = pd.read_csv('sales_data_sample.csv', encoding='ISO-8859-1')
        # Simplify column names for MySQL
        df.columns = [c.replace(" ", "_").replace("-", "_").upper() for c in df.columns]
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return

    # Connect to MySQL
    engine = None
    for i in range(10):
        try:
            print(f"Connecting to DB (Attempt {i+1})...")
            engine = create_engine('mysql+pymysql://root:root@localhost:13307/retail_db')
            with engine.connect() as conn:
                print("Connected!")
            break
        except Exception:
            time.sleep(5)
    
    if not engine:
        print("Could not connect to MySQL.")
        return

    # Write to SQL
    print("Writing to MySQL...")
    try:
        df.to_sql('sales', con=engine, if_exists='replace', index=False)
        print("Data seeded successfully!")
    except Exception as e:
        print(f"Error writing to SQL: {e}")

if __name__ == "__main__":
    seeding()
```

### 5. `scripts/run_sqoop_import.sh` (ETL)

Este script de Bash ejecuta el comando de Sqoop que extrae los datos de MySQL y los guarda de forma distribuida.

* **Configuración del entorno:** Define las variables de Hadoop y crea un archivo de configuración temporal (`core-site.xml`) para que Sqoop sepa cómo encontrar el NameNode en el puerto 9000.
* **Comando de importación:** Se conecta a la base de datos `retail_db` usando las credenciales root, selecciona la tabla `sales` y define la ruta de destino en HDFS (`/user/sqoop/sales`).

**File**: `scripts/run_sqoop_import.sh`
```bash
#!/bin/bash

# Wait for services
sleep 10

# Sqoop Command
# Import from MySQL 'sales' table to HDFS
export HADOOP_OPTS="-Dmapreduce.framework.name=local -Dfs.defaultFS=hdfs://namenode:9000"

# Minimal Hadoop config for Sqoop container
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
```

### 6. `conf/flume.conf` (El Agente de Recolección de Logs)

Este archivo de propiedades define el comportamiento del contenedor de Flume para el transporte continuo de datos no estructurados.

* **Source (Origen):** Está configurado como tipo `exec` para ejecutar el comando de Linux `tail -F` sobre el archivo `app.log`, capturando cada nueva línea que el `producer.py` escribe.
* **Channel (Canal):** Utiliza la memoria RAM (`memory`) para almacenar temporalmente los eventos antes de enviarlos, lo que permite un procesamiento muy rápido.
* **Sink (Destino):** Está configurado para conectarse a HDFS y agrupar los registros de texto, creando un nuevo archivo cada 30 segundos (rollInterval) en la ruta `/user/flume/logs/`.
* 
**File**: `conf/flume.conf`
```properties
# Flume Component Naming
agent.sources = r1
agent.sinks = k1
agent.channels = c1

# Source: Tail a log file (Simulating app logs)
agent.sources.r1.type = exec
agent.sources.r1.command = tail -F /var/log/app_logs/app.log

# Sink: HDFS
agent.sinks.k1.type = hdfs
agent.sinks.k1.hdfs.path = hdfs://namenode:9000/user/flume/logs/%y-%m-%d
agent.sinks.k1.hdfs.fileType = DataStream
agent.sinks.k1.hdfs.writeFormat = Text
agent.sinks.k1.hdfs.rollInterval = 30
agent.sinks.k1.hdfs.rollSize = 0
agent.sinks.k1.hdfs.rollCount = 0
agent.sinks.k1.hdfs.useLocalTimeStamp = true

# Channel: Memory
agent.channels.c1.type = memory
agent.channels.c1.capacity = 1000
agent.channels.c1.transactionCapacity = 100

# Bindings
agent.sources.r1.channels = c1
agent.sinks.k1.channel = c1
```

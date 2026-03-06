# Introducción a Docker, Docker Compose y Docker Hub

------------------------------------------------------------------------

## ¿Qué es Docker?

**Docker** es una plataforma de software que permite crear, probar y desplegar aplicaciones de manera rápida y consistente mediante **contenedores**.

Un contenedor es una unidad que incluye todo lo necesario para ejecutar una aplicación: código, librerías, dependencias y configuraciones, asegurando que se ejecute igual en cualquier entorno.

### Características principales:

-   Portabilidad: "Se ejecuta en mi máquina" deja de ser un problema.
-   Ligereza: Los contenedores comparten el kernel del sistema operativo, lo que los hace más livianos que las máquinas virtuales.
-   Escalabilidad: Ideal para arquitecturas de microservicios.
-   Rapidez: Arranque casi instantáneo.

Ejemplo básico para ejecutar un contenedor:

``` bash
docker run hello-world
```

------------------------------------------------------------------------

## ¿Qué es Docker Compose?

**Docker Compose** es una herramienta que permite definir y ejecutar aplicaciones multi-contenedor usando un solo archivo de configuración (`docker-compose.yml`).

Con Compose puedes levantar servicios relacionados (Hadoop y Spark) con un solo comando.

### Ventajas:

-   Define múltiples servicios en un archivo legible (YAML).
-   Facilita levantar entornos de desarrollo completos con un solo comando.
-   Permite manejar redes, volúmenes y dependencias entre contenedores.

### Partes de un archivo `docker-compose.yml`

Un archivo `docker-compose.yml` se usa para definir y gestionar múltiples contenedores Docker como un solo servicio. Está escrito en formato **YAML** (https://www.datacamp.com/blog/what-is-yaml?utm_source=chatgpt.com) y se compone de varias secciones principales.

------------------------------------------------------------------------

#### 1. **Version**

Define la versión del esquema de Docker Compose que se está utilizando.\
Ejemplo:

``` yaml
version: "3.9"
```

------------------------------------------------------------------------

#### 2. **Services**

Es la sección principal, donde se definen los contenedores (servicios). Cada servicio representa un contenedor que Docker Compose levantará.\
Dentro de cada servicio se especifican opciones como: 
- **image**: la imagen de Docker que se usará. 
- **build**: instrucciones para construir la imagen (si no se usa una preexistente). 
- **ports**: mapeo de puertos del host al contenedor. 
- **volumes**: directorios o archivos compartidos entre el host y contenedor. 
- **environment**: variables de entorno. 
- **depends_on**: orden de inicio entre servicios.

Ejemplo:

``` yaml
  datanode:
    image: bde2020/hadoop-datanode:2.0.0-hadoop3.2.1-java8
    container_name: datanode
    ports:
      - "9864:9864"   # DataNode web UI
    volumes:
      - hadoop_datanode:/hadoop/dfs/data
    environment:
      - SERVICE_PRECONDITION=namenode:9870
      - CORE_CONF_fs_defaultFS=hdfs://namenode:9000
    env_file:
      - ./hadoop.env
    networks: [bdnet]
    depends_on: [namenode]
```

------------------------------------------------------------------------

#### 3. **Volumes**

Define volúmenes persistentes que pueden ser compartidos entre servicios.

Ejemplo:

``` yaml
volumes:
  hadoop_namenode:
```

Luego, se pueden usar en un servicio:

``` yaml
services:
  datanode:
      volumes:
        - hadoop_datanode:/hadoop/dfs/data
```

------------------------------------------------------------------------

#### 4. **Networks**

Permite definir redes personalizadas para conectar los contenedores
entre sí.\
Ejemplo:

``` yaml
networks:
  bdnet:
```

Y en los servicios:

``` yaml
services:
  datanode:
    networks: 
      - bdnet

```

------------------------------------------------------------------------

#### Resumen visual de la estructura

``` yaml
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
      - "19092:19092" 
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: 'zookeeper:2181'
      KAFKA_LISTENERS: PLAINTEXT://0.0.0.0:9092,PLAINTEXT_HOST://0.0.0.0:19092
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
  # Sqoop needs Hadoop libs and MySQL connector
  sqoop:
    image: dvoros/sqoop:latest
    container_name: sqoop
    volumes:
      - ./scripts:/scripts
      - ./mysql-connector-java-8.0.28.jar:/usr/local/sqoop/lib/mysql-connector-java-8.0.28.jar
    # We will keep this alive or run commands via docker run/exec
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


Ejecutar con:

``` bash
docker-compose up
```

------------------------------------------------------------------------

## ¿Qué es Docker Hub?

**Docker Hub** es un **registro de imágenes** en la nube, administrado por Docker Inc. Funciona como un repositorio donde los desarrolladores pueden: 
- Descargar imágenes oficiales (nginx, postgres, redis, etc.). 
- Subir sus propias imágenes personalizadas. 
- Compartir y versionar imágenes con equipos o la comunidad.

### Ventajas:

-   Repositorio centralizado de imágenes confiables.
-   Integración directa con Docker CLI.
-   Automatización de builds y despliegues.

Ejemplo para descargar una imagen desde Docker Hub:

``` bash
docker pull nginx:latest
```

------------------------------------------------------------------------

## Consideraciones finales

-   **Docker**: plataforma para crear y ejecutar aplicaciones en contenedores.
-   **Docker Compose**: orquestador simple de múltiples contenedores con un archivo YAML.
-   **Docker Hub**: repositorio público/privado de imágenes Docker en la nube.

Juntas, estas herramientas permiten un flujo de trabajo ágil y consistente desde el desarrollo hasta la producción.



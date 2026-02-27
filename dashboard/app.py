import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import plotly.express as px
import time
import json
from kafka import KafkaConsumer
from kazoo.client import KazooClient
from kafka import TopicPartition

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
    # Helper to connect to MySQL
    # Retries are handled by SQLAlchemy pool, but we assume network is up
    return create_engine('mysql+pymysql://root:root@mysql:3306/retail_db')

def get_kafka_consumer():
    # Helper to connect to Kafka
    try:
        consumer = KafkaConsumer(
            'transactions',
            bootstrap_servers=['kafka:9092'],
            auto_offset_reset='earliest',
            value_deserializer=lambda x: json.loads(x.decode('utf-8'))
        )
        return consumer
    except Exception as e:
        return None

def get_zookeeper_client():
    # Helper to connect to Zookeeper
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
            # KPIS
            c1, c2, c3, c4 = st.columns(4)
            total_sales = df['SALES'].sum()
            c1.metric("Total Revenue", f"${total_sales:,.2f}")
            c2.metric("Total Orders", len(df))
            c3.metric("Avg Deal Size", f"${df['SALES'].mean():,.2f}")
            c4.metric("Unique Customers", df['CUSTOMERNAME'].nunique())
            
            st.divider()

            # CHARTS
            row1_1, row1_2 = st.columns(2)
            
            with row1_1:
                st.subheader("Sales by Product Line")
                # Group by Product Line
                prod_data = df.groupby('PRODUCTLINE')['SALES'].sum().reset_index()
                fig_prod = px.bar(prod_data, x='PRODUCTLINE', y='SALES', color='SALES', 
                                  color_continuous_scale='Viridis', title="Revenue per Product Line")
                st.plotly_chart(fig_prod, use_container_width=True)

            with row1_2:
                st.subheader("Deal Size Distribution")
                # Deal size pie (Medium, Small, Large)
                deal_counts = df['DEALSIZE'].value_counts().reset_index()
                deal_counts.columns = ['DEALSIZE', 'COUNT']
                fig_deal = px.pie(deal_counts, values='COUNT', names='DEALSIZE', 
                                  title="Deal Size Segmentation", hole=0.4, color_discrete_sequence=px.colors.sequential.RdBu)
                st.plotly_chart(fig_deal, use_container_width=True)
            
            row2_1, row2_2 = st.columns(2)
            
            with row2_1:
                st.subheader("Top 10 Customers")
                cust_data = df.groupby('CUSTOMERNAME')['SALES'].sum().reset_index().sort_values('SALES', ascending=False).head(10)
                fig_cust = px.bar(cust_data, y='CUSTOMERNAME', x='SALES', orientation='h', 
                                  title="Top Revenue Generating Customers")
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

    # Create a consumer on the fly
    consumer = get_kafka_consumer()
    
    if consumer:
        messages = []
        topic_name = 'transactions'
        
        # 1. Ask Kafka for the partitions in this topic
        partitions = consumer.partitions_for_topic(topic_name)
        
        if partitions:
            # 2. Manually assign the consumer to partition 0
            # (Based on the Kafka UI, this topic has 1 partition)
            tp = TopicPartition(topic_name, list(partitions)[0])
            consumer.assign([tp])
            
            # 3. Find the absolute last offset in the topic
            end_offsets = consumer.end_offsets([tp])
            end_offset = end_offsets[tp]
            
            # 4. Calculate where to start reading (end minus 30)
            start_offset = max(0, end_offset - 30)
            consumer.seek(tp, start_offset)
            
            # 5. Poll exactly those last 30 messages
            records = consumer.poll(timeout_ms=2000, max_records=30)
            
            for topic_partition, consumer_records in records.items():
                for record in consumer_records:
                    messages.append(record.value)
                    
            # 6. Reverse the list so the newest transaction is at the top of the UI
            messages.reverse()
        
        if messages:
            st.success(f"Captured the {len(messages)} most recent events.")
            df_stream = pd.DataFrame(messages)
            
            # Show Data
            st.dataframe(df_stream, use_container_width=True)
            
            # Quick Stats
            c_rt1, c_rt2 = st.columns(2)
            c_rt1.metric("Recent Total Value", f"${df_stream['amount'].sum():,.2f}")
            c_rt2.metric("Most Common Status", df_stream['status'].mode()[0] if not df_stream.empty else "N/A")
            
        else:
            st.info("No new messages found. (Ensure Producer is running)")
        
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
                # Inspect Zookeeper ZNodes
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

    # 2. Service Port Checks (Simple connectivity check)
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
            "Datanode (HDFS)": ("datanode", 9864), # 9864 is usually web ui, 9000 is internal
            "Kafka Broker": ("kafka", 9092),
            "MySQL": ("mysql", 3306)
        }
        
        for name, (host, port) in services.items():
            if check_port(host, port):
                st.markdown(f"**{name}**: :green[Online] ✅")
            else:
                st.markdown(f"**{name}**: :red[Offline] ❌")


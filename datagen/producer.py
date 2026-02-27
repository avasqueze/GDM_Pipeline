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
                value_serializer=lambda x: json.dumps(x).encode('utf-8'),
                api_version=(2, 0, 2), # Force version to avoid hanging on detection
                request_timeout_ms=5000,
                max_block_ms=5000
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

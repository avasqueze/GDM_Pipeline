from kafka import KafkaConsumer
import json

print("Attempting to consume from localhost:19092...")
try:
    consumer = KafkaConsumer(
        'transactions',
        bootstrap_servers=['localhost:19092'],
        auto_offset_reset='earliest',
        value_deserializer=lambda x: json.loads(x.decode('utf-8')),
        consumer_timeout_ms=5000
    )
    print("Consumer created. Polling...")
    for msg in consumer:
        print(f"Received: {msg.value}")
        break
    print("Done.")
except Exception as e:
    print(f"Error: {e}")

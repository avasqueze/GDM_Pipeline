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
    # Retrying connection as MySQL container might take time to start
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

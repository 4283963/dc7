import clickhouse_connect
from typing import List, Dict, Optional
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import os

CLICKHOUSE_HOST = os.environ.get("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_PORT = int(os.environ.get("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_USER = os.environ.get("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASSWORD = os.environ.get("CLICKHOUSE_PASSWORD", "")
CLICKHOUSE_DATABASE = os.environ.get("CLICKHOUSE_DATABASE", "fab_monitor")


class ClickHouseClient:
    def __init__(self):
        self.client = None
        self.connect()
        self.init_database()

    def connect(self):
        max_retries = 10
        for i in range(max_retries):
            try:
                self.client = clickhouse_connect.get_client(
                    host=CLICKHOUSE_HOST,
                    port=CLICKHOUSE_PORT,
                    username=CLICKHOUSE_USER,
                    password=CLICKHOUSE_PASSWORD,
                    database=CLICKHOUSE_DATABASE,
                    connect_timeout=10,
                    send_receive_timeout=30,
                )
                logger.info("Connected to ClickHouse successfully")
                return
            except Exception as e:
                logger.warning(f"Connection attempt {i + 1}/{max_retries} failed: {e}")
                time.sleep(2)
        raise Exception("Failed to connect to ClickHouse after multiple retries")

    def init_database(self):
        self.client.command(f"CREATE DATABASE IF NOT EXISTS {CLICKHOUSE_DATABASE}")
        self.client.command(f"USE {CLICKHOUSE_DATABASE}")

        self.client.command("""
            CREATE TABLE IF NOT EXISTS sensor_readings (
                timestamp DateTime64(3, 'Asia/Shanghai'),
                sensor_id String,
                gas_type String,
                concentration Float64,
                x Int32,
                y Int32,
                area String
            )
            ENGINE = MergeTree()
            PARTITION BY toYYYYMMDD(timestamp)
            ORDER BY (timestamp, sensor_id, gas_type)
            TTL timestamp + INTERVAL 7 DAY
            SETTINGS index_granularity = 8192
        """)

        self.client.command("""
            CREATE TABLE IF NOT EXISTS sensor_metadata (
                sensor_id String,
                gas_type String,
                x Int32,
                y Int32,
                area String,
                threshold Float64,
                unit String DEFAULT 'PPM'
            )
            ENGINE = ReplacingMergeTree()
            ORDER BY (sensor_id, gas_type)
        """)
        logger.info("Database tables initialized")

    def insert_reading(self, sensor_id: str, gas_type: str, concentration: float,
                       x: int, y: int, area: str, timestamp: Optional[int] = None):
        if timestamp is None:
            timestamp = int(time.time() * 1000)
        self.client.insert(
            "sensor_readings",
            [[timestamp, sensor_id, gas_type, concentration, x, y, area]],
            column_names=["timestamp", "sensor_id", "gas_type", "concentration", "x", "y", "area"]
        )

    def insert_readings_batch(self, readings: List[Dict]):
        if not readings:
            return
        data = []
        for r in readings:
            ts = r.get("timestamp", int(time.time() * 1000))
            data.append([
                ts, r["sensor_id"], r["gas_type"],
                r["concentration"], r["x"], r["y"], r["area"]
            ])
        self.client.insert(
            "sensor_readings",
            data,
            column_names=["timestamp", "sensor_id", "gas_type", "concentration", "x", "y", "area"]
        )

    def upsert_sensor_metadata(self, sensor_id: str, gas_type: str, x: int, y: int,
                               area: str, threshold: float, unit: str = "PPM"):
        self.client.insert(
            "sensor_metadata",
            [[sensor_id, gas_type, x, y, area, threshold, unit]],
            column_names=["sensor_id", "gas_type", "x", "y", "area", "threshold", "unit"]
        )

    def get_aggregated_data(self, window_seconds: int = 60) -> List[Dict]:
        query = f"""
            SELECT
                sensor_id,
                gas_type,
                avg(concentration) AS avg_concentration,
                max(concentration) AS max_concentration,
                min(concentration) AS min_concentration,
                any(x) AS x,
                any(y) AS y,
                any(area) AS area,
                any(threshold) AS threshold
            FROM sensor_readings
            GLOBAL ANY LEFT JOIN sensor_metadata USING (sensor_id, gas_type)
            WHERE timestamp >= now() - INTERVAL {window_seconds} SECOND
            GROUP BY sensor_id, gas_type
            ORDER BY area, x, y, gas_type
        """
        result = self.client.query(query)
        columns = result.column_names
        return [dict(zip(columns, row)) for row in result.result_rows]

    def get_historical_data(self, sensor_id: str, gas_type: str,
                            minutes: int = 10) -> List[Dict]:
        query = f"""
            SELECT
                timestamp,
                concentration,
                avg(concentration) OVER (ORDER BY timestamp ROWS BETWEEN 5 PRECEDING AND 5 FOLLOWING) AS moving_avg
            FROM sensor_readings
            WHERE 
                timestamp >= now() - INTERVAL {minutes} MINUTE
                AND sensor_id = '{sensor_id}'
                AND gas_type = '{gas_type}'
            ORDER BY timestamp
        """
        result = self.client.query(query)
        columns = result.column_names
        return [dict(zip(columns, row)) for row in result.result_rows]

    def get_all_sensors(self) -> List[Dict]:
        query = """
            SELECT
                sensor_id,
                gas_type,
                x,
                y,
                area,
                threshold,
                unit
            FROM sensor_metadata
            ORDER BY area, x, y, gas_type
        """
        result = self.client.query(query)
        columns = result.column_names
        return [dict(zip(columns, row)) for row in result.result_rows]

    def get_gas_types(self) -> List[str]:
        query = "SELECT DISTINCT gas_type FROM sensor_metadata ORDER BY gas_type"
        result = self.client.query(query)
        return [row[0] for row in result.result_rows]

    def get_areas(self) -> List[str]:
        query = "SELECT DISTINCT area FROM sensor_metadata ORDER BY area"
        result = self.client.query(query)
        return [row[0] for row in result.result_rows]


db_client = None


def get_db_client():
    global db_client
    if db_client is None:
        db_client = ClickHouseClient()
    return db_client

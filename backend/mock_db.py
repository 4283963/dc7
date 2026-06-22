import time
import random
import threading
from typing import List, Dict, Optional
from collections import defaultdict, deque
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class InMemoryDB:
    def __init__(self):
        self.readings = defaultdict(lambda: deque(maxlen=7200))
        self.metadata = {}
        self.lock = threading.Lock()
        self.init_database()
        self.start_simulator()
        logger.info("In-memory database initialized (for demo purposes)")

    def init_database(self):
        self.gas_configs = [
            {"gas_type": "NH3", "threshold": 25.0, "base": 2.0, "variance": 3.0},
            {"gas_type": "SiH4", "threshold": 5.0, "base": 0.5, "variance": 0.8},
            {"gas_type": "HF", "threshold": 3.0, "base": 0.3, "variance": 0.5},
            {"gas_type": "HCl", "threshold": 5.0, "base": 0.4, "variance": 0.6},
            {"gas_type": "PH3", "threshold": 0.3, "base": 0.05, "variance": 0.08},
            {"gas_type": "AsH3", "threshold": 0.05, "base": 0.01, "variance": 0.02},
        ]
        
        self.areas = ["CLEANROOM_A", "CLEANROOM_B", "ETCH_BAY", "DIFFUSION", "WAFER_FAB"]
        self.grid_width = 10
        self.grid_height = 8
        
        sensor_idx = 0
        for area_idx, area in enumerate(self.areas):
            x_start = (area_idx % 2) * 5
            y_start = (area_idx // 2) * 4
            for y in range(y_start, min(y_start + 4, self.grid_height)):
                for x in range(x_start, min(x_start + 5, self.grid_width)):
                    for gas_config in self.gas_configs[:3]:
                        sensor_id = f"S{sensor_idx:04d}"
                        key = (sensor_id, gas_config["gas_type"])
                        self.metadata[key] = {
                            "sensor_id": sensor_id,
                            "gas_type": gas_config["gas_type"],
                            "x": x,
                            "y": y,
                            "area": area,
                            "threshold": gas_config["threshold"],
                            "unit": "PPM",
                            "base": gas_config["base"],
                            "variance": gas_config["variance"]
                        }
                        sensor_idx += 1
        
        self.leak_sensors = set()
        self._backfill_history()

    def _backfill_history(self, hours: int = 2):
        end_time = int(time.time() * 1000)
        start_time = end_time - hours * 3600 * 1000
        step_ms = 1000
        
        current_time = start_time
        while current_time < end_time:
            for key, meta in self.metadata.items():
                base = meta["base"]
                variance = meta["variance"]
                concentration = max(0, base + random.gauss(0, variance))
                key_str = f"{meta['sensor_id']}:{meta['gas_type']}"
                self.readings[key_str].append({
                    "timestamp": current_time,
                    "concentration": round(concentration, 4)
                })
            current_time += step_ms
        
        logger.info(f"Backfilled {len(self.metadata) * 7200} historical readings")

    def start_simulator(self):
        def simulator_worker():
            leak_sensor_ids = [
                k[0] for k in self.metadata.keys() 
                if self.metadata[k]["gas_type"] == "NH3"
            ][:8]
            
            while True:
                cycle_start = time.time()
                
                if random.random() < 0.02:
                    new_leak = random.choice(leak_sensor_ids)
                    self.leak_sensors.add(new_leak)
                    logger.warning(f"⚠️  Simulated leak started at sensor {new_leak}")
                
                if random.random() < 0.01 and self.leak_sensors:
                    removed = self.leak_sensors.pop()
                    logger.info(f"✅  Leak resolved at sensor {removed}")
                
                readings_batch = []
                for key, meta in self.metadata.items():
                    base = meta["base"]
                    variance = meta["variance"]
                    
                    if meta["sensor_id"] in self.leak_sensors:
                        multiplier = random.uniform(1.5, 3.0)
                        concentration = base * multiplier + random.gauss(0, variance)
                    else:
                        concentration = max(0, base + random.gauss(0, variance))
                    
                    reading = {
                        "sensor_id": meta["sensor_id"],
                        "gas_type": meta["gas_type"],
                        "concentration": round(concentration, 4),
                        "x": meta["x"],
                        "y": meta["y"],
                        "area": meta["area"],
                        "timestamp": int(time.time() * 1000)
                    }
                    readings_batch.append(reading)
                    
                    key_str = f"{meta['sensor_id']}:{meta['gas_type']}"
                    self.readings[key_str].append({
                        "timestamp": reading["timestamp"],
                        "concentration": reading["concentration"]
                    })
                
                elapsed = time.time() - cycle_start
                sleep_time = max(0, 1.0 - elapsed)
                time.sleep(sleep_time)
        
        self.simulator_thread = threading.Thread(target=simulator_worker, daemon=True)
        self.simulator_thread.start()
        logger.info("In-memory data simulator started")

    def insert_reading(self, sensor_id: str, gas_type: str, concentration: float,
                       x: int, y: int, area: str, timestamp: Optional[int] = None):
        if timestamp is None:
            timestamp = int(time.time() * 1000)
        
        key = (sensor_id, gas_type)
        if key not in self.metadata:
            self.metadata[key] = {
                "sensor_id": sensor_id,
                "gas_type": gas_type,
                "x": x,
                "y": y,
                "area": area,
                "threshold": 25.0,
                "unit": "PPM"
            }
        
        key_str = f"{sensor_id}:{gas_type}"
        self.readings[key_str].append({
            "timestamp": timestamp,
            "concentration": concentration
        })

    def insert_readings_batch(self, readings: List[Dict]):
        for r in readings:
            self.insert_reading(
                r["sensor_id"], r["gas_type"], r["concentration"],
                r["x"], r["y"], r["area"], r.get("timestamp")
            )

    def upsert_sensor_metadata(self, sensor_id: str, gas_type: str, x: int, y: int,
                               area: str, threshold: float, unit: str = "PPM"):
        key = (sensor_id, gas_type)
        self.metadata[key] = {
            "sensor_id": sensor_id,
            "gas_type": gas_type,
            "x": x,
            "y": y,
            "area": area,
            "threshold": threshold,
            "unit": unit
        }

    def get_aggregated_data(self, window_seconds: int = 60) -> List[Dict]:
        cutoff = int(time.time() * 1000) - window_seconds * 1000
        results = []
        
        with self.lock:
            for key, meta in self.metadata.items():
                key_str = f"{meta['sensor_id']}:{meta['gas_type']}"
                sensor_readings = list(self.readings.get(key_str, []))
                
                recent = [
                    r for r in sensor_readings 
                    if r["timestamp"] >= cutoff
                ]
            
                if recent:
                    concentrations = [r["concentration"] for r in recent]
                    results.append({
                        "sensor_id": meta["sensor_id"],
                        "gas_type": meta["gas_type"],
                        "avg_concentration": sum(concentrations) / len(concentrations),
                        "max_concentration": max(concentrations),
                        "min_concentration": min(concentrations),
                        "x": meta["x"],
                        "y": meta["y"],
                        "area": meta["area"],
                        "threshold": meta["threshold"]
                    })
        
        return sorted(results, key=lambda x: (x["area"], x["x"], x["y"], x["gas_type"]))

    def get_historical_data(self, sensor_id: str, gas_type: str,
                            minutes: int = 10) -> List[Dict]:
        cutoff = int(time.time() * 1000) - minutes * 60 * 1000
        key_str = f"{sensor_id}:{gas_type}"
        
        with self.lock:
            sensor_readings = list(self.readings.get(key_str, []))
        
        recent = [
            r for r in sensor_readings 
            if r["timestamp"] >= cutoff
        ]
        
        window_size = 11
        result = []
        for i, r in enumerate(recent):
            start = max(0, i - 5)
            end = min(len(recent), i + 6)
            window = [x["concentration"] for x in recent[start:end]]
            moving_avg = sum(window) / len(window) if window else r["concentration"]
            
            result.append({
                "timestamp": r["timestamp"],
                "concentration": r["concentration"],
                "moving_avg": moving_avg
            })
        
        return result

    def get_all_sensors(self) -> List[Dict]:
        return sorted(
            [
                {
                    "sensor_id": v["sensor_id"],
                    "gas_type": v["gas_type"],
                    "x": v["x"],
                    "y": v["y"],
                    "area": v["area"],
                    "threshold": v["threshold"],
                    "unit": v["unit"]
                }
                for v in self.metadata.values()
            ],
            key=lambda x: (x["area"], x["x"], x["y"], x["gas_type"])
        )

    def get_gas_types(self) -> List[str]:
        return sorted(list(set(v["gas_type"] for v in self.metadata.values())))

    def get_areas(self) -> List[str]:
        return sorted(list(set(v["area"] for v in self.metadata.values())))


db_client = None


def get_db_client():
    global db_client
    if db_client is None:
        db_client = InMemoryDB()
    return db_client

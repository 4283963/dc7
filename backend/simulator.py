import time
import random
import threading
import logging
from typing import List, Dict
from db import get_db_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GAS_CONFIGS = [
    {"gas_type": "NH3", "threshold": 25.0, "base": 2.0, "variance": 3.0},
    {"gas_type": "SiH4", "threshold": 5.0, "base": 0.5, "variance": 0.8},
    {"gas_type": "HF", "threshold": 3.0, "base": 0.3, "variance": 0.5},
    {"gas_type": "HCl", "threshold": 5.0, "base": 0.4, "variance": 0.6},
    {"gas_type": "PH3", "threshold": 0.3, "base": 0.05, "variance": 0.08},
    {"gas_type": "AsH3", "threshold": 0.05, "base": 0.01, "variance": 0.02},
]

AREAS = ["CLEANROOM_A", "CLEANROOM_B", "ETCH_BAY", "DIFFUSION", "WAFER_FAB"]

GRID_WIDTH = 10
GRID_HEIGHT = 8


def generate_sensor_layout() -> List[Dict]:
    sensors = []
    sensor_idx = 0
    for area_idx, area in enumerate(AREAS):
        x_start = (area_idx % 2) * 5
        y_start = (area_idx // 2) * 4
        for y in range(y_start, min(y_start + 4, GRID_HEIGHT)):
            for x in range(x_start, min(x_start + 5, GRID_WIDTH)):
                for gas_config in GAS_CONFIGS[:3]:
                    sensor_id = f"S{sensor_idx:04d}"
                    sensors.append({
                        "sensor_id": sensor_id,
                        "gas_type": gas_config["gas_type"],
                        "x": x,
                        "y": y,
                        "area": area,
                        "threshold": gas_config["threshold"],
                        "base": gas_config["base"],
                        "variance": gas_config["variance"]
                    })
                    sensor_idx += 1
    return sensors


def init_sensors():
    db = get_db_client()
    sensors = generate_sensor_layout()
    for s in sensors:
        db.upsert_sensor_metadata(
            s["sensor_id"], s["gas_type"], s["x"], s["y"],
            s["area"], s["threshold"]
        )
    logger.info(f"Initialized {len(sensors)} sensor metadata entries")
    return sensors


def generate_reading(sensor: Dict, leak_sensors: set = None) -> Dict:
    base = sensor["base"]
    variance = sensor["variance"]
    
    if leak_sensors and sensor["sensor_id"] in leak_sensors:
        multiplier = random.uniform(1.5, 3.0)
        concentration = base * multiplier + random.gauss(0, variance)
    else:
        concentration = max(0, base + random.gauss(0, variance))
    
    return {
        "sensor_id": sensor["sensor_id"],
        "gas_type": sensor["gas_type"],
        "concentration": round(concentration, 4),
        "x": sensor["x"],
        "y": sensor["y"],
        "area": sensor["area"],
        "timestamp": int(time.time() * 1000)
    }


def simulate_continuous(duration_minutes: int = 60):
    sensors = init_sensors()
    db = get_db_client()
    
    start_time = time.time()
    end_time = start_time + duration_minutes * 60
    
    leak_sensors = set()
    leak_sensor_ids = [s["sensor_id"] for s in sensors if s["gas_type"] == "NH3"][:8]
    
    while time.time() < end_time:
        cycle_start = time.time()
        
        if random.random() < 0.05:
            new_leak = random.choice(leak_sensor_ids)
            leak_sensors.add(new_leak)
            logger.warning(f"⚠️  Simulated leak started at sensor {new_leak}")
        
        if random.random() < 0.02 and leak_sensors:
            removed = leak_sensors.pop()
            logger.info(f"✅  Leak resolved at sensor {removed}")
        
        readings = []
        for sensor in sensors:
            readings.append(generate_reading(sensor, leak_sensors))
        
        db.insert_readings_batch(readings)
        elapsed = time.time() - cycle_start
        sleep_time = max(0, 1.0 - elapsed)
        
        logger.info(
            f"Inserted {len(readings)} readings | "
            f"Active leaks: {len(leak_sensors)} | "
            f"Cycle time: {elapsed:.3f}s"
        )
        
        time.sleep(sleep_time)
    
    logger.info("Simulation complete")


def simulate_backfill(hours: int = 2):
    sensors = init_sensors()
    db = get_db_client()
    
    end_time = int(time.time() * 1000)
    start_time = end_time - hours * 3600 * 1000
    step_ms = 1000
    
    total_points = (end_time - start_time) // step_ms
    logger.info(f"Backfilling {total_points} data points for {hours} hours...")
    
    batch_size = 1000
    batch = []
    count = 0
    
    current_time = start_time
    while current_time < end_time:
        for sensor in sensors:
            concentration = max(0, sensor["base"] + random.gauss(0, sensor["variance"]))
            batch.append({
                "sensor_id": sensor["sensor_id"],
                "gas_type": sensor["gas_type"],
                "concentration": round(concentration, 4),
                "x": sensor["x"],
                "y": sensor["y"],
                "area": sensor["area"],
                "timestamp": current_time
            })
        
        if len(batch) >= batch_size:
            db.insert_readings_batch(batch)
            count += len(batch)
            batch = []
            if count % 10000 == 0:
                progress = ((current_time - start_time) / (end_time - start_time)) * 100
                logger.info(f"Backfill progress: {progress:.1f}% ({count} rows)")
        
        current_time += step_ms
    
    if batch:
        db.insert_readings_batch(batch)
        count += len(batch)
    
    logger.info(f"Backfill complete: {count} rows inserted")


if __name__ == "__main__":
    import sys
    
    mode = sys.argv[1] if len(sys.argv) > 1 else "continuous"
    
    if mode == "backfill":
        hours = int(sys.argv[2]) if len(sys.argv) > 2 else 2
        simulate_backfill(hours)
    elif mode == "continuous":
        duration = int(sys.argv[2]) if len(sys.argv) > 2 else 60
        simulate_continuous(duration)
    else:
        print(f"Unknown mode: {mode}. Use 'backfill' or 'continuous'")
        sys.exit(1)

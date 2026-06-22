import asyncio
import json
import time
import logging
import random
from typing import Optional, List, AsyncGenerator, Dict
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import os
if os.environ.get("USE_MOCK_DB", "false").lower() == "true":
    print("⚠️  Using in-memory database (USE_MOCK_DB=true)")
    from mock_db import get_db_client
else:
    try:
        from db import get_db_client
        _test_db = get_db_client()
        _test_db.client.query("SELECT 1")
        print("✅ Using ClickHouse database")
    except Exception as e:
        print(f"⚠️  ClickHouse not available ({e}), using in-memory database for demo")
        from mock_db import get_db_client

from diffusion_model import get_diffusion_predictor
from models import (
    SensorReading, SensorMetadata, AggregatedSensorData,
    HeatmapResponse, HeatmapCell
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Fab Gas Monitor API", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = None
diffusion = None


async def environment_simulator():
    while True:
        try:
            if diffusion:
                new_dir = diffusion.wind_direction + random.gauss(0, 8)
                new_dir = new_dir % 360
                new_speed = max(0.3, diffusion.wind_speed + random.gauss(0, 0.15))
                new_speed = min(new_speed, 5.0)
                new_temp = diffusion.temperature + random.gauss(0, 0.1)
                new_temp = max(18, min(28, new_temp))
                
                diffusion.update_environment(
                    wind_direction=new_dir,
                    wind_speed=new_speed,
                    temperature=new_temp
                )
        except Exception as e:
            logger.debug(f"Env simulator error: {e}")
        await asyncio.sleep(5)


@app.on_event("startup")
async def startup_event():
    global db, diffusion
    db = get_db_client()
    diffusion = get_diffusion_predictor()
    asyncio.create_task(environment_simulator())
    logger.info("API server started with diffusion prediction module")


class HealthResponse(BaseModel):
    status: str
    timestamp: int
    clickhouse_connected: bool
    diffusion_model_loaded: bool


class EnvironmentParams(BaseModel):
    wind_direction: Optional[float] = None
    wind_speed: Optional[float] = None
    temperature: Optional[float] = None
    humidity: Optional[float] = None


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    try:
        if db:
            db.client.query("SELECT 1")
            connected = True
        else:
            connected = False
    except Exception:
        try:
            if db and hasattr(db, 'get_all_sensors'):
                db.get_all_sensors()
                connected = True
            else:
                connected = False
        except Exception:
            connected = False
    return {
        "status": "healthy",
        "timestamp": int(time.time() * 1000),
        "clickhouse_connected": connected,
        "diffusion_model_loaded": diffusion is not None
    }


@app.get("/api/sensors")
async def get_sensors():
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    return db.get_all_sensors()


@app.get("/api/gas-types")
async def get_gas_types():
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    return db.get_gas_types()


@app.get("/api/areas")
async def get_areas():
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    return db.get_areas()


@app.get("/api/environment")
async def get_environment():
    if not diffusion:
        raise HTTPException(status_code=500, detail="Diffusion model not loaded")
    return diffusion.get_environment()


@app.post("/api/environment")
async def update_environment(params: EnvironmentParams):
    if not diffusion:
        raise HTTPException(status_code=500, detail="Diffusion model not loaded")
    diffusion.update_environment(
        wind_direction=params.wind_direction,
        wind_speed=params.wind_speed,
        temperature=params.temperature,
        humidity=params.humidity
    )
    return {
        "status": "success",
        "environment": diffusion.get_environment(),
        "timestamp": int(time.time() * 1000)
    }


@app.post("/api/simulate-leak")
async def simulate_leak(
    sensor_id: str = Query(..., description="Sensor ID to trigger leak"),
    gas_type: str = Query(..., description="Gas type"),
    intensity: float = Query(2.0, ge=1.5, le=5.0, description="Leak intensity multiplier")
):
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    sensors = db.get_all_sensors()
    target = next((s for s in sensors if s["sensor_id"] == sensor_id and s["gas_type"] == gas_type), None)
    
    if not target:
        raise HTTPException(status_code=404, detail="Sensor not found")
    
    base_concentration = target["threshold"] * intensity
    for i in range(10):
        variation = random.gauss(0, base_concentration * 0.1)
        db.insert_reading(
            sensor_id, gas_type,
            max(0, base_concentration + variation),
            target["x"], target["y"], target["area"]
        )
        time.sleep(0.1)
    
    return {
        "status": "success",
        "message": f"Leak simulated at {sensor_id} ({gas_type})",
        "concentration": base_concentration,
        "timestamp": int(time.time() * 1000)
    }


@app.get("/api/diffusion/predictions")
async def get_diffusion_predictions(
    gas_type: Optional[str] = Query(None, description="Filter by gas type")
):
    if not diffusion:
        raise HTTPException(status_code=500, detail="Diffusion model not loaded")
    
    predictions = diffusion.get_active_predictions()
    if gas_type:
        predictions = [p for p in predictions if p["gas_type"] == gas_type]
    
    return {
        "timestamp": int(time.time() * 1000),
        "count": len(predictions),
        "predictions": predictions
    }


@app.post("/api/reading")
async def add_reading(reading: SensorReading):
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    db.insert_reading(
        reading.sensor_id, reading.gas_type, reading.concentration,
        reading.x, reading.y, reading.area, reading.timestamp
    )
    return {"status": "success", "timestamp": int(time.time() * 1000)}


@app.post("/api/readings/batch")
async def add_readings_batch(readings: List[SensorReading]):
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    db.insert_readings_batch([r.model_dump() for r in readings])
    return {"status": "success", "count": len(readings), "timestamp": int(time.time() * 1000)}


@app.post("/api/sensor/metadata")
async def add_sensor_metadata(metadata: SensorMetadata):
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    db.upsert_sensor_metadata(
        metadata.sensor_id, metadata.gas_type, metadata.x, metadata.y,
        metadata.area, metadata.threshold, metadata.unit
    )
    return {"status": "success"}


@app.get("/api/aggregated")
async def get_aggregated_data(
    window_seconds: int = Query(60, ge=1, le=3600),
    gas_type: Optional[str] = None,
    include_diffusion: bool = Query(True, description="Include diffusion predictions")
):
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    data = db.get_aggregated_data(window_seconds=window_seconds)
    if gas_type:
        data = [d for d in data if d["gas_type"] == gas_type]
    
    predictions = []
    if include_diffusion and diffusion:
        for d in data:
            if d.get("health_status", "healthy") == "healthy":
                pred = diffusion.predict_diffusion(
                    d["sensor_id"], d["gas_type"],
                    d["x"], d["y"],
                    d["avg_concentration"], d["threshold"]
                )
                if pred:
                    predictions.append(pred)
    
    all_predictions = diffusion.get_active_predictions() if diffusion else []
    if gas_type:
        all_predictions = [p for p in all_predictions if p["gas_type"] == gas_type]
    
    return {
        "timestamp": int(time.time() * 1000),
        "window_seconds": window_seconds,
        "data": data,
        "diffusion_predictions": all_predictions,
        "environment": diffusion.get_environment() if diffusion else {}
    }


@app.get("/api/historical/{sensor_id}/{gas_type}")
async def get_historical_data(
    sensor_id: str,
    gas_type: str,
    minutes: int = Query(10, ge=1, le=1440)
):
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    data = db.get_historical_data(sensor_id, gas_type, minutes=minutes)
    return {
        "sensor_id": sensor_id,
        "gas_type": gas_type,
        "minutes": minutes,
        "data": data
    }


@app.get("/api/heatmap")
async def get_heatmap(
    gas_type: str = Query(..., description="Gas type to visualize"),
    window_seconds: int = Query(60, ge=1, le=3600),
    grid_width: int = Query(10, ge=5, le=20),
    grid_height: int = Query(8, ge=4, le=16)
):
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    all_data = db.get_aggregated_data(window_seconds=window_seconds)
    filtered = [d for d in all_data if d["gas_type"] == gas_type]
    
    heatmap_data = []
    for d in filtered:
        heatmap_data.append(HeatmapCell(
            x=d["x"],
            y=d["y"],
            value=d["avg_concentration"],
            sensor_id=d["sensor_id"],
            gas_type=d["gas_type"],
            threshold=d["threshold"],
            area=d["area"]
        ))
    
    areas = list(set(d["area"] for d in filtered))
    
    predictions = diffusion.get_active_predictions() if diffusion else []
    predictions = [p for p in predictions if p["gas_type"] == gas_type]
    
    return HeatmapResponse(
        timestamp=int(time.time() * 1000),
        gas_type=gas_type,
        grid_width=grid_width,
        grid_height=grid_height,
        data=heatmap_data,
        areas=sorted(areas)
    )


async def generate_sse_data(
    gas_type: str,
    window_seconds: int,
    interval: int
) -> AsyncGenerator[str, None]:
    yield f": {json.dumps({'type': 'connected', 'timestamp': int(time.time() * 1000)})}\n\n"
    
    try:
        while True:
            try:
                all_data = db.get_aggregated_data(window_seconds=window_seconds)
                filtered = [d for d in all_data if d["gas_type"] == gas_type]
                
                heatmap_data = []
                new_predictions = []
                for d in filtered:
                    health = d.get("health_status", "healthy")
                    
                    pred = None
                    if health == "healthy" and diffusion:
                        pred = diffusion.predict_diffusion(
                            d["sensor_id"], d["gas_type"],
                            d["x"], d["y"],
                            d["avg_concentration"], d["threshold"]
                        )
                        if pred:
                            new_predictions.append(pred)
                    
                    if health == "faulty":
                        status = "faulty"
                    elif health == "stale":
                        status = "stale"
                    elif d["avg_concentration"] > d["threshold"]:
                        status = "alert"
                    else:
                        status = "normal"
                    
                    heatmap_data.append({
                        "x": d["x"],
                        "y": d["y"],
                        "value": d["avg_concentration"],
                        "max_value": d["max_concentration"],
                        "sensor_id": d["sensor_id"],
                        "gas_type": d["gas_type"],
                        "threshold": d["threshold"],
                        "area": d["area"],
                        "status": status,
                        "health_status": health,
                        "last_seen_ms": d.get("last_seen_ms", 0),
                        "consecutive_zeros": d.get("consecutive_zeros", 0)
                    })
                
                active_predictions = diffusion.get_active_predictions() if diffusion else []
                active_predictions = [p for p in active_predictions if p["gas_type"] == gas_type]
                
                env_data = diffusion.get_environment() if diffusion else {}
                
                response_data = {
                    "type": "heatmap_update",
                    "timestamp": int(time.time() * 1000),
                    "gas_type": gas_type,
                    "window_seconds": window_seconds,
                    "data": heatmap_data,
                    "diffusion_predictions": active_predictions,
                    "environment": env_data
                }
                
                yield f"data: {json.dumps(response_data)}\n\n"
                await asyncio.sleep(interval)
                
            except Exception as e:
                logger.error(f"Error in SSE stream: {e}")
                error_data = {
                    "type": "error",
                    "timestamp": int(time.time() * 1000),
                    "message": str(e)
                }
                yield f"data: {json.dumps(error_data)}\n\n"
                await asyncio.sleep(interval)
                
    except asyncio.CancelledError:
        logger.info("SSE connection closed by client")
        yield f"data: {json.dumps({'type': 'closed', 'timestamp': int(time.time() * 1000)})}\n\n"


@app.get("/api/stream/heatmap")
async def stream_heatmap(
    gas_type: str = Query(..., description="Gas type to visualize"),
    window_seconds: int = Query(60, ge=1, le=3600),
    interval: int = Query(2, ge=1, le=10, description="Push interval in seconds")
):
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    return StreamingResponse(
        generate_sse_data(gas_type, window_seconds, interval),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.get("/api/stream/linechart")
async def stream_linechart(
    sensor_id: str = Query(..., description="Sensor ID"),
    gas_type: str = Query(..., description="Gas type"),
    minutes: int = Query(10, ge=1, le=60),
    interval: int = Query(2, ge=1, le=10)
):
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    async def generate():
        yield f": {json.dumps({'type': 'connected', 'timestamp': int(time.time() * 1000)})}\n\n"
        try:
            while True:
                try:
                    data = db.get_historical_data(sensor_id, gas_type, minutes=minutes)
                    response = {
                        "type": "linechart_update",
                        "timestamp": int(time.time() * 1000),
                        "sensor_id": sensor_id,
                        "gas_type": gas_type,
                        "minutes": minutes,
                        "data": data
                    }
                    yield f"data: {json.dumps(response)}\n\n"
                    await asyncio.sleep(interval)
                except Exception as e:
                    logger.error(f"Error in linechart stream: {e}")
                    yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
                    await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("Linechart SSE connection closed")
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

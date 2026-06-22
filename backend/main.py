import asyncio
import json
import time
import logging
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
from models import (
    SensorReading, SensorMetadata, AggregatedSensorData,
    HeatmapResponse, HeatmapCell
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Fab Gas Monitor API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = None


@app.on_event("startup")
async def startup_event():
    global db
    db = get_db_client()
    logger.info("API server started")


class HealthResponse(BaseModel):
    status: str
    timestamp: int
    clickhouse_connected: bool


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    try:
        if db:
            db.client.query("SELECT 1")
            connected = True
        else:
            connected = False
    except Exception:
        connected = False
    return {
        "status": "healthy",
        "timestamp": int(time.time() * 1000),
        "clickhouse_connected": connected
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
    gas_type: Optional[str] = None
):
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    data = db.get_aggregated_data(window_seconds=window_seconds)
    if gas_type:
        data = [d for d in data if d["gas_type"] == gas_type]
    return {
        "timestamp": int(time.time() * 1000),
        "window_seconds": window_seconds,
        "data": data
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
                for d in filtered:
                    heatmap_data.append({
                        "x": d["x"],
                        "y": d["y"],
                        "value": d["avg_concentration"],
                        "max_value": d["max_concentration"],
                        "sensor_id": d["sensor_id"],
                        "gas_type": d["gas_type"],
                        "threshold": d["threshold"],
                        "area": d["area"],
                        "status": "alert" if d["avg_concentration"] > d["threshold"] else "normal"
                    })
                
                response_data = {
                    "type": "heatmap_update",
                    "timestamp": int(time.time() * 1000),
                    "gas_type": gas_type,
                    "window_seconds": window_seconds,
                    "data": heatmap_data
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

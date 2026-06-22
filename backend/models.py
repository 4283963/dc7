from pydantic import BaseModel
from typing import Optional, List


class SensorReading(BaseModel):
    sensor_id: str
    gas_type: str
    concentration: float
    x: int
    y: int
    area: str
    timestamp: Optional[int] = None


class SensorMetadata(BaseModel):
    sensor_id: str
    gas_type: str
    x: int
    y: int
    area: str
    threshold: float
    unit: str = "PPM"


class AggregatedSensorData(BaseModel):
    sensor_id: str
    gas_type: str
    avg_concentration: float
    max_concentration: float
    min_concentration: float
    x: int
    y: int
    area: str
    threshold: float
    unit: str = "PPM"


class HistoricalDataPoint(BaseModel):
    timestamp: int
    concentration: float
    moving_avg: float


class HeatmapCell(BaseModel):
    x: int
    y: int
    value: float
    sensor_id: str
    gas_type: str
    threshold: float
    area: str


class HeatmapResponse(BaseModel):
    timestamp: int
    gas_type: str
    grid_width: int
    grid_height: int
    data: List[HeatmapCell]
    areas: List[str]

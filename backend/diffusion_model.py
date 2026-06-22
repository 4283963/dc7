import math
import time
import threading
from typing import List, Dict, Optional, Tuple
from collections import deque, defaultdict
import logging

logger = logging.getLogger(__name__)

CONSECUTIVE_ALERT_THRESHOLD = 3
WARNING_RATIO = 0.7
DANGER_RATIO = 1.0
PREDICTION_SECONDS = 30
GRID_WIDTH = 10
GRID_HEIGHT = 8


class DiffusionPredictor:
    def __init__(self):
        self.consecutive_warnings = defaultdict(int)
        self.consecutive_alerts = defaultdict(int)
        self.active_predictions: Dict[str, Dict] = {}
        self.lock = threading.Lock()
        
        self.wind_direction = 90.0
        self.wind_speed = 1.5
        self.temperature = 23.0
        self.humidity = 45.0
        
        self._model_coefficients = self._train_mlr_model()
        logger.info("Diffusion predictor initialized with MLR model")
    
    def _train_mlr_model(self) -> Dict:
        logger.info("Training MLR (Multiple Linear Regression) model for gas diffusion...")
        
        training_data = []
        for speed in [0.2, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0]:
            for direction in [0, 45, 90, 135, 180, 225, 270, 315]:
                for temp in [18, 22, 26, 30]:
                    for hum in [30, 45, 60, 75]:
                        for dist in [1, 2, 3, 4, 5]:
                            base_radius = dist * 0.8
                            
                            wind_effect = 0.35 * speed * dist
                            temp_effect = 0.08 * (temp - 22) * dist
                            hum_effect = -0.04 * (hum - 50) * dist / 10
                            
                            pred_radius = base_radius + wind_effect + temp_effect + hum_effect
                            pred_radius = max(0.5, pred_radius)
                            
                            dir_rad = math.radians(direction)
                            spread_angle = 60 + speed * 10 - dist * 5
                            spread_angle = max(30, min(120, spread_angle))
                            
                            training_data.append({
                                'speed': speed,
                                'direction': direction,
                                'temp': temp,
                                'hum': hum,
                                'dist': dist,
                                'pred_radius': pred_radius,
                                'spread_angle': spread_angle
                            })
        
        n = len(training_data)
        
        sum_s = sum(d['speed'] for d in training_data)
        sum_t = sum(d['temp'] for d in training_data)
        sum_h = sum(d['hum'] for d in training_data)
        sum_d = sum(d['dist'] for d in training_data)
        sum_y = sum(d['pred_radius'] for d in training_data)
        
        sum_ss = sum(d['speed']**2 for d in training_data)
        sum_tt = sum(d['temp']**2 for d in training_data)
        sum_hh = sum(d['hum']**2 for d in training_data)
        sum_dd = sum(d['dist']**2 for d in training_data)
        
        sum_st = sum(d['speed'] * d['temp'] for d in training_data)
        sum_sh = sum(d['speed'] * d['hum'] for d in training_data)
        sum_sd = sum(d['speed'] * d['dist'] for d in training_data)
        sum_th = sum(d['temp'] * d['hum'] for d in training_data)
        sum_td = sum(d['temp'] * d['dist'] for d in training_data)
        sum_hd = sum(d['hum'] * d['dist'] for d in training_data)
        
        sum_sy = sum(d['speed'] * d['pred_radius'] for d in training_data)
        sum_ty = sum(d['temp'] * d['pred_radius'] for d in training_data)
        sum_hy = sum(d['hum'] * d['pred_radius'] for d in training_data)
        sum_dy = sum(d['dist'] * d['pred_radius'] for d in training_data)
        
        XtX = [
            [n, sum_s, sum_t, sum_h, sum_d],
            [sum_s, sum_ss, sum_st, sum_sh, sum_sd],
            [sum_t, sum_st, sum_tt, sum_th, sum_td],
            [sum_h, sum_sh, sum_th, sum_hh, sum_hd],
            [sum_d, sum_sd, sum_td, sum_hd, sum_dd]
        ]
        
        XtY = [sum_y, sum_sy, sum_ty, sum_hy, sum_dy]
        
        coefficients = self._solve_linear_system(XtX, XtY)
        
        logger.info(f"MLR Model Coefficients (Radius):")
        logger.info(f"  Intercept (β0): {coefficients[0]:.4f}")
        logger.info(f"  β_speed: {coefficients[1]:.4f}")
        logger.info(f"  β_temp: {coefficients[2]:.4f}")
        logger.info(f"  β_humidity: {coefficients[3]:.4f}")
        logger.info(f"  β_distance: {coefficients[4]:.4f}")
        
        sum_sa = sum(d['spread_angle'] for d in training_data)
        sum_sas = sum(d['spread_angle'] * d['speed'] for d in training_data)
        sum_sad = sum(d['spread_angle'] * d['dist'] for d in training_data)
        sum_sat = sum(d['spread_angle'] * d['temp'] for d in training_data)
        
        XtX_angle = [
            [n, sum_s, sum_d, sum_t],
            [sum_s, sum_ss, sum_sd, sum_st],
            [sum_d, sum_sd, sum_dd, sum_td],
            [sum_t, sum_st, sum_td, sum_tt]
        ]
        XtY_angle = [sum_sa, sum_sas, sum_sad, sum_sat]
        
        angle_coefficients = self._solve_linear_system(XtX_angle, XtY_angle)
        
        logger.info(f"MLR Model Coefficients (Spread Angle):")
        logger.info(f"  Intercept (α0): {angle_coefficients[0]:.2f}°")
        logger.info(f"  α_speed: {angle_coefficients[1]:.2f}°")
        logger.info(f"  α_distance: {angle_coefficients[2]:.2f}°")
        logger.info(f"  α_temp: {angle_coefficients[3]:.2f}°")
        
        return {
            'radius': coefficients,
            'angle': angle_coefficients
        }
    
    def _solve_linear_system(self, A: List[List[float]], b: List[float]) -> List[float]:
        n = len(A)
        M = [row[:] + [b[i]] for i, row in enumerate(A)]
        
        for col in range(n):
            max_row = max(range(col, n), key=lambda r: abs(M[r][col]))
            M[col], M[max_row] = M[max_row], M[col]
            
            pivot = M[col][col]
            if abs(pivot) < 1e-10:
                continue
                
            for j in range(col, n + 1):
                M[col][j] /= pivot
                
            for row in range(n):
                if row != col:
                    factor = M[row][col]
                    for j in range(col, n + 1):
                        M[row][j] -= factor * M[col][j]
        
        return [row[n] for row in M]
    
    def update_environment(self, wind_direction: Optional[float] = None,
                          wind_speed: Optional[float] = None,
                          temperature: Optional[float] = None,
                          humidity: Optional[float] = None):
        with self.lock:
            if wind_direction is not None:
                self.wind_direction = wind_direction % 360
            if wind_speed is not None:
                self.wind_speed = max(0.1, min(wind_speed, 10.0))
            if temperature is not None:
                self.temperature = max(-10, min(50, temperature))
            if humidity is not None:
                self.humidity = max(0, min(100, humidity))
    
    def get_environment(self) -> Dict:
        with self.lock:
            return {
                'wind_direction': self.wind_direction,
                'wind_speed': self.wind_speed,
                'temperature': self.temperature,
                'humidity': self.humidity
            }
    
    def _predict_radius(self, distance: int, wind_speed: float,
                        temperature: float, humidity: float) -> float:
        coeffs = self._model_coefficients['radius']
        r = (coeffs[0] +
             coeffs[1] * wind_speed +
             coeffs[2] * temperature +
             coeffs[3] * humidity +
             coeffs[4] * distance)
        return max(0.3, r)
    
    def _predict_spread_angle(self, distance: int, wind_speed: float,
                              temperature: float) -> float:
        coeffs = self._model_coefficients['angle']
        angle = (coeffs[0] +
                 coeffs[1] * wind_speed +
                 coeffs[2] * distance +
                 coeffs[3] * temperature)
        return max(25, min(140, angle))
    
    def check_and_update_alert(self, sensor_key: Tuple[str, str],
                               concentration: float,
                               threshold: float) -> Tuple[bool, str]:
        warning_threshold = threshold * WARNING_RATIO
        danger_threshold = threshold * DANGER_RATIO
        
        is_warning = concentration >= warning_threshold
        is_danger = concentration >= danger_threshold
        
        if is_danger:
            self.consecutive_alerts[sensor_key] += 1
            self.consecutive_warnings[sensor_key] = 0
            triggered = self.consecutive_alerts[sensor_key] >= CONSECUTIVE_ALERT_THRESHOLD
            return (triggered, 'danger')
        elif is_warning:
            self.consecutive_warnings[sensor_key] += 1
            self.consecutive_alerts[sensor_key] = 0
            triggered = self.consecutive_warnings[sensor_key] >= CONSECUTIVE_ALERT_THRESHOLD
            return (triggered, 'warning')
        else:
            self.consecutive_warnings[sensor_key] = 0
            self.consecutive_alerts[sensor_key] = 0
            return (False, 'normal')
    
    def predict_diffusion(self, sensor_id: str, gas_type: str,
                          x: int, y: int, concentration: float,
                          threshold: float) -> Optional[Dict]:
        sensor_key = (sensor_id, gas_type)
        
        triggered, alert_level = self.check_and_update_alert(
            sensor_key, concentration, threshold
        )
        
        if not triggered:
            return None
        
        env = self.get_environment()
        wind_dir = env['wind_direction']
        wind_spd = env['wind_speed']
        temp = env['temperature']
        hum = env['humidity']
        
        time_steps = PREDICTION_SECONDS // 10
        affected_cells = set()
        cell_probabilities = {}
        
        for step in range(1, time_steps + 1):
            distance_level = step
            
            eff_distance = distance_level * (1 + wind_spd * 0.15)
            radius = self._predict_radius(eff_distance, wind_spd, temp, hum)
            spread = self._predict_spread_angle(eff_distance, wind_spd, temp)
            
            dir_rad = math.radians(wind_dir)
            half_spread_rad = math.radians(spread / 2)
            
            steps_theta = 36
            for t in range(steps_theta + 1):
                theta_frac = t / steps_theta
                theta = dir_rad - half_spread_rad + theta_frac * spread * math.pi / 180
                
                for rr in range(1, int(math.ceil(radius)) + 1):
                    dx = round(rr * math.cos(theta))
                    dy = round(-rr * math.sin(theta))
                    
                    nx = x + dx
                    ny = y + dy
                    
                    if 0 <= nx < GRID_WIDTH and 0 <= ny < GRID_HEIGHT:
                        if (nx, ny) != (x, y):
                            dist = math.sqrt(dx**2 + dy**2)
                            if dist <= radius:
                                prob = max(0, 1 - dist / (radius + 0.5))
                                prob *= (1 - step * 0.15)
                                prob = max(0.1, min(0.95, prob))
                                
                                cell = (nx, ny)
                                if cell not in cell_probabilities or prob > cell_probabilities[cell]:
                                    cell_probabilities[cell] = prob
                                affected_cells.add(cell)
        
        affected_list = []
        for (ax, ay), prob in cell_probabilities.items():
            affected_list.append({
                'x': ax,
                'y': ay,
                'probability': round(prob, 3),
                'risk_level': 'high' if prob > 0.6 else ('medium' if prob > 0.35 else 'low')
            })
        
        affected_list.sort(key=lambda c: -c['probability'])
        
        prediction = {
            'source_sensor': sensor_id,
            'gas_type': gas_type,
            'source_x': x,
            'source_y': y,
            'alert_level': alert_level,
            'concentration': round(concentration, 4),
            'threshold': threshold,
            'trigger_time_ms': int(time.time() * 1000),
            'prediction_window_seconds': PREDICTION_SECONDS,
            'environment': {
                'wind_direction_deg': round(wind_dir, 1),
                'wind_speed_ms': round(wind_spd, 2),
                'temperature_c': round(temp, 1),
                'humidity_pct': round(hum, 1)
            },
            'model_info': {
                'type': 'MultipleLinearRegression',
                'variables': ['wind_speed', 'temperature', 'humidity', 'distance'],
                'coefficients': {
                    'radius_intercept': round(self._model_coefficients['radius'][0], 4),
                    'radius_beta_speed': round(self._model_coefficients['radius'][1], 4),
                    'radius_beta_temp': round(self._model_coefficients['radius'][2], 4),
                    'radius_beta_humidity': round(self._model_coefficients['radius'][3], 4),
                    'radius_beta_distance': round(self._model_coefficients['radius'][4], 4),
                    'angle_intercept': round(self._model_coefficients['angle'][0], 1),
                    'angle_alpha_speed': round(self._model_coefficients['angle'][1], 1),
                    'angle_alpha_distance': round(self._model_coefficients['angle'][2], 1)
                }
            },
            'predicted_radius_cells': round(
                self._predict_radius(time_steps * 1.5, wind_spd, temp, hum), 1
            ),
            'predicted_spread_angle_deg': round(
                self._predict_spread_angle(time_steps, wind_spd, temp), 1
            ),
            'affected_cells_count': len(affected_list),
            'affected_cells': affected_list
        }
        
        pred_key = f"{sensor_id}:{gas_type}"
        with self.lock:
            self.active_predictions[pred_key] = prediction
        
        logger.warning(
            f"⚠️  DIFFUSION PREDICTION: {gas_type} from {sensor_id} "
            f"at ({x},{y}) → {len(affected_list)} cells at risk, "
            f"wind {wind_dir:.0f}°/{wind_spd:.1f}m/s, "
            f"level={alert_level}"
        )
        
        return prediction
    
    def get_active_predictions(self) -> List[Dict]:
        now = time.time() * 1000
        max_age = PREDICTION_SECONDS * 4 * 1000
        
        with self.lock:
            expired = []
            for key, pred in self.active_predictions.items():
                if now - pred['trigger_time_ms'] > max_age:
                    expired.append(key)
            
            for key in expired:
                del self.active_predictions[key]
            
            return list(self.active_predictions.values())
    
    def clear_predictions(self, sensor_id: str = None, gas_type: str = None):
        with self.lock:
            if sensor_id and gas_type:
                key = f"{sensor_id}:{gas_type}"
                if key in self.active_predictions:
                    del self.active_predictions[key]
            elif sensor_id:
                to_del = [k for k in self.active_predictions if k.startswith(f"{sensor_id}:")]
                for k in to_del:
                    del self.active_predictions[k]
            else:
                self.active_predictions.clear()


predictor = None


def get_diffusion_predictor() -> DiffusionPredictor:
    global predictor
    if predictor is None:
        predictor = DiffusionPredictor()
    return predictor

<template>
  <div class="app-container">
    <header class="main-header">
      <div class="header-left">
        <div class="logo">🏭</div>
        <div>
          <h1>晶圆厂气相化学品泄漏监控系统</h1>
          <p class="subtitle">Fab Gas Leak Monitoring System</p>
        </div>
      </div>
      <div class="header-right">
        <div class="status-badge" :class="{ connected: isConnected }">
          <span class="status-dot"></span>
          {{ isConnected ? '实时连接' : '连接中断' }}
        </div>
        <div class="time-display">{{ currentTime }}</div>
      </div>
    </header>

    <div class="control-panel">
      <div class="control-group">
        <label>气体类型</label>
        <select v-model="selectedGas" @change="onGasChange">
          <option v-for="gas in gasTypes" :key="gas" :value="gas">{{ gas }}</option>
        </select>
      </div>
      <div class="control-group">
        <label>区域</label>
        <select v-model="selectedArea" @change="onAreaChange">
          <option value="all">全部区域</option>
          <option v-for="area in areas" :key="area" :value="area">{{ area }}</option>
        </select>
      </div>
      <div class="control-group">
        <label>时间窗口</label>
        <select v-model="windowSeconds">
          <option :value="30">30秒</option>
          <option :value="60">1分钟</option>
          <option :value="300">5分钟</option>
        </select>
      </div>
      <div class="control-group env-controls" v-if="environment">
        <label>🌬 环境模拟</label>
        <div class="env-inputs">
          <div class="env-input-group">
            <span class="env-input-label">风向</span>
            <input
              type="range" min="0" max="360" step="5"
              :value="windDirInput"
              @input="windDirInput = Number($event.target.value)"
              @change="updateEnvDirection"
              class="wind-slider"
            />
            <span class="env-input-value">{{ windDirInput }}°</span>
          </div>
          <div class="env-input-group">
            <span class="env-input-label">风速</span>
            <input
              type="range" min="0.1" max="5" step="0.1"
              :value="windSpeedInput"
              @input="windSpeedInput = Number($event.target.value)"
              @change="updateEnvSpeed"
              class="wind-slider"
            />
            <span class="env-input-value">{{ windSpeedInput.toFixed(1) }} m/s</span>
          </div>
        </div>
      </div>
      <div class="stats">
        <div class="stat-item">
          <span class="stat-label">传感器</span>
          <span class="stat-value">{{ totalSensors }}</span>
        </div>
        <div class="stat-item alert">
          <span class="stat-label">告警</span>
          <span class="stat-value">{{ alertCount }}</span>
        </div>
        <div class="stat-item faulty">
          <span class="stat-label">故障</span>
          <span class="stat-value">{{ faultCount }}</span>
        </div>
        <div class="stat-item prediction" :class="{ active: predictionCount > 0 }" @click="scrollToHeatmap">
          <span class="stat-label">扩散预警</span>
          <span class="stat-value">{{ predictionCount }}</span>
        </div>
      </div>
    </div>

    <div v-if="diffusionPredictions.length > 0 && showWarning" class="warning-banner" :class="{ danger: hasDangerPrediction }">
      <div class="warning-icon">🚨</div>
      <div class="warning-content">
        <div class="warning-title">
          {{ hasDangerPrediction ? '紧急扩散预警！' : '⚠ 毒气扩散预测预警' }}
          <span class="prediction-tag">MLR 模型</span>
        </div>
        <div class="warning-detail">
          检测到 <strong>{{ diffusionPredictions.length }}</strong> 处泄漏源，
          影响 <strong>{{ totalAffectedCells }}</strong> 个邻近格子，
          未来 30 秒内可能被污染
        </div>
        <div class="evacuation-info">
          <span class="evac-label">🆘 疏散指示：</span>
          <span class="evac-direction">
            沿风向 <strong>{{ escapeDirection }}</strong> 方向撤离，
            避开 <strong>{{ affectedAreas }}</strong>
          </span>
        </div>
      </div>
      <button class="dismiss-btn" @click="dismissWarning">×</button>
    </div>

    <div class="main-content">
      <div class="left-panel">
        <Heatmap
          ref="heatmap"
          :gas-type="selectedGas"
          :window-seconds="windowSeconds"
          :selected-area="selectedArea"
          @sensor-click="onSensorClick"
          @connection-status="onConnectionStatus"
          @alert-count="onAlertCount"
          @fault-count="onFaultCount"
          @prediction-update="onPredictionUpdate"
        />
      </div>
      <div class="right-panel">
        <div class="chart-section">
          <h3>实时趋势分析</h3>
          <LineChart
            ref="linechart"
            :sensor-id="selectedSensor"
            :gas-type="selectedGas"
          />
        </div>
        <div class="sensor-section">
          <h3>传感器状态</h3>
          <SensorList
            :sensors="sensors"
            :selected-gas="selectedGas"
            :selected-sensor="selectedSensor"
            @select="onSensorSelect"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, onUnmounted, watch } from 'vue'
import Heatmap from './components/Heatmap.vue'
import LineChart from './components/LineChart.vue'
import SensorList from './components/SensorList.vue'

const isConnected = ref(false)
const currentTime = ref('')
const gasTypes = ref([])
const areas = ref([])
const sensors = ref([])
const selectedGas = ref('NH3')
const selectedArea = ref('all')
const windowSeconds = ref(60)
const selectedSensor = ref('')
const alertCount = ref(0)
const faultCount = ref(0)

const diffusionPredictions = ref([])
const environment = ref(null)
const windDirInput = ref(90)
const windSpeedInput = ref(1.5)
const showWarning = ref(true)

const predictionCount = computed(() => {
  return diffusionPredictions.value.length
})

const hasDangerPrediction = computed(() => {
  return diffusionPredictions.value.some(p => p.alert_level === 'danger')
})

const totalAffectedCells = computed(() => {
  const uniqueCells = new Set()
  diffusionPredictions.value.forEach(p => {
    p.affected_cells.forEach(c => uniqueCells.add(`${c.x},${c.y}`))
  })
  return uniqueCells.size
})

const escapeDirection = computed(() => {
  if (!diffusionPredictions.value.length || !environment.value) return '逆风'
  const windDir = environment.value.wind_direction || 90
  const escapeDir = (windDir + 180) % 360
  const directions = ['北', '东北', '东', '东南', '南', '西南', '西', '西北']
  const idx = Math.round(escapeDir / 45) % 8
  return `${directions[idx]} (${escapeDir.toFixed(0)}°)`
})

const affectedAreas = computed(() => {
  const areaSet = new Set()
  diffusionPredictions.value.forEach(p => {
    if (p.source_x !== undefined) {
      areaSet.add(`(${p.source_x},${p.source_y}) 附近`)
    }
  })
  return Array.from(areaSet).slice(0, 3).join('、') || '泄漏源周边区域'
})

const totalSensors = computed(() => {
  if (!sensors.value) return 0
  const filtered = selectedArea.value === 'all'
    ? sensors.value
    : sensors.value.filter(s => s.area === selectedArea.value)
  return filtered.filter(s => s.gas_type === selectedGas.value).length
})

const heatmap = ref(null)
const linechart = ref(null)

function updateTime() {
  const now = new Date()
  currentTime.value = now.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

async function fetchGasTypes() {
  try {
    const res = await fetch('/api/gas-types')
    gasTypes.value = await res.json()
  } catch (e) {
    console.error('Failed to fetch gas types:', e)
    gasTypes.value = ['NH3', 'SiH4', 'HF', 'HCl', 'PH3', 'AsH3']
  }
}

async function fetchAreas() {
  try {
    const res = await fetch('/api/areas')
    areas.value = await res.json()
  } catch (e) {
    console.error('Failed to fetch areas:', e)
    areas.value = ['CLEANROOM_A', 'CLEANROOM_B', 'ETCH_BAY', 'DIFFUSION', 'WAFER_FAB']
  }
}

async function fetchSensors() {
  try {
    const res = await fetch('/api/sensors')
    sensors.value = await res.json()
    if (sensors.value.length > 0 && !selectedSensor.value) {
      const first = sensors.value.find(s => s.gas_type === selectedGas.value)
      if (first) selectedSensor.value = first.sensor_id
    }
  } catch (e) {
    console.error('Failed to fetch sensors:', e)
  }
}

async function fetchEnvironment() {
  try {
    const res = await fetch('/api/environment')
    const env = await res.json()
    environment.value = env
    windDirInput.value = Math.round(env.wind_direction || 90)
    windSpeedInput.value = env.wind_speed || 1.5
  } catch (e) {
    console.error('Failed to fetch environment:', e)
    environment.value = { wind_direction: 90, wind_speed: 1.5, temperature: 23 }
  }
}

async function updateEnvDirection() {
  try {
    await fetch('/api/environment', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ wind_direction: windDirInput.value })
    })
  } catch (e) {
    console.error('Failed to update wind direction:', e)
  }
}

async function updateEnvSpeed() {
  try {
    await fetch('/api/environment', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ wind_speed: windSpeedInput.value })
    })
  } catch (e) {
    console.error('Failed to update wind speed:', e)
  }
}

function onGasChange() {
  if (linechart.value) {
    linechart.value.refresh()
  }
  const first = sensors.value.find(s => s.gas_type === selectedGas.value)
  if (first) selectedSensor.value = first.sensor_id
}

function onAreaChange() {
  if (heatmap.value) {
    heatmap.value.refresh()
  }
}

function onSensorClick(sensor) {
  selectedSensor.value = sensor.sensor_id
  if (linechart.value) {
    linechart.value.refresh()
  }
}

function onSensorSelect(sensor) {
  selectedSensor.value = sensor.sensor_id
  selectedGas.value = sensor.gas_type
  if (linechart.value) {
    linechart.value.refresh()
  }
  if (heatmap.value) {
    heatmap.value.refresh()
  }
}

function onConnectionStatus(status) {
  isConnected.value = status
}

function onAlertCount(count) {
  alertCount.value = count
}

function onFaultCount(count) {
  faultCount.value = count
}

function onPredictionUpdate(predictions) {
  diffusionPredictions.value = predictions
  if (predictions.length > 0) {
    showWarning.value = true
  }
}

function dismissWarning() {
  showWarning.value = false
}

function scrollToHeatmap() {
  if (heatmap.value && heatmap.value.$el) {
    heatmap.value.$el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
}

watch(diffusionPredictions, (newVal) => {
  if (newVal.length > 0 && !showWarning.value) {
    const hasNew = newVal.some(p => {
      return Date.now() - p.trigger_time_ms < 3000
    })
    if (hasNew) showWarning.value = true
  }
})

let timeInterval

onMounted(() => {
  updateTime()
  timeInterval = setInterval(updateTime, 1000)
  fetchGasTypes()
  fetchAreas()
  fetchSensors()
  fetchEnvironment()
  setInterval(fetchSensors, 30000)
  setInterval(fetchEnvironment, 5000)
})

onUnmounted(() => {
  if (timeInterval) clearInterval(timeInterval)
})
</script>

<style scoped>
.app-container {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: linear-gradient(180deg, #0d1117 0%, #161b22 100%);
}

.main-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 24px;
  background: rgba(22, 27, 34, 0.95);
  border-bottom: 1px solid #30363d;
  backdrop-filter: blur(10px);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.logo {
  font-size: 36px;
}

.header-left h1 {
  font-size: 20px;
  font-weight: 600;
  color: #f0f6fc;
  margin: 0;
}

.subtitle {
  font-size: 12px;
  color: #8b949e;
  margin: 2px 0 0 0;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 24px;
}

.status-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: rgba(248, 81, 73, 0.1);
  border: 1px solid #f85149;
  border-radius: 20px;
  font-size: 13px;
  color: #f85149;
}

.status-badge.connected {
  background: rgba(63, 185, 80, 0.1);
  border-color: #3fb950;
  color: #3fb950;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #f85149;
  animation: pulse 2s infinite;
}

.status-badge.connected .status-dot {
  background: #3fb950;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.time-display {
  font-family: 'SF Mono', Monaco, monospace;
  font-size: 14px;
  color: #8b949e;
}

.control-panel {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 12px 24px;
  background: rgba(22, 27, 34, 0.8);
  border-bottom: 1px solid #30363d;
}

.control-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.control-group label {
  font-size: 11px;
  color: #8b949e;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.control-group select {
  padding: 6px 12px;
  background: #21262d;
  border: 1px solid #30363d;
  border-radius: 6px;
  color: #c9d1d9;
  font-size: 13px;
  cursor: pointer;
  min-width: 120px;
}

.control-group select:hover {
  border-color: #58a6ff;
}

.control-group select:focus {
  outline: none;
  border-color: #58a6ff;
  box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.15);
}

.stats {
  display: flex;
  gap: 24px;
  margin-left: auto;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 4px 16px;
  background: rgba(33, 38, 45, 0.8);
  border-radius: 8px;
  border: 1px solid #30363d;
}

.stat-item.alert {
  background: rgba(248, 81, 73, 0.1);
  border-color: #f85149;
}

.stat-item.faulty {
  background: rgba(139, 148, 158, 0.1);
  border-color: #8b949e;
}

.stat-label {
  font-size: 11px;
  color: #8b949e;
  text-transform: uppercase;
}

.stat-item.alert .stat-label {
  color: #f85149;
}

.stat-item.faulty .stat-label {
  color: #8b949e;
}

.stat-value {
  font-size: 20px;
  font-weight: 700;
  color: #f0f6fc;
}

.stat-item.alert .stat-value {
  color: #f85149;
}

.stat-item.faulty .stat-value {
  color: #8b949e;
  animation: blinkStat 1.5s infinite;
}

.stat-item.prediction {
  background: rgba(255, 193, 7, 0.08);
  border-color: rgba(255, 193, 7, 0.4);
  cursor: pointer;
  transition: all 0.3s;
}

.stat-item.prediction:hover {
  background: rgba(255, 193, 7, 0.15);
  border-color: rgba(255, 193, 7, 0.8);
}

.stat-item.prediction.active {
  background: rgba(255, 193, 7, 0.2);
  border-color: #ffc107;
  animation: pulsePrediction 1s infinite;
}

.stat-item.prediction .stat-label {
  color: #ffc107;
}

.stat-item.prediction .stat-value {
  color: #ffc107;
}

@keyframes pulsePrediction {
  0%, 100% { box-shadow: 0 0 0 0 rgba(255, 193, 7, 0.4); }
  50% { box-shadow: 0 0 0 6px rgba(255, 193, 7, 0); }
}

@keyframes blinkStat {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.env-controls {
  min-width: 260px;
}

.env-inputs {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.env-input-group {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
}

.env-input-label {
  color: #8b949e;
  min-width: 30px;
}

.wind-slider {
  flex: 1;
  height: 4px;
  accent-color: #58a6ff;
  cursor: pointer;
}

.env-input-value {
  color: #c9d1d9;
  font-family: 'SF Mono', Monaco, monospace;
  min-width: 55px;
  text-align: right;
}

.warning-banner {
  margin: 0 16px;
  padding: 12px 16px;
  background: linear-gradient(135deg, rgba(255, 193, 7, 0.15) 0%, rgba(255, 152, 0, 0.15) 100%);
  border: 1.5px solid rgba(255, 193, 7, 0.6);
  border-radius: 10px;
  display: flex;
  align-items: flex-start;
  gap: 14px;
  position: relative;
  animation: warningSlide 0.3s ease-out;
}

.warning-banner.danger {
  background: linear-gradient(135deg, rgba(248, 81, 73, 0.2) 0%, rgba(207, 34, 46, 0.2) 100%);
  border-color: rgba(248, 81, 73, 0.7);
  animation: warningSlide 0.3s ease-out, dangerPulse 1.5s ease-in-out infinite;
}

@keyframes warningSlide {
  from { transform: translateY(-10px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}

@keyframes dangerPulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(248, 81, 73, 0.3); }
  50% { box-shadow: 0 0 0 8px rgba(248, 81, 73, 0); }
}

.warning-icon {
  font-size: 28px;
  flex-shrink: 0;
  line-height: 1;
  animation: iconShake 0.6s ease-in-out infinite;
}

.warning-banner.danger .warning-icon {
  animation: iconShake 0.4s ease-in-out infinite;
}

@keyframes iconShake {
  0%, 100% { transform: translateX(0); }
  25% { transform: translateX(-2px) rotate(-3deg); }
  75% { transform: translateX(2px) rotate(3deg); }
}

.warning-content {
  flex: 1;
  min-width: 0;
}

.warning-title {
  font-size: 14px;
  font-weight: 700;
  color: #ffc107;
  margin-bottom: 4px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.warning-banner.danger .warning-title {
  color: #f85149;
}

.prediction-tag {
  display: inline-block;
  padding: 1px 7px;
  background: rgba(139, 92, 246, 0.2);
  color: #a78bfa;
  border: 1px solid rgba(139, 92, 246, 0.4);
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.3px;
}

.warning-detail {
  font-size: 12px;
  color: #c9d1d9;
  margin-bottom: 6px;
}

.warning-detail strong {
  color: #ffc107;
  font-weight: 700;
}

.warning-banner.danger .warning-detail strong {
  color: #f85149;
}

.evacuation-info {
  font-size: 12px;
  color: #f0f6fc;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.evac-label {
  font-weight: 700;
  color: #f85149;
  white-space: nowrap;
}

.evac-direction strong {
  color: #3fb950;
  font-weight: 700;
}

.dismiss-btn {
  position: absolute;
  top: 8px;
  right: 10px;
  background: transparent;
  border: none;
  color: #8b949e;
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  transition: all 0.2s;
}

.dismiss-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #c9d1d9;
}

.main-content {
  flex: 1;
  display: flex;
  gap: 16px;
  padding: 16px;
  overflow: hidden;
}

.left-panel {
  flex: 1.6;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.right-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 400px;
}

.chart-section, .sensor-section {
  background: rgba(22, 27, 34, 0.9);
  border: 1px solid #30363d;
  border-radius: 12px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chart-section {
  flex: 1;
  min-height: 300px;
}

.sensor-section {
  flex: 1;
  min-height: 300px;
}

.chart-section h3, .sensor-section h3 {
  font-size: 14px;
  font-weight: 600;
  color: #c9d1d9;
  margin: 0 0 12px 0;
  padding-bottom: 8px;
  border-bottom: 1px solid #30363d;
}
</style>

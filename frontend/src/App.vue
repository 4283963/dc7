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
      <div class="stats">
        <div class="stat-item">
          <span class="stat-label">传感器</span>
          <span class="stat-value">{{ totalSensors }}</span>
        </div>
        <div class="stat-item alert">
          <span class="stat-label">告警</span>
          <span class="stat-value">{{ alertCount }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">更新频率</span>
          <span class="stat-value">2s</span>
        </div>
      </div>
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
import { ref, onMounted, computed, onUnmounted } from 'vue'
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

let timeInterval

onMounted(() => {
  updateTime()
  timeInterval = setInterval(updateTime, 1000)
  fetchGasTypes()
  fetchAreas()
  fetchSensors()
  setInterval(fetchSensors, 30000)
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

.stat-label {
  font-size: 11px;
  color: #8b949e;
  text-transform: uppercase;
}

.stat-item.alert .stat-label {
  color: #f85149;
}

.stat-value {
  font-size: 20px;
  font-weight: 700;
  color: #f0f6fc;
}

.stat-item.alert .stat-value {
  color: #f85149;
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

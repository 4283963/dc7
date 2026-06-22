<template>
  <div class="sensor-list-container">
    <div class="filter-bar">
      <input
        v-model="searchQuery"
        type="text"
        placeholder="搜索传感器ID..."
        class="search-input"
      />
      <div class="filter-btns">
        <button
          @click="filterStatus = 'all'"
          :class="{ active: filterStatus === 'all' }"
        >
          全部
        </button>
        <button
          @click="filterStatus = 'fault'"
          :class="{ active: filterStatus === 'fault' }"
          class="fault-btn"
        >
          故障
        </button>
        <button
          @click="filterStatus = 'alert'"
          :class="{ active: filterStatus === 'alert' }"
        >
          告警
        </button>
        <button
          @click="filterStatus = 'normal'"
          :class="{ active: filterStatus === 'normal' }"
        >
          正常
        </button>
      </div>
    </div>
    
    <div class="sensor-grid" ref="gridRef">
      <div
        v-for="sensor in filteredSensors"
        :key="`${sensor.sensor_id}-${sensor.gas_type}`"
        class="sensor-card"
        :class="{
          active: selectedSensor === sensor.sensor_id && selectedGas === sensor.gas_type,
          alert: isSensorAlert(sensor),
          warning: isSensorWarning(sensor),
          faulty: isSensorFaulty(sensor),
          stale: isSensorStale(sensor)
        }"
        @click="$emit('select', sensor)"
      >
        <div class="sensor-header">
          <span class="sensor-id">{{ sensor.sensor_id }}</span>
          <span class="status-dot" :class="getStatusClass(sensor)"></span>
        </div>
        <div class="sensor-body">
          <div class="gas-tag">{{ sensor.gas_type }}</div>
          <div class="sensor-location">
            <span class="area">{{ sensor.area }}</span>
            <span class="coord">({{ sensor.x }}, {{ sensor.y }})</span>
          </div>
          <div class="concentration" v-if="isSensorFaulty(sensor)">
            <span class="value faulty">故障</span>
            <span class="fault-hint">数据不可信</span>
          </div>
          <div class="concentration" v-else-if="isSensorStale(sensor)">
            <span class="value stale">断连</span>
            <span class="stale-hint">数据过期</span>
          </div>
          <div class="concentration" v-else-if="getConcentration(sensor) !== null">
            <span class="value" :class="{ alert: isSensorAlert(sensor) }">
              {{ getConcentration(sensor).toFixed(3) }}
            </span>
            <span class="unit">PPM</span>
            <span class="threshold">/ {{ sensor.threshold }}</span>
          </div>
          <div class="concentration" v-else>
            <span class="value loading">--</span>
            <span class="unit">PPM</span>
          </div>
        </div>
        <div class="sensor-progress">
          <div
            class="progress-bar"
            :style="{ width: getProgressPercent(sensor) + '%' }"
            :class="getProgressClass(sensor)"
          ></div>
        </div>
        <div v-if="isSensorFaulty(sensor) || isSensorStale(sensor)" class="fault-badge">
          <span class="fault-icon">⚠</span>
          {{ isSensorFaulty(sensor) ? '硬件故障' : '通讯中断' }}
        </div>
      </div>
    </div>
    
    <div class="empty-state" v-if="filteredSensors.length === 0">
      <p>没有找到匹配的传感器</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  sensors: { type: Array, default: () => [] },
  selectedGas: { type: String, default: 'NH3' },
  selectedSensor: { type: String, default: '' }
})

defineEmits(['select'])

const searchQuery = ref('')
const filterStatus = ref('all')
const sensorData = ref({})
const gridRef = ref(null)

let eventSource = null

const filteredSensors = computed(() => {
  let result = props.sensors.filter(s => s.gas_type === props.selectedGas)
  
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    result = result.filter(s =>
      s.sensor_id.toLowerCase().includes(q) ||
      s.area.toLowerCase().includes(q)
    )
  }
  
  if (filterStatus.value === 'fault') {
    result = result.filter(s => isSensorFaulty(s) || isSensorStale(s))
  } else if (filterStatus.value === 'alert') {
    result = result.filter(s => isSensorAlert(s) && !isSensorFaulty(s) && !isSensorStale(s))
  } else if (filterStatus.value === 'normal') {
    result = result.filter(s => !isSensorAlert(s) && !isSensorWarning(s) && !isSensorFaulty(s) && !isSensorStale(s))
  }
  
  return result
})

function getSensorData(sensor) {
  const key = `${sensor.sensor_id}-${sensor.gas_type}`
  return sensorData.value[key] || null
}

function getConcentration(sensor) {
  const data = getSensorData(sensor)
  return data ? data.value : null
}

function isSensorFaulty(sensor) {
  const data = getSensorData(sensor)
  return data && data.health_status === 'faulty'
}

function isSensorStale(sensor) {
  const data = getSensorData(sensor)
  return data && data.health_status === 'stale'
}

function isSensorAlert(sensor) {
  const conc = getConcentration(sensor)
  if (conc === null) return false
  if (isSensorFaulty(sensor) || isSensorStale(sensor)) return false
  return conc > sensor.threshold
}

function isSensorWarning(sensor) {
  const conc = getConcentration(sensor)
  if (conc === null) return false
  if (isSensorFaulty(sensor) || isSensorStale(sensor)) return false
  return conc > sensor.threshold * 0.7 && conc <= sensor.threshold
}

function getStatusClass(sensor) {
  if (isSensorFaulty(sensor)) return 'faulty'
  if (isSensorStale(sensor)) return 'stale'
  if (isSensorAlert(sensor)) return 'alert'
  if (isSensorWarning(sensor)) return 'warning'
  return 'normal'
}

function getProgressPercent(sensor) {
  if (isSensorFaulty(sensor) || isSensorStale(sensor)) return 100
  const conc = getConcentration(sensor)
  if (conc === null) return 0
  return Math.min((conc / sensor.threshold) * 100, 100)
}

function getProgressClass(sensor) {
  if (isSensorFaulty(sensor)) return 'faulty'
  if (isSensorStale(sensor)) return 'stale'
  if (isSensorAlert(sensor)) return 'alert'
  if (isSensorWarning(sensor)) return 'warning'
  return 'normal'
}

function connectSSE() {
  if (eventSource) {
    eventSource.close()
  }
  
  const url = `/api/stream/heatmap?gas_type=${props.selectedGas}&window_seconds=60&interval=2`
  eventSource = new EventSource(url)
  
  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.type === 'heatmap_update') {
        const newData = {}
        data.data.forEach(d => {
          const key = `${d.sensor_id}-${d.gas_type}`
          newData[key] = d
        })
        sensorData.value = newData
      }
    } catch (e) {
      console.error('Failed to parse SSE message for sensor list:', e)
    }
  }
}

watch(() => props.selectedGas, () => {
  sensorData.value = {}
  connectSSE()
})

onMounted(() => {
  connectSSE()
})

onUnmounted(() => {
  if (eventSource) {
    eventSource.close()
  }
})
</script>

<style scoped>
.sensor-list-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.filter-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
  flex-shrink: 0;
}

.search-input {
  flex: 1;
  padding: 6px 12px;
  background: #21262d;
  border: 1px solid #30363d;
  border-radius: 6px;
  color: #c9d1d9;
  font-size: 12px;
}

.search-input:focus {
  outline: none;
  border-color: #58a6ff;
}

.search-input::placeholder {
  color: #6e7681;
}

.filter-btns {
  display: flex;
  gap: 4px;
}

.filter-btns button {
  padding: 6px 12px;
  background: #21262d;
  border: 1px solid #30363d;
  border-radius: 6px;
  color: #8b949e;
  font-size: 11px;
  cursor: pointer;
  transition: all 0.2s;
}

.filter-btns button:hover {
  border-color: #58a6ff;
  color: #58a6ff;
}

.filter-btns button.active {
  background: rgba(88, 166, 255, 0.15);
  border-color: #58a6ff;
  color: #58a6ff;
}

.filter-btns button.fault-btn:hover {
  border-color: #f85149;
  color: #f85149;
}

.filter-btns button.fault-btn.active {
  background: rgba(248, 81, 73, 0.15);
  border-color: #f85149;
  color: #f85149;
}

.sensor-grid {
  flex: 1;
  overflow-y: auto;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 8px;
  padding-right: 4px;
}

.sensor-grid::-webkit-scrollbar {
  width: 6px;
}

.sensor-grid::-webkit-scrollbar-track {
  background: transparent;
}

.sensor-grid::-webkit-scrollbar-thumb {
  background: #30363d;
  border-radius: 3px;
}

.sensor-card {
  background: rgba(33, 38, 45, 0.8);
  border: 1px solid #30363d;
  border-radius: 8px;
  padding: 10px;
  cursor: pointer;
  transition: all 0.2s;
  position: relative;
  overflow: hidden;
}

.sensor-card:hover {
  border-color: #58a6ff;
  transform: translateY(-1px);
}

.sensor-card.active {
  border-color: #58a6ff;
  background: rgba(88, 166, 255, 0.1);
}

.sensor-card.alert {
  border-color: #f85149;
  background: rgba(248, 81, 73, 0.1);
  animation: alertPulse 2s infinite;
}

@keyframes alertPulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(248, 81, 73, 0.4); }
  50% { box-shadow: 0 0 0 4px rgba(248, 81, 73, 0); }
}

.sensor-card.warning {
  border-color: #ffa41c;
  background: rgba(255, 164, 28, 0.1);
}

.sensor-card.faulty {
  border-color: #8b949e;
  background: repeating-linear-gradient(
    45deg,
    rgba(139, 148, 158, 0.1),
    rgba(139, 148, 158, 0.1) 5px,
    rgba(110, 118, 129, 0.1) 5px,
    rgba(110, 118, 129, 0.1) 10px
  );
  animation: faultPulse 2s infinite;
}

@keyframes faultPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

.sensor-card.stale {
  border-color: #6e7681;
  background: rgba(110, 118, 129, 0.15);
  opacity: 0.6;
}

.sensor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.sensor-id {
  font-size: 11px;
  font-weight: 600;
  color: #f0f6fc;
  font-family: 'SF Mono', Monaco, monospace;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #3fb950;
}

.status-dot.alert {
  background: #f85149;
  animation: blink 1s infinite;
}

.status-dot.warning {
  background: #ffa41c;
}

.status-dot.faulty {
  background: #8b949e;
  animation: blink 0.8s infinite;
}

.status-dot.stale {
  background: #6e7681;
  opacity: 0.5;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.sensor-body {
  font-size: 11px;
}

.gas-tag {
  display: inline-block;
  padding: 2px 6px;
  background: rgba(88, 166, 255, 0.2);
  color: #58a6ff;
  border-radius: 3px;
  font-weight: 600;
  margin-bottom: 4px;
}

.sensor-location {
  display: flex;
  justify-content: space-between;
  color: #8b949e;
  margin-bottom: 6px;
}

.concentration {
  display: flex;
  align-items: baseline;
  gap: 2px;
  flex-wrap: wrap;
}

.concentration .value {
  font-size: 16px;
  font-weight: 700;
  color: #f0f6fc;
  font-family: 'SF Mono', Monaco, monospace;
}

.concentration .value.alert {
  color: #f85149;
}

.concentration .value.faulty {
  color: #f85149;
  font-size: 13px;
}

.concentration .value.stale {
  color: #ffa41c;
  font-size: 13px;
}

.concentration .value.loading {
  color: #484f58;
}

.concentration .unit {
  font-size: 10px;
  color: #8b949e;
}

.concentration .threshold {
  font-size: 10px;
  color: #6e7681;
}

.fault-hint, .stale-hint {
  font-size: 10px;
  color: #8b949e;
  margin-left: 4px;
}

.sensor-progress {
  height: 3px;
  background: #30363d;
  border-radius: 2px;
  margin-top: 8px;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  transition: width 0.3s, background-color 0.3s;
}

.progress-bar.normal {
  background: #3fb950;
}

.progress-bar.warning {
  background: #ffa41c;
}

.progress-bar.alert {
  background: #f85149;
}

.progress-bar.faulty {
  background: repeating-linear-gradient(
    90deg,
    #8b949e,
    #8b949e 4px,
    #6e7681 4px,
    #6e7681 8px
  );
}

.progress-bar.stale {
  background: #6e7681;
  opacity: 0.5;
}

.fault-badge {
  position: absolute;
  top: 0;
  right: 0;
  background: rgba(248, 81, 73, 0.95);
  color: white;
  font-size: 9px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 0 0 0 6px;
  display: flex;
  align-items: center;
  gap: 3px;
}

.fault-icon {
  font-size: 10px;
}

.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #6e7681;
  font-size: 13px;
}
</style>

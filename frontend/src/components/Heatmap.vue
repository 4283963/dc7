<template>
  <div class="heatmap-container">
    <div class="heatmap-header">
      <h3>车间平面热力图 - {{ gasType }}</h3>
      <div class="legend">
        <div class="legend-item">
          <span class="legend-color safe"></span>
          <span>安全</span>
        </div>
        <div class="legend-item">
          <span class="legend-color warning"></span>
          <span>警告</span>
        </div>
        <div class="legend-item">
          <span class="legend-color danger"></span>
          <span>超标</span>
        </div>
        <div class="legend-item">
          <span class="legend-color faulty"></span>
          <span>故障</span>
        </div>
        <div class="legend-item">
          <span class="legend-color stale"></span>
          <span>断连</span>
        </div>
      </div>
    </div>
    <div ref="chartRef" class="chart"></div>
    <div v-if="hoveredSensor" class="tooltip" :style="tooltipStyle">
      <div class="tooltip-header" :class="{
        'header-faulty': hoveredSensor.health_status === 'faulty',
        'header-stale': hoveredSensor.health_status === 'stale'
      }">
        {{ hoveredSensor.sensor_id }}
        <span v-if="hoveredSensor.health_status === 'faulty'" class="health-badge faulty-badge">故障</span>
        <span v-if="hoveredSensor.health_status === 'stale'" class="health-badge stale-badge">断连</span>
      </div>
      <div class="tooltip-row">
        <span>区域:</span>
        <span>{{ hoveredSensor.area }}</span>
      </div>
      <div class="tooltip-row" v-if="hoveredSensor.health_status === 'healthy'">
        <span>浓度:</span>
        <span :class="{ alert: hoveredSensor.value > hoveredSensor.threshold }">
          {{ hoveredSensor.value.toFixed(4) }} PPM
        </span>
      </div>
      <div class="tooltip-row" v-else-if="hoveredSensor.health_status === 'faulty'">
        <span>读数:</span>
        <span class="faulty-text">
          {{ hoveredSensor.value.toFixed(4) }} PPM
          <small>（连续零值: {{ hoveredSensor.consecutive_zeros }}次）</small>
        </span>
      </div>
      <div class="tooltip-row" v-else>
        <span>读数:</span>
        <span class="stale-text">数据中断</span>
      </div>
      <div class="tooltip-row">
        <span>阈值:</span>
        <span>{{ hoveredSensor.threshold }} PPM</span>
      </div>
      <div class="tooltip-row" v-if="hoveredSensor.health_status !== 'healthy'">
        <span>状态:</span>
        <span :class="hoveredSensor.health_status === 'faulty' ? 'status-faulty' : 'status-stale'">
          {{ hoveredSensor.health_status === 'faulty' ? '⚠️ 设备故障 — 数据不可信' : '⚠️ 通讯中断 — 数据过期' }}
        </span>
      </div>
      <div class="tooltip-row" v-else>
        <span>状态:</span>
        <span :class="hoveredSensor.value > hoveredSensor.threshold ? 'status-danger' : 'status-safe'">
          {{ hoveredSensor.value > hoveredSensor.threshold ? '⚠️ 超标' : '✓ 正常' }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  gasType: { type: String, default: 'NH3' },
  windowSeconds: { type: Number, default: 60 },
  selectedArea: { type: String, default: 'all' }
})

const emit = defineEmits(['sensor-click', 'connection-status', 'alert-count', 'fault-count'])

const chartRef = ref(null)
let chart = null
let eventSource = null

const hoveredSensor = ref(null)
const tooltipStyle = ref({})
const heatmapData = ref([])
const maxValue = ref(50)

const GRID_WIDTH = 10
const GRID_HEIGHT = 8

const AREA_COLORS = {
  'CLEANROOM_A': { fill: 'rgba(88, 166, 255, 0.1)', border: '#58a6ff' },
  'CLEANROOM_B': { fill: 'rgba(63, 185, 80, 0.1)', border: '#3fb950' },
  'ETCH_BAY': { fill: 'rgba(255, 164, 28, 0.1)', border: '#ffa41c' },
  'DIFFUSION': { fill: 'rgba(188, 140, 255, 0.1)', border: '#bc8cff' },
  'WAFER_FAB': { fill: 'rgba(255, 111, 199, 0.1)', border: '#ff6fc7' }
}

function getColor(value, threshold, healthStatus) {
  if (healthStatus === 'faulty') {
    return { r: 139, g: 148, b: 158 }
  }
  if (healthStatus === 'stale') {
    return { r: 110, g: 118, b: 129 }
  }
  const ratio = value / threshold
  if (ratio < 0.5) {
    const t = ratio * 2
    return {
      r: Math.round(47 + t * 208),
      g: Math.round(161 + t * (128 - 161)),
      b: Math.round(79)
    }
  } else if (ratio < 1) {
    const t = (ratio - 0.5) * 2
    return {
      r: 255,
      g: Math.round(128 + t * (64 - 128)),
      b: 0
    }
  } else {
    const t = Math.min((ratio - 1) / 2, 1)
    return {
      r: 255,
      g: Math.round(64 - t * 64),
      b: 0
    }
  }
}

function rgbToString(rgb) {
  return `rgb(${rgb.r}, ${rgb.g}, ${rgb.b})`
}

function initChart() {
  if (!chartRef.value) return
  
  chart = echarts.init(chartRef.value, 'dark')
  
  const option = {
    backgroundColor: 'transparent',
    tooltip: {
      show: false
    },
    grid: {
      left: 60,
      right: 40,
      top: 40,
      bottom: 60
    },
    xAxis: {
      type: 'category',
      data: Array.from({ length: GRID_WIDTH }, (_, i) => `X${i}`),
      splitLine: {
        show: true,
        lineStyle: { color: '#30363d' }
      },
      axisLine: { lineStyle: { color: '#484f58' } }
    },
    yAxis: {
      type: 'category',
      data: Array.from({ length: GRID_HEIGHT }, (_, i) => `Y${i}`),
      splitLine: {
        show: true,
        lineStyle: { color: '#30363d' }
      },
      axisLine: { lineStyle: { color: '#484f58' } }
    },
    series: [
      {
        name: 'markers',
        type: 'scatter',
        data: [],
        symbolSize: 28,
        encode: { tooltip: ['value'] },
        label: {
          show: true,
          formatter: (params) => {
            const d = params.data[3]
            if (d && (d.health_status === 'faulty' || d.health_status === 'stale')) {
              return '!'
            }
            const val = params.data[2]
            return val.toFixed(2)
          },
          fontSize: 10,
          color: '#fff',
          textBorderColor: 'rgba(0,0,0,0.8)',
          textBorderWidth: 2
        }
      },
      {
        name: 'areas',
        type: 'custom',
        renderItem: renderAreas,
        data: [],
        z: -10
      }
    ]
  }
  
  chart.on('mousemove', onChartMouseMove)
  chart.on('mouseout', onChartMouseOut)
  chart.on('click', onChartClick)
  
  chart.setOption(option)
}

function renderAreas(params, api) {
  const areas = [
    { name: 'CLEANROOM_A', x: [0, 4], y: [0, 3] },
    { name: 'CLEANROOM_B', x: [5, 9], y: [0, 3] },
    { name: 'ETCH_BAY', x: [0, 4], y: [4, 7] },
    { name: 'DIFFUSION', x: [5, 9], y: [4, 7] },
    { name: 'WAFER_FAB', x: [2, 7], y: [2, 5] }
  ]
  
  const results = []
  
  areas.forEach(area => {
    if (props.selectedArea !== 'all' && props.selectedArea !== area.name) return
    
    const x1 = area.x[0]
    const x2 = area.x[1]
    const y1 = area.y[0]
    const y2 = area.y[1]
    
    const points = [
      api.coord([x1, y1]),
      api.coord([x2 + 0.8, y1]),
      api.coord([x2 + 0.8, y2 + 0.8]),
      api.coord([x1, y2 + 0.8])
    ]
    
    const colors = AREA_COLORS[area.name] || AREA_COLORS['CLEANROOM_A']
    
    results.push({
      type: 'group',
      children: [
        {
          type: 'polygon',
          shape: {
            points: points.map(p => [p[0], p[1]])
          },
          style: {
            fill: colors.fill,
            stroke: colors.border,
            lineWidth: 2,
            lineDash: [5, 3]
          }
        },
        {
          type: 'text',
          style: {
            x: (points[0][0] + points[1][0]) / 2,
            y: points[0][1] + 20,
            text: area.name,
            fill: colors.border,
            fontSize: 11,
            fontWeight: 'bold',
            align: 'center'
          }
        }
      ]
    })
  })
  
  return { type: 'group', children: results }
}

function connectSSE() {
  if (eventSource) {
    eventSource.close()
  }
  
  const url = `/api/stream/heatmap?gas_type=${props.gasType}&window_seconds=${props.windowSeconds}&interval=2`
  eventSource = new EventSource(url)
  
  eventSource.onopen = () => {
    console.log('SSE connected')
    emit('connection-status', true)
  }
  
  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.type === 'heatmap_update') {
        updateHeatmap(data.data)
      } else if (data.type === 'error') {
        console.error('SSE error:', data.message)
      }
    } catch (e) {
      console.error('Failed to parse SSE message:', e)
    }
  }
  
  eventSource.onerror = (err) => {
    console.error('SSE error:', err)
    emit('connection-status', false)
  }
}

function updateHeatmap(data) {
  heatmapData.value = data
  
  const filtered = props.selectedArea === 'all'
    ? data
    : data.filter(d => d.area === props.selectedArea)
  
  const healthyData = filtered.filter(d => d.health_status === 'healthy')
  const maxVal = Math.max(...healthyData.map(d => d.value), 1)
  maxValue.value = Math.max(maxVal * 1.2, 10)
  
  const alertCount = filtered.filter(d => d.status === 'alert').length
  const faultCount = filtered.filter(d => d.health_status === 'faulty' || d.health_status === 'stale').length
  emit('alert-count', alertCount)
  emit('fault-count', faultCount)
  
  const seriesData = filtered.map(d => {
    const color = getColor(d.value, d.threshold, d.health_status)
    const isFaulty = d.health_status === 'faulty'
    const isStale = d.health_status === 'stale'
    
    let shadowColor = 'transparent'
    let shadowBlur = 0
    let borderColor = 'transparent'
    let borderWidth = 0
    
    if (isFaulty) {
      shadowColor = 'rgba(139, 148, 158, 0.6)'
      shadowBlur = 12
      borderColor = '#f85149'
      borderWidth = 2
    } else if (isStale) {
      borderColor = '#ffa41c'
      borderWidth = 2
    } else if (d.value > d.threshold) {
      shadowColor = 'rgba(248, 81, 73, 0.5)'
      shadowBlur = 15
    }
    
    return {
      value: [d.x, d.y, d.value, d],
      itemStyle: {
        color: rgbToString(color),
        shadowColor,
        shadowBlur,
        borderColor,
        borderWidth,
        opacity: isFaulty ? 0.6 : (isStale ? 0.45 : 1)
      }
    }
  })
  
  if (chart) {
    chart.setOption({
      series: [{
        data: seriesData
      }]
    })
  }
}

function findSensorAt(x, y) {
  return heatmapData.value.find(d => d.x === x && d.y === y)
}

function onChartMouseMove(params) {
  if (params.componentType === 'series' && params.data) {
    const x = params.data[0]
    const y = params.data[1]
    const sensor = findSensorAt(x, y)
    if (sensor) {
      hoveredSensor.value = sensor
      const point = chart.convertToPixel({ seriesIndex: 0 }, [x, y])
      if (point) {
        tooltipStyle.value = {
          left: `${point[0] + 15}px`,
          top: `${point[1] + 15}px`
        }
      }
    }
  }
}

function onChartMouseOut() {
  hoveredSensor.value = null
}

function onChartClick(params) {
  if (params.componentType === 'series' && params.data) {
    const x = params.data[0]
    const y = params.data[1]
    const sensor = findSensorAt(x, y)
    if (sensor) {
      emit('sensor-click', sensor)
    }
  }
}

function refresh() {
  connectSSE()
  if (chart) {
    chart.setOption({ series: [{ data: [] }] })
  }
}

function handleResize() {
  if (chart) {
    chart.resize()
  }
}

watch(() => props.gasType, () => {
  connectSSE()
})

watch(() => props.selectedArea, () => {
  updateHeatmap(heatmapData.value)
})

onMounted(() => {
  initChart()
  connectSSE()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  if (eventSource) {
    eventSource.close()
  }
  if (chart) {
    chart.dispose()
  }
  window.removeEventListener('resize', handleResize)
})

defineExpose({ refresh })
</script>

<style scoped>
.heatmap-container {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: rgba(22, 27, 34, 0.9);
  border: 1px solid #30363d;
  border-radius: 12px;
  padding: 16px;
  position: relative;
  overflow: hidden;
}

.heatmap-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-shrink: 0;
}

.heatmap-header h3 {
  font-size: 14px;
  font-weight: 600;
  color: #c9d1d9;
  margin: 0;
}

.legend {
  display: flex;
  align-items: center;
  gap: 16px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #8b949e;
}

.legend-color {
  width: 12px;
  height: 12px;
  border-radius: 3px;
}

.legend-color.safe {
  background: linear-gradient(135deg, #2fa84f 0%, #3fb950 100%);
}

.legend-color.warning {
  background: linear-gradient(135deg, #ff8c00 0%, #ffa41c 100%);
}

.legend-color.danger {
  background: linear-gradient(135deg, #cf222e 0%, #f85149 100%);
}

.legend-color.faulty {
  background: repeating-linear-gradient(
    45deg,
    #8b949e,
    #8b949e 3px,
    #6e7681 3px,
    #6e7681 6px
  );
  border: 1.5px solid #f85149;
}

.legend-color.stale {
  background: repeating-linear-gradient(
    45deg,
    #6e7681,
    #6e7681 3px,
    #484f58 3px,
    #484f58 6px
  );
  border: 1.5px solid #ffa41c;
}

.chart {
  flex: 1;
  min-height: 0;
}

.tooltip {
  position: absolute;
  background: rgba(22, 27, 34, 0.98);
  border: 1px solid #30363d;
  border-radius: 8px;
  padding: 12px;
  min-width: 220px;
  pointer-events: none;
  z-index: 100;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
}

.tooltip-header {
  font-weight: 600;
  color: #f0f6fc;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid #30363d;
  display: flex;
  align-items: center;
  gap: 8px;
}

.tooltip-header.header-faulty {
  border-bottom-color: #f85149;
  color: #f85149;
}

.tooltip-header.header-stale {
  border-bottom-color: #ffa41c;
  color: #ffa41c;
}

.health-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.5px;
}

.faulty-badge {
  background: rgba(248, 81, 73, 0.2);
  color: #f85149;
  border: 1px solid #f85149;
}

.stale-badge {
  background: rgba(255, 164, 28, 0.2);
  color: #ffa41c;
  border: 1px solid #ffa41c;
}

.tooltip-row {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  margin-top: 4px;
}

.tooltip-row span:first-child {
  color: #8b949e;
}

.tooltip-row span:last-child {
  color: #c9d1d9;
  font-family: 'SF Mono', Monaco, monospace;
}

.tooltip-row .alert {
  color: #f85149;
  font-weight: 600;
}

.faulty-text {
  color: #8b949e !important;
  text-decoration: line-through;
}

.faulty-text small {
  color: #f85149 !important;
  text-decoration: none;
}

.stale-text {
  color: #6e7681 !important;
  font-style: italic;
}

.status-safe {
  color: #3fb950 !important;
}

.status-danger {
  color: #f85149 !important;
  font-weight: 600;
}

.status-faulty {
  color: #f85149 !important;
  font-weight: 600;
}

.status-stale {
  color: #ffa41c !important;
  font-weight: 600;
}
</style>

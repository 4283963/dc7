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
        <div class="legend-item">
          <span class="legend-color prediction"></span>
          <span>预测扩散</span>
        </div>
      </div>
    </div>
    <div ref="chartRef" class="chart"></div>
    <div v-if="environment && diffusionPredictions.length > 0" class="env-panel">
      <div class="env-title">🌬 环境参数</div>
      <div class="env-row">
        <span class="env-label">风向</span>
        <span class="env-value">
          {{ environment.wind_direction?.toFixed(0) }}°
          <span class="wind-arrow" :style="{ transform: `rotate(${-environment.wind_direction + 90}deg)` }">➤</span>
        </span>
      </div>
      <div class="env-row">
        <span class="env-label">风速</span>
        <span class="env-value">{{ environment.wind_speed?.toFixed(2) }} m/s</span>
      </div>
      <div class="env-row">
        <span class="env-label">温度</span>
        <span class="env-value">{{ environment.temperature?.toFixed(1) }}°C</span>
      </div>
    </div>
    <div v-if="hoveredSensor" class="tooltip" :style="tooltipStyle">
      <div class="tooltip-header" :class="{
        'header-faulty': hoveredSensor.health_status === 'faulty',
        'header-stale': hoveredSensor.health_status === 'stale',
        'header-predicted': hoveredSensor.is_predicted
      }">
        {{ hoveredSensor.sensor_id || '预测区域' }}
        <span v-if="hoveredSensor.health_status === 'faulty'" class="health-badge faulty-badge">故障</span>
        <span v-if="hoveredSensor.health_status === 'stale'" class="health-badge stale-badge">断连</span>
        <span v-if="hoveredSensor.is_predicted" class="health-badge predicted-badge">预测</span>
      </div>
      <div class="tooltip-row" v-if="hoveredSensor.area">
        <span>区域:</span>
        <span>{{ hoveredSensor.area }}</span>
      </div>
      <div class="tooltip-row" v-if="hoveredSensor.is_predicted">
        <span>预测概率:</span>
        <span class="status-warning">{{ (hoveredSensor.probability * 100).toFixed(0) }}%</span>
      </div>
      <div class="tooltip-row" v-if="hoveredSensor.is_predicted">
        <span>风险等级:</span>
        <span :class="`status-${hoveredSensor.risk_level}`">
          {{ hoveredSensor.risk_level === 'high' ? '🔴 高风险' : hoveredSensor.risk_level === 'medium' ? '🟡 中风险' : '🟢 低风险' }}
        </span>
      </div>
      <div class="tooltip-row" v-else-if="hoveredSensor.health_status === 'healthy'">
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
      <div class="tooltip-row" v-if="hoveredSensor.threshold">
        <span>阈值:</span>
        <span>{{ hoveredSensor.threshold }} PPM</span>
      </div>
      <div class="tooltip-row" v-if="hoveredSensor.is_predicted">
        <span>来源:</span>
        <span>{{ hoveredSensor.source_sensor }}</span>
      </div>
      <div class="tooltip-row" v-if="hoveredSensor.health_status !== undefined && !hoveredSensor.is_predicted">
        <span>状态:</span>
        <span :class="getStatusClass(hoveredSensor)">
          {{ getStatusText(hoveredSensor) }}
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

const emit = defineEmits(['sensor-click', 'connection-status', 'alert-count', 'fault-count', 'prediction-update'])

const chartRef = ref(null)
let chart = null
let eventSource = null

const hoveredSensor = ref(null)
const tooltipStyle = ref({})
const heatmapData = ref([])
const diffusionPredictions = ref([])
const predictedCells = ref([])
const environment = ref(null)
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

function getColor(value, threshold, healthStatus, isPredicted) {
  if (isPredicted) {
    return { r: 255, g: 210, b: 0 }
  }
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
    tooltip: { show: false },
    grid: {
      left: 60,
      right: 40,
      top: 40,
      bottom: 60
    },
    xAxis: {
      type: 'category',
      data: Array.from({ length: GRID_WIDTH }, (_, i) => `X${i}`),
      splitLine: { show: true, lineStyle: { color: '#30363d' } },
      axisLine: { lineStyle: { color: '#484f58' } }
    },
    yAxis: {
      type: 'category',
      data: Array.from({ length: GRID_HEIGHT }, (_, i) => `Y${i}`),
      splitLine: { show: true, lineStyle: { color: '#30363d' } },
      axisLine: { lineStyle: { color: '#484f58' } }
    },
    series: [
      {
        name: 'diffusion_zones',
        type: 'custom',
        renderItem: renderDiffusionZones,
        data: [],
        z: 5
      },
      {
        name: 'wind_indicator',
        type: 'custom',
        renderItem: renderWindIndicator,
        data: [],
        z: 7
      },
      {
        name: 'predicted_cells',
        type: 'scatter',
        data: [],
        symbolSize: 26,
        z: 15,
        label: {
          show: true,
          formatter: (params) => {
            const d = params.data[3]
            if (d && d.probability) {
              return `${(d.probability * 100).toFixed(0)}%`
            }
            return ''
          },
          fontSize: 9,
          color: '#1a1a1a',
          fontWeight: 'bold',
          textBorderColor: 'rgba(255,210,0,0.8)',
          textBorderWidth: 2
        }
      },
      {
        name: 'markers',
        type: 'scatter',
        data: [],
        symbolSize: 28,
        z: 20,
        encode: { tooltip: ['value'] },
        label: {
          show: true,
          formatter: (params) => {
            if (!params.data || params.data.length < 4) return ''
            const d = params.data[3]
            if (d && (d.health_status === 'faulty' || d.health_status === 'stale')) {
              return '!'
            }
            const val = params.data[2]
            if (val === undefined || val === null) return ''
            return typeof val === 'number' ? val.toFixed(2) : ''
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
          shape: { points: points.map(p => [p[0], p[1]]) },
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

function renderDiffusionZones(params, api) {
  if (!diffusionPredictions.value.length) return { type: 'group', children: [] }
  
  const now = Date.now()
  const results = []
  
  diffusionPredictions.value.forEach(pred => {
    const src = api.coord([pred.source_x + 0.4, pred.source_y + 0.4])
    if (!src || !src[0] || !src[1]) return
    
    const windDir = (pred.environment?.wind_direction_deg || 90) * Math.PI / 180
    const radius = pred.predicted_radius_cells || 3
    const spreadAngle = (pred.predicted_spread_angle_deg || 60) * Math.PI / 180
    
    const unitPts = api.coord([1, 1])
    const zeroPts = api.coord([0, 0])
    const cellW = unitPts[0] - zeroPts[0]
    const cellH = unitPts[1] - zeroPts[1]
    const cellSize = Math.min(cellW, cellH)
    const pxRadius = radius * cellSize
    
    const startAngle = windDir - spreadAngle / 2
    const endAngle = windDir + spreadAngle / 2
    
    const age = (now - pred.trigger_time_ms) / 1000
    const maxAge = pred.prediction_window_seconds * 4
    const pulsePhase = Math.min(age / maxAge, 1)
    
    const alpha = Math.max(0.08, 0.25 - pulsePhase * 0.15)
    const dashAlpha = Math.max(0.5, 1 - pulsePhase * 0.5)
    
    const isDanger = pred.alert_level === 'danger'
    const zoneColor = isDanger ? '248, 81, 73' : '255, 193, 7'
    
    const arcPoints = [[src[0], src[1]]]
    const segments = 40
    for (let i = 0; i <= segments; i++) {
      const theta = startAngle + (endAngle - startAngle) * i / segments
      const ex = src[0] + pxRadius * Math.cos(theta)
      const ey = src[1] - pxRadius * Math.sin(theta)
      arcPoints.push([ex, ey])
    }
    arcPoints.push([src[0], src[1]])
    
    results.push({
      type: 'polygon',
      shape: { points: arcPoints },
      style: {
        fill: `rgba(${zoneColor}, ${alpha})`,
        stroke: `rgba(${zoneColor}, 0)`,
        lineWidth: 0
      }
    })
    
    const dashPoints = []
    const segs = 50
    for (let i = 0; i <= segs; i++) {
      const theta = startAngle + (endAngle - startAngle) * i / segs
      const ex = src[0] + pxRadius * Math.cos(theta)
      const ey = src[1] - pxRadius * Math.sin(theta)
      dashPoints.push([ex, ey])
    }
    
    for (let i = 0; i < dashPoints.length - 1; i += 2) {
      results.push({
        type: 'line',
        shape: {
          x1: dashPoints[i][0],
          y1: dashPoints[i][1],
          x2: dashPoints[Math.min(i + 1, dashPoints.length - 1)][0],
          y2: dashPoints[Math.min(i + 1, dashPoints.length - 1)][1]
        },
        style: {
          stroke: isDanger ? `rgba(248, 81, 73, ${dashAlpha})` : `rgba(255, 193, 7, ${dashAlpha})`,
          lineWidth: 3,
          lineDash: [6, 4]
        }
      })
    }
    
    const lineEnd1 = [
      src[0] + pxRadius * 0.15 * Math.cos(startAngle),
      src[1] - pxRadius * 0.15 * Math.sin(startAngle)
    ]
    const farLine1 = [
      src[0] + pxRadius * 1.0 * Math.cos(startAngle),
      src[1] - pxRadius * 1.0 * Math.sin(startAngle)
    ]
    const lineEnd2 = [
      src[0] + pxRadius * 0.15 * Math.cos(endAngle),
      src[1] - pxRadius * 0.15 * Math.sin(endAngle)
    ]
    const farLine2 = [
      src[0] + pxRadius * 1.0 * Math.cos(endAngle),
      src[1] - pxRadius * 1.0 * Math.sin(endAngle)
    ]
    
    results.push({
      type: 'line',
      shape: { x1: lineEnd1[0], y1: lineEnd1[1], x2: farLine1[0], y2: farLine1[1] },
      style: {
        stroke: `rgba(${zoneColor}, ${dashAlpha * 0.8})`,
        lineWidth: 2,
        lineDash: [4, 4]
      }
    })
    results.push({
      type: 'line',
      shape: { x1: lineEnd2[0], y1: lineEnd2[1], x2: farLine2[0], y2: farLine2[1] },
      style: {
        stroke: `rgba(${zoneColor}, ${dashAlpha * 0.8})`,
        lineWidth: 2,
        lineDash: [4, 4]
      }
    })
    
    results.push({
      type: 'circle',
      shape: { cx: src[0], cy: src[1], r: cellSize * 0.2 },
      style: {
        fill: 'transparent',
        stroke: `rgba(${zoneColor}, ${dashAlpha})`,
        lineWidth: 3,
        lineDash: [4, 4]
      }
    })
    
    results.push({
      type: 'text',
      style: {
        x: src[0] + 10,
        y: src[1] - 25,
        text: isDanger ? '⚠ 扩散预警' : '预测扩散',
        fill: isDanger ? '#f85149' : '#ffc107',
        fontSize: 11,
        fontWeight: 'bold',
        textBorderColor: 'rgba(0,0,0,0.7)',
        textBorderWidth: 3
      }
    })
  })
  
  return { type: 'group', children: results }
}

function renderWindIndicator(params, api) {
  if (!environment.value) return { type: 'group', children: [] }
  
  const grid = { left: 60, right: 40, top: 40, bottom: 60 }
  const cw = params.width - grid.left - grid.right
  const ch = params.height - grid.top - grid.bottom
  
  const x = grid.left + cw - 30
  const y = grid.top + 20
  
  const dir = (environment.value.wind_direction || 90) * Math.PI / 180
  const r = 14
  
  return {
    type: 'group',
    children: [
      {
        type: 'circle',
        shape: { cx: x, cy: y, r: r + 4 },
        style: {
          fill: 'rgba(33, 38, 45, 0.85)',
          stroke: 'rgba(88, 166, 255, 0.5)',
          lineWidth: 1.5
        }
      },
      {
        type: 'polygon',
        shape: {
          points: [
            [x + r * Math.cos(dir), y - r * Math.sin(dir)],
            [x + r * 0.5 * Math.cos(dir + 2.5), y - r * 0.5 * Math.sin(dir + 2.5)],
            [x - r * 0.7 * Math.cos(dir), y + r * 0.7 * Math.sin(dir)],
            [x + r * 0.5 * Math.cos(dir - 2.5), y - r * 0.5 * Math.sin(dir - 2.5)]
          ]
        },
        style: { fill: '#58a6ff', stroke: '#58a6ff', lineWidth: 1 }
      },
      {
        type: 'text',
        style: {
          x, y: y + r + 14,
          text: 'WIND',
          fill: '#8b949e',
          fontSize: 9,
          fontWeight: 'bold',
          align: 'center'
        }
      }
    ]
  }
}

function getStatusClass(s) {
  if (s.is_predicted) return 'status-warning'
  if (s.health_status === 'faulty') return 'status-faulty'
  if (s.health_status === 'stale') return 'status-stale'
  return s.value > s.threshold ? 'status-danger' : 'status-safe'
}

function getStatusText(s) {
  if (s.health_status === 'faulty') return '⚠️ 设备故障 — 数据不可信'
  if (s.health_status === 'stale') return '⚠️ 通讯中断 — 数据过期'
  return s.value > s.threshold ? '⚠️ 超标' : '✓ 正常'
}

function connectSSE() {
  if (eventSource) eventSource.close()
  
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
        if (data.environment) environment.value = data.environment
        if (data.diffusion_predictions) {
          diffusionPredictions.value = data.diffusion_predictions
          emit('prediction-update', data.diffusion_predictions)
        }
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
  
  const allPredictedCells = new Map()
  diffusionPredictions.value.forEach(pred => {
    pred.affected_cells.forEach(cell => {
      const key = `${cell.x},${cell.y}`
      if (!allPredictedCells.has(key) || cell.probability > allPredictedCells.get(key).probability) {
        allPredictedCells.set(key, {
          x: cell.x,
          y: cell.y,
          probability: cell.probability,
          risk_level: cell.risk_level,
          source_sensor: pred.source_sensor
        })
      }
    })
  })
  predictedCells.value = Array.from(allPredictedCells.values())
  
  const sourceSet = new Set(filtered.map(d => `${d.x},${d.y}`))
  const nonSourcePredicted = predictedCells.value.filter(p => !sourceSet.has(`${p.x},${p.y}`))
  
  const predictedSeriesData = nonSourcePredicted.map(p => {
    const opacity = 0.25 + p.probability * 0.55
    return {
      value: [p.x, p.y, p.probability, {
        is_predicted: true,
        probability: p.probability,
        risk_level: p.risk_level,
        source_sensor: p.source_sensor,
        area: null
      }],
      itemStyle: {
        color: p.risk_level === 'high'
          ? `rgba(255, 152, 0, ${opacity})`
          : p.risk_level === 'medium'
            ? `rgba(255, 210, 0, ${opacity})`
            : `rgba(174, 213, 129, ${opacity})`,
        borderColor: p.probability > 0.5 ? '#ff6b00' : '#ffc107',
        borderWidth: 2,
        borderDash: [4, 4],
        shadowColor: p.probability > 0.5 ? 'rgba(255, 152, 0, 0.4)' : 'rgba(255, 193, 7, 0.3)',
        shadowBlur: 10
      }
    }
  })
  
  const seriesData = filtered.map(d => {
    const color = getColor(d.value, d.threshold, d.health_status, false)
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
    
    const predKey = `${d.x},${d.y}`
    if (allPredictedCells.has(predKey)) {
      borderColor = borderColor === 'transparent' ? '#ffc107' : borderColor
      borderWidth = Math.max(borderWidth, 2)
    }
    
    return {
      value: [d.x, d.y, d.value, {
        ...d,
        is_predicted: allPredictedCells.has(predKey),
        probability: allPredictedCells.get(predKey)?.probability
      }],
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
      series: [
        { data: [{}], renderItem: renderDiffusionZones },
        { data: [{}], renderItem: renderWindIndicator },
        { data: predictedSeriesData },
        { data: seriesData },
        { data: [{}] }
      ]
    })
  }
}

function findSensorAt(x, y) {
  const direct = heatmapData.value.find(d => d.x === x && d.y === y)
  if (direct) {
    const pred = predictedCells.value.find(p => p.x === x && p.y === y)
    if (pred) {
      return { ...direct, is_predicted: true, probability: pred.probability, risk_level: pred.risk_level, source_sensor: pred.source_sensor }
    }
    return direct
  }
  
  const pred = predictedCells.value.find(p => p.x === x && p.y === y)
  if (pred) {
    return {
      x, y,
      sensor_id: null,
      is_predicted: true,
      probability: pred.probability,
      risk_level: pred.risk_level,
      source_sensor: pred.source_sensor,
      area: null
    }
  }
  return null
}

function onChartMouseMove(params) {
  if (params.componentType === 'series' && params.data && params.data.length >= 2) {
    const x = params.data[0]
    const y = params.data[1]
    const sensor = findSensorAt(x, y)
    if (sensor) {
      hoveredSensor.value = sensor
      const point = chart.convertToPixel({ seriesIndex: 3 }, [x, y])
      if (point) {
        tooltipStyle.value = { left: `${point[0] + 15}px`, top: `${point[1] + 15}px` }
      }
    } else {
      hoveredSensor.value = null
    }
  }
}

function onChartMouseOut() {
  hoveredSensor.value = null
}

function onChartClick(params) {
  if (params.componentType === 'series' && params.data && params.data.length >= 2) {
    const x = params.data[0]
    const y = params.data[1]
    const sensor = findSensorAt(x, y)
    if (sensor && sensor.sensor_id && !sensor.is_predicted) {
      emit('sensor-click', sensor)
    }
  }
}

function refresh() {
  connectSSE()
  if (chart) chart.setOption({ series: [{ data: [] }] })
}

function handleResize() {
  if (chart) chart.resize()
}

watch(() => props.gasType, () => {
  diffusionPredictions.value = []
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
  if (eventSource) eventSource.close()
  if (chart) chart.dispose()
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
  flex-wrap: wrap;
  gap: 10px;
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
  gap: 14px;
  flex-wrap: wrap;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 5px;
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
  background: repeating-linear-gradient(45deg, #8b949e, #8b949e 3px, #6e7681 3px, #6e7681 6px);
  border: 1.5px solid #f85149;
}
.legend-color.stale {
  background: repeating-linear-gradient(45deg, #6e7681, #6e7681 3px, #484f58 3px, #484f58 6px);
  border: 1.5px solid #ffa41c;
}
.legend-color.prediction {
  background: rgba(255, 193, 7, 0.4);
  border: 2px dashed #ffc107;
}

.chart {
  flex: 1;
  min-height: 0;
}

.env-panel {
  position: absolute;
  top: 60px;
  right: 24px;
  background: rgba(22, 27, 34, 0.92);
  border: 1px solid #30363d;
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 11px;
  z-index: 50;
  min-width: 110px;
}

.env-title {
  font-weight: 700;
  color: #58a6ff;
  margin-bottom: 6px;
  text-align: center;
  font-size: 10px;
  letter-spacing: 0.5px;
}

.env-row {
  display: flex;
  justify-content: space-between;
  margin-top: 3px;
}

.env-label {
  color: #8b949e;
}

.env-value {
  color: #c9d1d9;
  font-family: 'SF Mono', Monaco, monospace;
  display: flex;
  align-items: center;
  gap: 4px;
}

.wind-arrow {
  display: inline-block;
  color: #58a6ff;
  font-size: 12px;
  transition: transform 0.5s ease;
}

.tooltip {
  position: absolute;
  background: rgba(22, 27, 34, 0.98);
  border: 1px solid #30363d;
  border-radius: 8px;
  padding: 12px;
  min-width: 230px;
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
.tooltip-header.header-predicted {
  border-bottom-color: #ffc107;
  color: #ffc107;
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
.predicted-badge {
  background: rgba(255, 193, 7, 0.2);
  color: #ffc107;
  border: 1px solid #ffc107;
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

.status-safe { color: #3fb950 !important; }
.status-danger { color: #f85149 !important; font-weight: 600; }
.status-faulty { color: #f85149 !important; font-weight: 600; }
.status-stale { color: #ffa41c !important; font-weight: 600; }
.status-warning { color: #ffc107 !important; font-weight: 600; }
.status-high { color: #ff6b00 !important; font-weight: 600; }
.status-medium { color: #ffc107 !important; font-weight: 600; }
.status-low { color: #aed581 !important; }
</style>

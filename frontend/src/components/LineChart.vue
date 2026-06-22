<template>
  <div class="linechart-container">
    <div class="chart-info" v-if="sensorInfo">
      <span class="sensor-id">{{ sensorInfo.sensor_id }}</span>
      <span class="sensor-area">{{ sensorInfo.area }}</span>
      <span class="sensor-threshold">阈值: {{ sensorInfo.threshold }} PPM</span>
    </div>
    <div ref="chartRef" class="chart"></div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted, computed } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  sensorId: { type: String, default: '' },
  gasType: { type: String, default: 'NH3' },
  minutes: { type: Number, default: 10 }
})

const chartRef = ref(null)
let chart = null
let eventSource = null

const sensorInfo = computed(() => {
  if (!props.sensorId) return null
  return {
    sensor_id: props.sensorId,
    area: 'loading...',
    threshold: '...'
  }
})

function initChart() {
  if (!chartRef.value) return
  
  chart = echarts.init(chartRef.value, 'dark')
  
  const option = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(22, 27, 34, 0.98)',
      borderColor: '#30363d',
      borderWidth: 1,
      textStyle: { color: '#c9d1d9' },
      formatter: (params) => {
        if (!params || params.length === 0) return ''
        const p = params[0]
        const time = new Date(p.value[0])
        const timeStr = time.toLocaleTimeString('zh-CN', { hour12: false })
        return `
          <div style="font-weight: 600; margin-bottom: 4px;">${timeStr}</div>
          <div>浓度: <span style="color: #58a6ff; font-weight: 600;">${p.value[1].toFixed(4)} PPM</span></div>
          <div>移动平均: <span style="color: #3fb950;">${p.value[2]?.toFixed(4) || '-'} PPM</span></div>
        `
      }
    },
    grid: {
      left: 50,
      right: 20,
      top: 20,
      bottom: 40
    },
    xAxis: {
      type: 'time',
      axisLine: { lineStyle: { color: '#484f58' } },
      axisLabel: {
        color: '#8b949e',
        fontSize: 10,
        formatter: (value) => {
          const d = new Date(value)
          return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
        }
      },
      splitLine: { lineStyle: { color: '#30363d' } }
    },
    yAxis: {
      type: 'value',
      name: 'PPM',
      nameTextStyle: { color: '#8b949e', fontSize: 10 },
      axisLine: { lineStyle: { color: '#484f58' } },
      axisLabel: {
        color: '#8b949e',
        fontSize: 10,
        formatter: (value) => value.toFixed(2)
      },
      splitLine: { lineStyle: { color: '#30363d' } }
    },
    series: [
      {
        name: '实时浓度',
        type: 'line',
        data: [],
        smooth: true,
        symbol: 'none',
        lineStyle: {
          width: 2,
          color: '#58a6ff'
        },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(88, 166, 255, 0.3)' },
            { offset: 1, color: 'rgba(88, 166, 255, 0.02)' }
          ])
        }
      },
      {
        name: '移动平均',
        type: 'line',
        data: [],
        smooth: true,
        symbol: 'none',
        lineStyle: {
          width: 2,
          color: '#3fb950',
          type: 'dashed'
        }
      },
      {
        name: '阈值线',
        type: 'line',
        data: [],
        symbol: 'none',
        lineStyle: {
          width: 1,
          color: '#f85149',
          type: 'dotted'
        },
        markLine: {
          silent: true,
          data: [{
            yAxis: 25,
            lineStyle: { color: '#f85149', type: 'dotted', width: 1 },
            label: {
              formatter: '阈值',
              color: '#f85149',
              fontSize: 10
            }
          }]
        }
      }
    ]
  }
  
  chart.setOption(option)
}

function connectSSE() {
  if (eventSource) {
    eventSource.close()
  }
  
  if (!props.sensorId || !props.gasType) return
  
  const url = `/api/stream/linechart?sensor_id=${props.sensorId}&gas_type=${props.gasType}&minutes=${props.minutes}&interval=2`
  eventSource = new EventSource(url)
  
  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.type === 'linechart_update') {
        updateChart(data.data)
      }
    } catch (e) {
      console.error('Failed to parse linechart SSE message:', e)
    }
  }
  
  eventSource.onerror = (err) => {
    console.error('Linechart SSE error:', err)
  }
}

function updateChart(data) {
  if (!chart || !data || data.length === 0) return
  
  const rawData = []
  const avgData = []
  let threshold = 25
  
  data.forEach(d => {
    const ts = d.timestamp || d[0]
    const conc = d.concentration !== undefined ? d.concentration : d[1]
    const avg = d.moving_avg !== undefined ? d.moving_avg : (d[2] !== undefined ? d[2] : null)
    
    rawData.push([ts, conc])
    if (avg !== null && avg !== undefined) {
      avgData.push([ts, avg])
    }
  })
  
  chart.setOption({
    series: [
      { data: rawData },
      { data: avgData },
      {
        markLine: {
          data: [{
            yAxis: threshold,
            lineStyle: { color: '#f85149', type: 'dotted', width: 1 },
            label: {
              formatter: `阈值 ${threshold}`,
              color: '#f85149',
              fontSize: 10
            }
          }]
        }
      }
    ]
  })
}

function refresh() {
  connectSSE()
  if (chart) {
    chart.setOption({
      series: [{ data: [] }, { data: [] }]
    })
  }
}

function handleResize() {
  if (chart) {
    chart.resize()
  }
}

watch(() => props.sensorId, () => {
  refresh()
})

watch(() => props.gasType, () => {
  refresh()
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
.linechart-container {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 250px;
}

.chart-info {
  display: flex;
  gap: 16px;
  margin-bottom: 8px;
  font-size: 12px;
}

.sensor-id {
  font-weight: 600;
  color: #f0f6fc;
}

.sensor-area {
  color: #8b949e;
}

.sensor-threshold {
  color: #f85149;
  margin-left: auto;
}

.chart {
  flex: 1;
  min-height: 0;
}
</style>

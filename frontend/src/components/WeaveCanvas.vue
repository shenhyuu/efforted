<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Energy, WeaveData, WeaveThread } from '@/api'

const props = defineProps<{ weave: WeaveData | null; animateKey?: number }>()
const emit = defineEmits<{ selectDay: [day: string | null] }>()
const canvas = ref<HTMLCanvasElement | null>(null)
const wrap = ref<HTMLDivElement | null>(null)
const zoom = ref(1)
let touchDistance = 0
let observer: ResizeObserver | undefined
let frame = 0

const colors: Record<Energy | 'plain', string> = {
  low: '#87979e', mid: '#a78469', enough: '#858d70', plain: '#948b80',
}

function expandedThreads() {
  if (!props.weave) return [] as Array<{ energy: Energy | null; group: number; day: string | null }>
  const result: Array<{ energy: Energy | null; group: number; day: string | null }> = []
  const append = (threads: WeaveThread[], group: number, day: string | null) => {
    threads.forEach((thread) => {
      for (let index = 0; index < thread.count && result.length < 2000; index++) {
        result.push({ energy: thread.energy, group, day })
      }
    })
  }
  append(props.weave.past.threads, -1, null)
  props.weave.days.forEach((day, index) => append(day.threads, index, day.day))
  return result
}

const visibleThreads = computed(() => {
  const all = expandedThreads()
  const count = Math.max(1, Math.ceil(all.length / zoom.value))
  return all.slice(-count)
})

function draw(progress = 1) {
  const element = canvas.value
  const weave = props.weave
  if (!element || !weave) return
  const bounds = element.getBoundingClientRect()
  const ratio = Math.min(window.devicePixelRatio || 1, 2)
  const width = Math.max(280, bounds.width), height = Math.max(300, bounds.height)
  element.width = Math.round(width * ratio); element.height = Math.round(height * ratio)
  const context = element.getContext('2d')
  if (!context) return
  context.scale(ratio, ratio); context.clearRect(0, 0, width, height)
  const threads = visibleThreads.value
  const visible = Math.ceil(threads.length * progress)
  const temperature = Math.max(.15, Math.min(1, weave.ember.temperature))
  const margin = 22, span = Math.max(1, height - margin * 2)
  threads.slice(0, visible).forEach((thread, index) => {
    const y = margin + (index / Math.max(threads.length - 1, 1)) * span
    const seed = ((index + 11) * 2654435761) >>> 0
    const bend = ((seed % 19) - 9) * .72
    const groupShift = thread.group < 0 ? -5 : ((thread.group % 7) - 3) * .8
    context.beginPath()
    context.moveTo(8, y)
    context.bezierCurveTo(width * .28, y + bend, width * .67, y - bend + groupShift, width - 8, y + groupShift)
    context.strokeStyle = colors[thread.energy || 'plain']
    context.globalAlpha = (.2 + temperature * .56) * (.78 + (seed % 20) / 100)
    context.lineWidth = threads.length > 900 ? .65 : threads.length > 300 ? .9 : 1.25
    context.stroke()
  })
  context.globalAlpha = 1
}

function changeZoom(next: number) {
  zoom.value = Math.max(1, Math.min(4, next))
  draw()
}
function pick(event: PointerEvent) {
  const element = canvas.value
  const threads = visibleThreads.value
  if (!element || !threads.length) return
  const bounds = element.getBoundingClientRect()
  const margin = 22
  const position = Math.max(0, Math.min(1, (event.clientY - bounds.top - margin) / Math.max(1, bounds.height - margin * 2)))
  const thread = threads[Math.round(position * Math.max(0, threads.length - 1))]
  if (thread) emit('selectDay', thread.day)
}
function distance(touches: TouchList) {
  if (touches.length < 2) return 0
  return Math.hypot(touches[0]!.clientX - touches[1]!.clientX, touches[0]!.clientY - touches[1]!.clientY)
}
function onTouchStart(event: TouchEvent) { touchDistance = distance(event.touches) }
function onTouchMove(event: TouchEvent) {
  const next = distance(event.touches)
  if (!touchDistance || !next) return
  if (Math.abs(next - touchDistance) > 18) {
    event.preventDefault()
    changeZoom(zoom.value + (next > touchDistance ? .5 : -.5))
    touchDistance = next
  }
}

function render(animate: boolean) {
  cancelAnimationFrame(frame)
  if (!animate || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return draw()
  const started = performance.now()
  const tick = (now: number) => {
    const progress = Math.min(1, (now - started) / 520)
    draw(1 - Math.pow(1 - progress, 3))
    if (progress < 1) frame = requestAnimationFrame(tick)
  }
  frame = requestAnimationFrame(tick)
}

watch(() => props.weave, () => render(false), { deep: true })
watch(() => props.animateKey, () => render(true))
onMounted(() => {
  observer = new ResizeObserver(() => draw())
  if (canvas.value) observer.observe(canvas.value)
  wrap.value?.addEventListener('touchstart', onTouchStart, { passive: true })
  wrap.value?.addEventListener('touchmove', onTouchMove, { passive: false })
  draw()
})
onBeforeUnmount(() => {
  observer?.disconnect(); cancelAnimationFrame(frame)
  wrap.value?.removeEventListener('touchstart', onTouchStart)
  wrap.value?.removeEventListener('touchmove', onTouchMove)
})
</script>

<template>
  <div ref="wrap" class="weave-canvas-wrap">
    <canvas ref="canvas" class="weave-canvas" role="button" tabindex="0" aria-label="打开这根痕迹所在日期" @pointerup="pick" @keydown.enter="emit('selectDay', visibleThreads.at(-1)?.day || null)"></canvas>
    <div class="weave-zoom" aria-label="调整织痕视图">
      <button type="button" :disabled="zoom <= 1" aria-label="看更多痕迹" @click="changeZoom(zoom - .5)">−</button>
      <button type="button" :disabled="zoom >= 4" aria-label="靠近最近痕迹" @click="changeZoom(zoom + .5)">＋</button>
    </div>
    <p class="sr-only">织痕布中保留着 {{ expandedThreads().length }} 根痕迹。</p>
  </div>
</template>

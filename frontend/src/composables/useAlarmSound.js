/**
 * 告警提示音：用 WebAudio 现场合成，不引入任何音频资源文件。
 * 静音开关持久化在 localStorage。
 */
import { ref } from 'vue'

const STORAGE_KEY = 'fsm.alarm.muted'

const muted = ref(window.localStorage.getItem(STORAGE_KEY) === '1')
let ctx = null

function ensureContext() {
  if (typeof window === 'undefined') return null
  const Ctor = window.AudioContext || window.webkitAudioContext
  if (!Ctor) return null
  if (!ctx) ctx = new Ctor()
  if (ctx.state === 'suspended') ctx.resume().catch(() => {})
  return ctx
}

function tone(ac, { freq, start, duration, gain = 0.14, type = 'sine' }) {
  const osc = ac.createOscillator()
  const amp = ac.createGain()
  osc.type = type
  osc.frequency.setValueAtTime(freq, start)
  amp.gain.setValueAtTime(0.0001, start)
  amp.gain.exponentialRampToValueAtTime(gain, start + 0.02)
  amp.gain.exponentialRampToValueAtTime(0.0001, start + duration)
  osc.connect(amp).connect(ac.destination)
  osc.start(start)
  osc.stop(start + duration + 0.03)
}

/** 播放一次告警提示音；critical 是两声更急促的高音。 */
function beep(level = 'warning') {
  if (muted.value) return
  const ac = ensureContext()
  if (!ac) return
  const t = ac.currentTime + 0.01
  if (level === 'critical') {
    tone(ac, { freq: 1046, start: t, duration: 0.16, gain: 0.16, type: 'triangle' })
    tone(ac, { freq: 1318, start: t + 0.2, duration: 0.2, gain: 0.16, type: 'triangle' })
  } else {
    tone(ac, { freq: 784, start: t, duration: 0.22, gain: 0.12, type: 'sine' })
  }
}

function setMuted(value) {
  muted.value = Boolean(value)
  window.localStorage.setItem(STORAGE_KEY, muted.value ? '1' : '0')
}

function toggleMuted() {
  setMuted(!muted.value)
}

export function useAlarmSound() {
  return {
    muted,
    setMuted,
    toggleMuted,
    beep,
    /** 用户手势里调用一次，解锁浏览器的音频自动播放限制。 */
    unlock: ensureContext,
  }
}

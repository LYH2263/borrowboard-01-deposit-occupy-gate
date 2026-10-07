<template>
  <div style="padding:16px;max-width:560px">
    <h1>占用档</h1>
    <p class="muted">策略：未确认占用即占住可借额度——占用期间物品停在可借栏、借还记录不增行，但他人不能借出或再占用。</p>
    <p v-if="error" class="error">{{ error }}</p>
    <h3>未确认占用</h3>
    <p v-if="!holds.length" class="muted">暂无</p>
    <div v-for="h in holds" :key="h.id" class="item">
      <strong>{{ h.title }}</strong> → {{ h.borrower }} × {{ h.qty }}
      <div class="muted">占用档 #{{ h.id }} · 物主 {{ h.owner || '—' }} · 应还 {{ h.due_date }}</div>
      <button @click="confirm(h.id)">确认借出</button>
      <button class="ghost" @click="cancel(h.id)">取消占用</button>
    </div>
  </div>
</template>
<script setup>
import { inject, ref, onMounted } from 'vue'
import { api } from '../api'
const reloadBoard = inject('reloadBoard')
const holds = ref([])
const error = ref('')
async function load() {
  holds.value = await api('/holds?open_only=true')
}
async function call(fn) {
  error.value = ''
  try {
    await fn()
    await load()
    await reloadBoard()
  } catch (e) {
    error.value = e.message
    await load()
  }
}
function confirm(id) {
  return call(() => api('/holds/' + id + '/confirm', { method: 'POST', body: '{}' }))
}
function cancel(id) {
  return call(() => api('/holds/' + id + '/cancel', { method: 'POST', body: '{}' }))
}
onMounted(load)
</script>

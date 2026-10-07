<template>
  <div class="split">
    <section class="pane">
      <h2>可借物</h2>
      <div v-for="i in board.available" :key="i.id" class="item" :class="{ occupied: i.occupancy }">
        <strong>{{ i.title }}</strong>
        <div class="muted">物主 {{ i.owner || '—' }}</div>
        <template v-if="i.occupancy">
          <div class="muted">占用中 · {{ i.occupancy.borrower }} · 数量 {{ i.occupancy.qty }} · 待确认</div>
          <router-link to="/occupancies">去占用列表确认 →</router-link>
        </template>
        <template v-else>
          <input v-model="forms[i.id].borrower" placeholder="借用人" />
          <input v-model="forms[i.id].due_date" placeholder="应还日 YYYY-MM-DD" />
          <input v-model.number="forms[i.id].qty" type="number" min="1" placeholder="数量" />
          <button @click="openOcc(i.id)">开占用档</button>
          <button @click="lend(i.id)">直接借出</button>
        </template>
      </div>
      <div v-if="err" class="err">{{ err }}</div>
    </section>
    <section class="pane">
      <h2>在借 / 逾期</h2>
      <div v-for="l in [...board.overdue, ...board.active]" :key="l.id" class="item" :class="{ overdue: l.overdue }">
        <strong>{{ l.title }}</strong> → {{ l.borrower }}
        <div class="muted">应还 {{ l.due_date }} {{ l.overdue ? '· 逾期' : '' }}</div>
        <button @click="ret(l.id)">归还</button>
      </div>
    </section>
  </div>
</template>
<script setup>
import { inject, reactive, ref, watch } from 'vue'
import { api } from '../api'
const board = inject('board')
const reload = inject('reloadBoard')
const forms = reactive({})
const err = ref('')
watch(board, (b) => {
  for (const i of (b.available || [])) {
    if (!forms[i.id]) forms[i.id] = { borrower: '邻居', due_date: '2026-12-31', qty: 1 }
  }
}, { immediate: true, deep: true })
async function run(fn) {
  err.value = ''
  try { await fn() } catch (e) { err.value = e.message }
  await reload()
}
async function openOcc(id) {
  await run(() => api('/items/' + id + '/occupancy', { method: 'POST', body: JSON.stringify(forms[id]) }))
}
async function lend(id) {
  await run(() => api('/items/' + id + '/lend', { method: 'POST', body: JSON.stringify(forms[id]) }))
}
async function ret(id) {
  await run(() => api('/loans/' + id + '/return', { method: 'POST', body: '{}' }))
}
</script>

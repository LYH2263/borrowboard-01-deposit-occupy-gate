<template>
  <div class="split">
    <section class="pane">
      <h2>待确认占用</h2>
      <div v-if="!data.pending.length" class="muted">暂无占用档</div>
      <div v-for="o in data.pending" :key="o.id" class="item occupied">
        <strong>{{ o.title }}</strong> → {{ o.borrower }}
        <div class="muted">数量 {{ o.qty }} · 应还 {{ o.due_date }} · 开档 {{ fmt(o.created_at) }}</div>
        <button @click="confirm(o.id)">确认借出</button>
      </div>
      <div v-if="err" class="err">{{ err }}</div>
    </section>
    <section class="pane">
      <h2>已确认</h2>
      <div v-if="!data.confirmed.length" class="muted">暂无</div>
      <div v-for="o in data.confirmed" :key="o.id" class="item">
        <strong>{{ o.title }}</strong> → {{ o.borrower }}
        <div class="muted">借单 #{{ o.loan_id }} · 确认 {{ fmt(o.confirmed_at) }}</div>
      </div>
    </section>
  </div>
</template>
<script setup>
import { ref, onMounted, inject } from 'vue'
import { api } from '../api'
const data = ref({ pending: [], confirmed: [] })
const err = ref('')
const reloadBoard = inject('reloadBoard')
async function load() { data.value = await api('/occupancies') }
async function confirm(id) {
  err.value = ''
  try {
    await api('/occupancies/' + id + '/confirm', { method: 'POST', body: '{}' })
    await Promise.all([load(), reloadBoard()])
  } catch (e) {
    err.value = '确认失败：' + e.message
    await Promise.all([load(), reloadBoard()])
  }
}
function fmt(s) { return (s || '').slice(0, 10) }
onMounted(load)
</script>

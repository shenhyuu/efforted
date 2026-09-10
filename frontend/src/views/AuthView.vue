<script setup lang="ts">
import { ref } from 'vue'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const password = ref('')
const busy = ref(false)
async function submit() {
  if (password.value.length < 6 || busy.value) return
  busy.value = true
  await session.enter(password.value)
  busy.value = false
}
</script>

<template>
  <main class="auth-page">
    <section class="auth-card">
      <span class="eyebrow">一处安静的地方</span>
      <h1>{{ session.initialized ? '欢迎回来。' : '先留一把钥匙。' }}</h1>
      <p>{{ session.initialized ? '这里还保留着你留下的痕迹。' : '密码只用来守住这台设备里的记录。' }}</p>
      <form @submit.prevent="submit">
        <label for="password">{{ session.initialized ? '密码' : '设置密码，至少六位' }}</label>
        <input id="password" v-model="password" type="password" minlength="6" maxlength="128" autocomplete="current-password">
        <button type="submit" :disabled="password.length < 6 || busy">{{ busy ? '正在打开' : '进入织痕' }}</button>
      </form>
      <p v-if="session.error" class="soft-error static-error">{{ session.error }}</p>
    </section>
  </main>
</template>

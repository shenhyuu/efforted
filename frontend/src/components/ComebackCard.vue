<script setup lang="ts">
import type { ComebackData } from '@/api'

defineProps<{ comeback: ComebackData }>()
const emit = defineEmits<{ choose: [choice: 'backfill' | 'fresh'] }>()
</script>

<template>
  <aside v-if="comeback.is_comeback && comeback.card" class="comeback-card" aria-labelledby="comeback-title">
    <span class="eyebrow">再次相遇</span>
    <h2 id="comeback-title">你回来了。</h2>
    <p>{{ comeback.card.last_left_hint }}</p>
    <p>{{ comeback.card.message }}</p>
    <div class="comeback-actions">
      <button type="button" @click="emit('choose', 'backfill')">补记那段时间</button>
      <button type="button" @click="emit('choose', 'fresh')">直接开始新的</button>
    </div>
  </aside>
</template>

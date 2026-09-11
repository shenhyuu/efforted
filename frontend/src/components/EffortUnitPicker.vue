<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '@/api'

const unit = defineModel<string | undefined>()
const custom = ref('')
const presets = ['读一页', '一道题', '一次出门', '一次深呼吸']
const remembered = ref<string[]>([])
const rememberedChoices = computed(() => remembered.value.filter((value) => !presets.includes(value)))

function choose(value: string) {
  unit.value = unit.value === value ? undefined : value
}

function useCustom() {
  unit.value = custom.value.trim() || undefined
}

onMounted(async () => {
  remembered.value = (await api.effortUnits().catch(() => ({ items: [] }))).items
})
</script>

<template>
  <fieldset class="effort-unit-picker">
    <legend>想给这根线一个说法 <small>可以不选</small></legend>
    <div class="choice-row">
      <button v-for="preset in presets" :key="preset" type="button"
        :class="{ selected: unit === preset }" @click="choose(preset)">{{ preset }}</button>
    </div>
    <div v-if="rememberedChoices.length" class="remembered-units">
      <small>你用过的说法</small>
      <div class="choice-row">
        <button v-for="value in rememberedChoices" :key="value" type="button"
          :class="{ selected: unit === value }" @click="choose(value)">{{ value }}</button>
      </div>
    </div>
    <details>
      <summary>写自己的说法</summary>
      <input v-model="custom" type="text" maxlength="40" placeholder="例如：打开了文档" @input="useCustom">
    </details>
  </fieldset>
</template>

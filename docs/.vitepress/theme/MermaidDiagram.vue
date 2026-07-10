<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import mermaid from 'mermaid'

const props = defineProps<{ code: string }>()
const html = ref('')
const error = ref('')

function source() {
  return decodeURIComponent(props.code)
}

mermaid.initialize({
  startOnLoad: false,
  securityLevel: 'loose',
  theme: 'dark',
  flowchart: {
    htmlLabels: true,
    padding: 14,
    nodeSpacing: 42,
    rankSpacing: 48
  },
  themeVariables: {
    primaryColor: '#151f2e',
    primaryTextColor: '#f8fafc',
    primaryBorderColor: '#dc1f2d',
    lineColor: '#8fb9bd',
    secondaryColor: '#172536',
    tertiaryColor: '#0b1018'
  }
})

async function renderDiagram() {
  error.value = ''
  try {
    const id = `mermaid-${Math.random().toString(36).slice(2)}`
    const result = await mermaid.render(id, source())
    html.value = result.svg
  } catch (err) {
    html.value = ''
    error.value = err instanceof Error ? err.message : String(err)
  }
}

onMounted(renderDiagram)
watch(() => props.code, renderDiagram)
</script>

<template>
  <div class="z-mermaid">
    <div v-if="html" v-html="html" />
    <pre v-else class="z-mermaid-error"><code>{{ error || source() }}</code></pre>
  </div>
</template>

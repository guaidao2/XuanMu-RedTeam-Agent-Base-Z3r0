import { inBrowser, onContentUpdated } from 'vitepress'
import DefaultTheme from 'vitepress/theme'
import mediumZoom from 'medium-zoom'
import type { Zoom } from 'medium-zoom'
import MermaidDiagram from './MermaidDiagram.vue'
import './styles/z3r0-theme.css'

let zoom: Zoom | undefined

function bindImageZoom() {
  if (!inBrowser) return

  zoom ??= mediumZoom({
    background: 'rgba(9, 13, 22, .92)',
    margin: 24,
    scrollOffset: 80
  })

  zoom.detach()
  zoom.attach('.vp-doc :not(a) > img:not(.no-zoom)')
}

export default {
  extends: DefaultTheme,
  enhanceApp({ app }) {
    app.component('MermaidDiagram', MermaidDiagram)
  },
  setup() {
    if (inBrowser) onContentUpdated(bindImageZoom)
  }
}

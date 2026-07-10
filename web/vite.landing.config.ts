import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";
import { renderLandingHtml } from "./src/landing-prerender";
import { landingSeo, getRobotsTxt, getSitemapXml, getWebManifest, structuredData } from "./landing.seo";

const logoEntryPath = "../src/assets/z3r0-logo.png";
const logoOutputPath = "assets/z3r0-logo.png";
const siteImageUrl = new URL(logoOutputPath, landingSeo.siteUrl).toString();

function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function buildMetaTags() {
  const tags = [
    `<title>${escapeHtml(landingSeo.title)}</title>`,
    `<meta name="description" content="${escapeHtml(landingSeo.description)}" />`,
    `<meta name="keywords" content="${escapeHtml(landingSeo.keywords.join(", "))}" />`,
    '<meta name="robots" content="index, follow, max-image-preview:large" />',
    '<meta name="author" content="Z3r0" />',
    '<meta name="theme-color" content="#d92d3a" />',
    `<link rel="canonical" href="${landingSeo.siteUrl}" />`,
    '<link rel="manifest" href="./site.webmanifest" />',
    `<meta property="og:site_name" content="${escapeHtml(landingSeo.siteName)}" />`,
    '<meta property="og:type" content="website" />',
    `<meta property="og:url" content="${landingSeo.siteUrl}" />`,
    `<meta property="og:title" content="${escapeHtml(landingSeo.title)}" />`,
    `<meta property="og:description" content="${escapeHtml(landingSeo.description)}" />`,
    `<meta property="og:image" content="${siteImageUrl}" />`,
    `<meta property="og:image:alt" content="${escapeHtml(landingSeo.imageAlt)}" />`,
    '<meta property="og:image:type" content="image/png" />',
    '<meta property="og:image:width" content="1000" />',
    '<meta property="og:image:height" content="1000" />',
    '<meta name="twitter:card" content="summary_large_image" />',
    `<meta name="twitter:title" content="${escapeHtml(landingSeo.title)}" />`,
    `<meta name="twitter:description" content="${escapeHtml(landingSeo.description)}" />`,
    `<meta name="twitter:image" content="${siteImageUrl}" />`,
    `<meta name="twitter:image:alt" content="${escapeHtml(landingSeo.imageAlt)}" />`,
    `<script type="application/ld+json">${JSON.stringify(structuredData)}</script>`,
  ];

  return tags.join("\n    ");
}

function landingSeoPlugin(): Plugin {
  return {
    name: "z3r0-landing-seo",
    transformIndexHtml(html) {
      return html
        .replace(/\s*<meta\s+name="description"[\s\S]*?\/>\s*/i, "\n")
        .replace(/\s*<title>[\s\S]*?<\/title>\s*/i, "\n")
        .replace("</head>", `    ${buildMetaTags()}\n  </head>`)
        .replace('<link rel="icon" type="image/png" href="../src/assets/z3r0-logo.png" />', `<link rel="icon" type="image/png" href="${logoEntryPath}" />`)
        .replace('<div id="root"></div>', `<div id="root">${renderLandingHtml(`./${logoOutputPath}`)}</div>`);
    },
    generateBundle() {
      this.emitFile({
        type: "asset",
        fileName: "robots.txt",
        source: getRobotsTxt(),
      });
      this.emitFile({
        type: "asset",
        fileName: "sitemap.xml",
        source: getSitemapXml(),
      });
      this.emitFile({
        type: "asset",
        fileName: "site.webmanifest",
        source: getWebManifest(`./${logoOutputPath}`),
      });
    },
  };
}

export default defineConfig({
  base: "./",
  root: "landing",
  plugins: [react(), landingSeoPlugin()],
  build: {
    outDir: "../dist-landing",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        assetFileNames(assetInfo) {
          if (assetInfo.name === "z3r0-logo.png") return logoOutputPath;
          return "assets/[name]-[hash][extname]";
        },
      },
    },
  },
});

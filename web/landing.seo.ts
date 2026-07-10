export const landingSeo = {
  siteUrl: "https://z3r0.fans/",
  siteName: "Z3r0",
  title: "Z3r0 - Red Team Collaboration Workbench for Authorized Security Work",
  description:
    "Z3r0 is an open-source red team collaboration workbench with multi-agent orchestration, WorkProject evidence records, distributed Docker sandboxes, controlled egress, and replayable timelines.",
  imagePath: "assets/z3r0-logo.png",
  imageAlt: "Z3r0 logo",
  keywords: [
    "Z3r0",
    "red team collaboration workbench",
    "multi-agent red team platform",
    "authorized penetration testing",
    "authorized pentesting",
    "vulnerability research",
    "vulnerability validation",
    "red team orchestration",
    "attack path analysis",
    "attack path replay",
    "sandboxed security tooling",
    "distributed Docker sandbox",
    "controlled egress",
    "proxy egress",
    "evidence records",
    "asset relationship graph",
    "WorkProject records",
    "code audit automation",
    "source code security audit",
    "dependency review",
    "security finding management",
    "agent orchestration",
    "reverse engineering automation",
    "cryptography review",
  ],
};

export const structuredData = [
  {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: landingSeo.siteName,
    applicationCategory: "SecurityApplication",
    operatingSystem: "Linux, Docker",
    url: landingSeo.siteUrl,
    image: new URL(landingSeo.imagePath, landingSeo.siteUrl).toString(),
    description: landingSeo.description,
    softwareRequirements: "Docker Engine, Docker Compose, PostgreSQL, model provider credentials",
    offers: {
      "@type": "Offer",
      price: "0",
      priceCurrency: "USD",
    },
    sameAs: ["https://github.com/yv1ing/Z3r0"],
  },
  {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: [
      {
        "@type": "Question",
        name: "What is Z3r0?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Z3r0 is an open-source red team collaboration workbench for authorized penetration testing, vulnerability discovery, code auditing, and security research.",
        },
      },
      {
        "@type": "Question",
        name: "Who is Z3r0 designed for?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Z3r0 is designed for authorized red teams, penetration testers, vulnerability researchers, internal security teams, code auditors, reverse engineers, cryptography reviewers, and controlled research environments.",
        },
      },
      {
        "@type": "Question",
        name: "How does Z3r0 run security tooling?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Z3r0 binds agent tools and manual review workflows to controlled Docker sandbox containers with command execution, file access, shell access, browser workflows, and noVNC review.",
        },
      },
      {
        "@type": "Question",
        name: "What environments should use Z3r0?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Z3r0 should be used only within lawful and explicitly authorized, trusted, and isolated environments where Docker access, model credentials, terminal access, and sandbox containers can be governed as high-privilege assets.",
        },
      },
    ],
  },
  {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      {
        "@type": "ListItem",
        position: 1,
        name: "Z3r0",
        item: landingSeo.siteUrl,
      },
    ],
  },
];

export function getRobotsTxt() {
  return [
    "User-agent: *",
    "Allow: /",
    "",
    `Sitemap: ${new URL("sitemap.xml", landingSeo.siteUrl).toString()}`,
    "",
  ].join("\n");
}

export function getSitemapXml() {
  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    "  <url>",
    `    <loc>${landingSeo.siteUrl}</loc>`,
    "    <changefreq>weekly</changefreq>",
    "    <priority>1.0</priority>",
    "  </url>",
    "</urlset>",
    "",
  ].join("\n");
}

export function getWebManifest(iconSrc: string) {
  return JSON.stringify(
    {
      name: "Z3r0",
      short_name: "Z3r0",
      description: landingSeo.description,
      start_url: "/",
      display: "standalone",
      background_color: "#090d16",
      theme_color: "#d92d3a",
      icons: [
        {
          src: iconSrc,
          sizes: "1000x1000",
          type: "image/png",
          purpose: "any",
        },
      ],
    },
    null,
    2,
  );
}

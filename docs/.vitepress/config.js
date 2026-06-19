import { defineConfig } from "vitepress";

export default defineConfig({
  title: "JalaAgent",
  description: "Open-source self-improving AI agent with hybrid memory",
  base: "/",
  cleanUrls: true,
  themeConfig: {
    nav: [
      { text: "Home", link: "/" },
      { text: "Guide", link: "/guide/quickstart" },
      { text: "Reference", link: "/reference/architecture" },
      { text: "Contributing", link: "/contributing" },
    ],
    sidebar: {
      "/guide/": [
        { text: "Quickstart", link: "/guide/quickstart" },
        { text: "User Guide", link: "/guide/user-guide" },
        { text: "Configuration", link: "/guide/configuration" },
        { text: "Providers", link: "/guide/providers" },
        { text: "Skills Catalog", link: "/guide/skills" },
        { text: "Commands Reference", link: "/guide/commands" },
        { text: "Authoring Skills", link: "/guide/authoring-skills" },
      ],
      "/reference/": [
        { text: "Architecture", link: "/reference/architecture" },
        { text: "Memory System", link: "/reference/memory" },
        { text: "Harness", link: "/reference/harness" },
        { text: "API Reference", link: "/reference/api-reference" },
      ],
    },
    socialLinks: [
      { icon: "github", link: "https://github.com/algojogacor/JalaAgent" },
    ],
    footer: {
      message: "Apache 2.0 Licensed",
      copyright: "Copyright 2026 JalaAgent",
    },
    search: {
      provider: "local",
    },
  },
});

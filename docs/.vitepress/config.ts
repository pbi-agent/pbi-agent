import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'pbi-agent',
  description: 'Multi-provider LLM CLI agent for Power BI report editing',
  base: '/pbi-agent/',
  cleanUrls: true,
  lastUpdated: true,
  themeConfig: {
    nav: [
      { text: 'Guide', link: '/guide/' },
      { text: 'Reference', link: '/reference/cli' },
      { text: 'GitHub', link: 'https://github.com/nasirus/pbi-agent' }
    ],
    sidebar: {
      '/guide/': [
        { text: 'Introduction', link: '/guide/' },
        { text: 'Installation', link: '/guide/installation' },
        { text: 'Providers', link: '/guide/providers' },
        { text: 'Audit System', link: '/guide/audit' }
      ],
      '/reference/': [
        { text: 'CLI Reference', link: '/reference/cli' },
        { text: 'Tools', link: '/reference/tools' },
        { text: 'Environment Variables', link: '/reference/environment' }
      ]
    },
    search: {
      provider: 'local'
    },
    socialLinks: [
      { icon: 'github', link: 'https://github.com/nasirus/pbi-agent' }
    ],
    footer: {
      message: 'Released under the MIT License.',
      copyright: 'Copyright © 2026 Nasir Ben Said'
    }
  }
})

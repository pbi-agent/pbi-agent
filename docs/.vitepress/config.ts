import { defineConfig, type HeadConfig } from 'vitepress'

const siteName = 'pbi-agent'
const siteDescription =
  'Multi-provider LLM CLI agent for Power BI report editing'
const siteBase = '/pbi-agent/'
const siteUrl = 'https://nasirus.github.io/pbi-agent/'
const socialImageUrl = new URL('social-card.jpg', siteUrl).toString()
const faviconUrl = `${siteBase}favicon.png`

function resolvePageUrl(page: string): string {
  if (page === 'index.md') {
    return siteUrl
  }

  const path = page.endsWith('/index.md')
    ? page.slice(0, -'index.md'.length)
    : page.replace(/\.md$/, '')

  return new URL(path, siteUrl).toString()
}

function resolveSocialTitle(title: string, page: string): string {
  if (page === 'index.md') {
    return 'pbi-agent docs for Power BI editing'
  }

  return `${title} | pbi-agent docs`
}

function buildSocialHead(
  page: string,
  title: string,
  description: string
): HeadConfig[] {
  const metaTitle = resolveSocialTitle(title || siteName, page)
  const metaDescription = description || siteDescription
  const pageUrl = resolvePageUrl(page)

  return [
    ['link', { rel: 'canonical', href: pageUrl }],
    ['meta', { property: 'og:type', content: 'website' }],
    ['meta', { property: 'og:site_name', content: siteName }],
    ['meta', { property: 'og:title', content: metaTitle }],
    ['meta', { property: 'og:description', content: metaDescription }],
    ['meta', { property: 'og:url', content: pageUrl }],
    ['meta', { property: 'og:image', content: socialImageUrl }],
    [
      'meta',
      { property: 'og:image:alt', content: 'pbi-agent documentation preview' }
    ],
    ['meta', { name: 'twitter:card', content: 'summary_large_image' }],
    ['meta', { name: 'twitter:title', content: metaTitle }],
    ['meta', { name: 'twitter:description', content: metaDescription }],
    ['meta', { name: 'twitter:image', content: socialImageUrl }]
  ]
}

export default defineConfig({
  title: siteName,
  description: siteDescription,
  lang: 'en-US',
  base: siteBase,
  cleanUrls: true,
  lastUpdated: true,
  head: [
    ['link', { rel: 'icon', type: 'image/png', href: faviconUrl }],
    ['link', { rel: 'apple-touch-icon', href: faviconUrl }],
    ['meta', { name: 'theme-color', content: '#0f172a' }]
  ],
  transformHead(context) {
    return buildSocialHead(
      context.page,
      context.pageData.title,
      context.description
    )
  },
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
      copyright: 'Copyright © 2026 pbi-agent contributors'
    }
  }
})

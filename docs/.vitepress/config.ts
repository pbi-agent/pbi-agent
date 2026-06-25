import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig, type HeadConfig } from 'vitepress'

const siteName = 'pbi-agent'
const siteDescription =
  'Local coding agent for skills, commands, agents, and multi-domain workflows'
const siteBase = '/pbi-agent/'
const siteUrl = 'https://pbi-agent.github.io/pbi-agent/'
const socialImageUrl = new URL('social-card.jpg', siteUrl).toString()
const faviconUrl = '/logo.jpg'
const docsDir = path.dirname(fileURLToPath(import.meta.url))
const sharedPublicDir = path.resolve(docsDir, '../../src/pbi_agent/web/static')

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
    return 'pbi-agent docs'
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
  titleTemplate: ':title | pbi-agent',
  description: siteDescription,
  lang: 'en-US',
  base: siteBase,
  cleanUrls: true,
  lastUpdated: true,
  srcExclude: ['**/README.md', '**/TODO.md'],
  head: [
    ['link', { rel: 'icon', type: 'image/jpeg', href: faviconUrl }],
    ['link', { rel: 'apple-touch-icon', href: faviconUrl }],
    ['meta', { name: 'theme-color', content: '#0f172a' }]
  ],
  markdown: {
    image: {
      lazyLoading: true
    }
  },
  vite: {
    publicDir: sharedPublicDir
  },
  transformHead(context) {
    return buildSocialHead(
      context.page,
      context.pageData.title,
      context.description
    )
  },
  themeConfig: {
    nav: [
      { text: 'Docs', link: '/introduction', activeMatch: '^/(introduction|installation|providers|web-ui|speech-to-text|session-commands|cli|sandbox|kanban-dashboard|model-profiles|customization|tools|extensions|environment|changelog)' },
      { text: 'Changelog', link: '/changelog/' },
      { text: 'GitHub', link: 'https://github.com/pbi-agent/pbi-agent' }
    ],
    sidebar: [
      {
        text: 'Getting Started',
        collapsed: false,
        items: [
          { text: 'Introduction', link: '/introduction' },
          { text: 'Installation', link: '/installation' },
          { text: 'Providers', link: '/providers' }
        ]
      },
      {
        text: 'Using pbi-agent',
        collapsed: false,
        items: [
          { text: 'Web UI', link: '/web-ui' },
          { text: 'Speech-to-text', link: '/speech-to-text' },
          { text: 'Session Commands', link: '/session-commands' },
          { text: 'CLI', link: '/cli' },
          { text: 'Docker Sandbox', link: '/sandbox' },
          { text: 'Kanban Dashboard', link: '/kanban-dashboard' },
          { text: 'Model Profiles', link: '/model-profiles' }
        ]
      },
      {
        text: 'Customizing',
        collapsed: false,
        items: [
          {
            text: 'Customization',
            link: '/customization/',
            items: [
              { text: 'Custom System Prompt', link: '/customization/instructions' },
              { text: 'Project Rules', link: '/customization/project-rules' },
              { text: 'Project Skills', link: '/customization/skills' },
              { text: 'Project Commands', link: '/customization/commands' },
              { text: 'Project Sub-agents', link: '/customization/sub-agents' },
              { text: 'Hooks', link: '/customization/hooks' },
              { text: 'Workspace Reload', link: '/customization/reload' },
              { text: 'MCP Servers', link: '/customization/mcp' },
              { text: 'File Constraints', link: '/customization/file-constraints' }
            ]
          },
          { text: 'Built-in Tools', link: '/tools' },
          { text: 'Python Extensions', link: '/extensions' },
          { text: 'Environment Variables', link: '/environment' }
        ]
      },
      {
        text: 'Release Notes',
        collapsed: false,
        items: [
        { text: 'Changelog', link: '/changelog/' },
        { text: 'v0.22.0', link: '/changelog/v0.22.0' },
        { text: 'v0.21.0', link: '/changelog/v0.21.0' },
          { text: 'v0.20.0', link: '/changelog/v0.20.0' },
          { text: 'v0.19.0', link: '/changelog/v0.19.0' },
          { text: 'v0.18.0', link: '/changelog/v0.18.0' },
          { text: 'v0.17.0', link: '/changelog/v0.17.0' },
          { text: 'v0.16.0', link: '/changelog/v0.16.0' },
          { text: 'v0.15.0', link: '/changelog/v0.15.0' },
          { text: 'v0.14.0', link: '/changelog/v0.14.0' },
          { text: 'v0.13.0', link: '/changelog/v0.13.0' },
          { text: 'v0.12.2', link: '/changelog/v0.12.2' },
          { text: 'v0.12.1', link: '/changelog/v0.12.1' },
          { text: 'v0.12.0', link: '/changelog/v0.12.0' },
          { text: 'v0.11.0', link: '/changelog/v0.11.0' },
          { text: 'v0.10.0', link: '/changelog/v0.10.0' },
          { text: 'v0.9.2', link: '/changelog/v0.9.2' },
          { text: 'v0.9.1', link: '/changelog/v0.9.1' },
          { text: 'v0.9.0', link: '/changelog/v0.9.0' },
          { text: 'v0.8.0', link: '/changelog/v0.8.0' },
          { text: 'v0.7.0', link: '/changelog/v0.7.0' },
          { text: 'v0.6.0', link: '/changelog/v0.6.0' },
          { text: 'v0.5.0', link: '/changelog/v0.5.0' },
          { text: 'v0.4.0', link: '/changelog/v0.4.0' },
          { text: 'v0.3.1', link: '/changelog/v0.3.1' },
          { text: 'v0.3.0', link: '/changelog/v0.3.0' },
          { text: 'v0.2.0', link: '/changelog/v0.2.0' },
          { text: 'v0.1.0', link: '/changelog/v0.1.0' },
          { text: 'v0.0.33', link: '/changelog/v0.0.33' }
        ]
      }
    ],
    outline: { level: [2, 3], label: 'On this page' },
    search: {
      provider: 'local'
    },
    externalLinkIcon: true,
    editLink: {
      pattern:
        'https://github.com/pbi-agent/pbi-agent/edit/master/docs/:path',
      text: 'Edit this page on GitHub'
    },
    socialLinks: [
      { icon: 'github', link: 'https://github.com/pbi-agent/pbi-agent' }
    ],
    footer: {
      message: 'Released under the MIT License.',
      copyright: 'Copyright © 2026 pbi-agent contributors'
    }
  }
})

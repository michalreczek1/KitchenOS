import type { MetadataRoute } from 'next'

export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: '*', allow: '/', disallow: '/?login=1' },
    sitemap: 'https://kitchenos.pl/sitemap.xml',
    host: 'https://kitchenos.pl',
  }
}

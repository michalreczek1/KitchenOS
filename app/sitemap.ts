import type { MetadataRoute } from 'next'

export default function sitemap(): MetadataRoute.Sitemap {
  return [{ url: 'https://kitchenos.pl/', changeFrequency: 'monthly', priority: 1 }]
}

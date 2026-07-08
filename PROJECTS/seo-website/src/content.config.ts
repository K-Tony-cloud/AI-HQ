import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const articles = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/articles' }),
  schema: z.object({
    article_id:          z.string(),
    keyword:             z.string(),
    category:            z.string().default(''),
    title:               z.string(),
    description:         z.string().default(''),
    product_ids:         z.array(z.number()).default([]),
    created_at:          z.string(),
    updated_at:          z.string(),
    last_product_sync:   z.string().optional(),
    article_status:      z.enum(['draft', 'reviewed', 'published', 'archived']).default('draft'),
    affiliate_disclosure: z.boolean().default(true),
    published_at:        z.string().optional(),
    canonical:           z.string().optional(),
  }),
});

export const collections = { articles };

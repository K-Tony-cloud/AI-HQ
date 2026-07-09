import { defineCollection, z } from 'astro:content';

const articles = defineCollection({
  type: 'content',
  schema: z.object({
    article_id:        z.string(),
    keyword:           z.string(),
    category:          z.string().default(''),
    category_label:    z.string().default(''),
    subcategory:       z.string().default(''),
    subcategory_label: z.string().default(''),
    title:             z.string(),
    description:       z.string().default(''),
    product_ids:       z.array(z.number()).default([]),
    created_at:        z.string().default(''),
    updated_at:        z.string().default(''),
    last_product_sync: z.string().optional(),
    published_at:      z.string().optional(),
    article_status:    z.string().default('draft'),
    affiliate_disclosure: z.boolean().default(true),
    canonical:         z.string().optional(),
  }),
});

export const collections = { articles };

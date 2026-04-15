import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const artworks = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/artworks' }),
  schema: ({ image }) =>
    z.object({
      title: z.string(),
      year: z.string(),
      medium: z.string(),
      dimensions: z.string(),
      widthCm: z.number().positive(),
      heightCm: z.number().positive(),
      category: z.enum(['figurative', 'abstract']),
      image: image(),
      order: z.number(),
      featured: z.boolean().default(false),
    }),
});

export const collections = { artworks };

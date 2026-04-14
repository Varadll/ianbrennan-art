// @ts-check
import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://ianbrennanart.com',
  image: {
    quality: 85,
  },
  prefetch: {
    prefetchAll: false,
    defaultStrategy: 'hover',
  },
});

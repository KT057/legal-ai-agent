import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { config as loadEnv } from 'dotenv';
import { z } from 'zod';

const here = fileURLToPath(import.meta.url);
loadEnv({ path: resolve(here, '../../../../.env') });
loadEnv();

const EnvSchema = z.object({
  BACKEND_PORT: z.coerce.number().default(3001),
  DATABASE_URL: z.string().url(),
  AI_SERVICE_URL: z.string().url().default('http://localhost:8000'),
});

export const env = EnvSchema.parse(process.env);
export type Env = z.infer<typeof EnvSchema>;

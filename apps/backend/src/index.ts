import { serve } from '@hono/node-server';
import { Hono } from 'hono';
import { cors } from 'hono/cors';
import { logger } from 'hono/logger';
import { env } from './env.js';
import { chatRouter } from './routes/chat.js';
import { contractsRouter } from './routes/contracts.js';

const app = new Hono();

app.use('*', logger());
app.use(
  '*',
  cors({
    origin: ['http://localhost:3000'],
    credentials: true,
  }),
);

app.get('/api/health', (c) => c.json({ status: 'ok' }));

const api = new Hono();
api.route('/contracts', contractsRouter);
api.route('/chat', chatRouter);
app.route('/api', api);

app.onError((err, c) => {
  console.error('[backend error]', err);
  const message =
    err.message || (err as { code?: string }).code || err.name || 'internal server error';
  return c.json({ error: message }, 500);
});

serve({ fetch: app.fetch, port: env.BACKEND_PORT }, (info) => {
  console.log(`[backend] listening on http://localhost:${info.port}`);
});

export type AppType = typeof api;

import { zValidator } from '@hono/zod-validator';
import type {
  ChatMessage,
  ChatThread,
  ChatThreadWithMessages,
  PostChatMessageResponse,
} from '@legal-ai-agent/shared-types';
import { asc, desc, eq } from 'drizzle-orm';
import { Hono } from 'hono';
import { z } from 'zod';
import { db } from '../db/client.js';
import { chatMessages, chatThreads } from '../db/schema.js';
import { chat as aiChat } from '../services/ai-client.js';

const createThreadSchema = z.object({
  title: z.string().min(1).max(200).optional(),
});

const postMessageSchema = z.object({
  content: z.string().min(1).max(10_000),
});

const toThread = (row: typeof chatThreads.$inferSelect): ChatThread => ({
  id: row.id,
  title: row.title,
  createdAt: row.createdAt.toISOString(),
});

const toMessage = (row: typeof chatMessages.$inferSelect): ChatMessage => ({
  id: row.id,
  threadId: row.threadId,
  role: row.role,
  content: row.content,
  createdAt: row.createdAt.toISOString(),
});

export const chatRouter = new Hono()
  .get('/threads', async (c) => {
    const rows = await db
      .select()
      .from(chatThreads)
      .orderBy(desc(chatThreads.createdAt));
    return c.json(rows.map(toThread));
  })
  .post('/threads', zValidator('json', createThreadSchema), async (c) => {
    const { title } = c.req.valid('json');
    const [row] = await db
      .insert(chatThreads)
      .values({ title: title ?? '新しい相談' })
      .returning();
    if (!row) throw new Error('failed to insert thread');
    return c.json(toThread(row));
  })
  .get('/threads/:id', async (c) => {
    const threadId = c.req.param('id');
    const [thread] = await db
      .select()
      .from(chatThreads)
      .where(eq(chatThreads.id, threadId));
    if (!thread) return c.notFound();

    const messages = await db
      .select()
      .from(chatMessages)
      .where(eq(chatMessages.threadId, threadId))
      .orderBy(asc(chatMessages.createdAt));

    const result: ChatThreadWithMessages = {
      ...toThread(thread),
      messages: messages.map(toMessage),
    };
    return c.json(result);
  })
  .post(
    '/threads/:id/messages',
    zValidator('json', postMessageSchema),
    async (c) => {
      const threadId = c.req.param('id');
      const { content } = c.req.valid('json');

      const [thread] = await db
        .select()
        .from(chatThreads)
        .where(eq(chatThreads.id, threadId));
      if (!thread) return c.notFound();

      const [userRow] = await db
        .insert(chatMessages)
        .values({ threadId, role: 'user', content })
        .returning();
      if (!userRow) throw new Error('failed to insert user message');

      const history = await db
        .select()
        .from(chatMessages)
        .where(eq(chatMessages.threadId, threadId))
        .orderBy(asc(chatMessages.createdAt));

      const aiResponse = await aiChat({
        messages: history.map((m) => ({ role: m.role, content: m.content })),
      });

      const [assistantRow] = await db
        .insert(chatMessages)
        .values({
          threadId,
          role: 'assistant',
          content: aiResponse.content,
        })
        .returning();
      if (!assistantRow) throw new Error('failed to insert assistant message');

      const result: PostChatMessageResponse = {
        userMessage: toMessage(userRow),
        assistantMessage: toMessage(assistantRow),
      };
      return c.json(result);
    },
  );

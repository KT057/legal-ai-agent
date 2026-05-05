import { zValidator } from '@hono/zod-validator';
import type {
  DraftPhase,
  DraftRisk,
  DraftSession,
  DraftSessionWithTurns,
  DraftTurn,
  DraftTurnMetadata,
  DraftTurnRole,
  GenerateDraftResponse,
  PostDraftHearingResponse,
  RequirementsDraft,
} from '@legal-ai-agent/shared-types';
import { asc, desc, eq } from 'drizzle-orm';
import { Hono } from 'hono';
import { z } from 'zod';
import { db } from '../db/client.js';
import { draftSessions, draftTurns } from '../db/schema.js';
import {
  draftGenerateFull,
  draftGenerateFullV2,
  draftHearingTurn,
  draftHearingTurnV2,
} from '../services/ai-client.js';

const createSessionSchema = z.object({
  title: z.string().min(1).max(200).optional(),
  engine: z.enum(['v1', 'v2']).optional(),
});

const postHearingSchema = z.object({
  content: z.string().min(1).max(10_000),
});

const toSession = (row: typeof draftSessions.$inferSelect): DraftSession => ({
  id: row.id,
  title: row.title,
  requirements: row.requirements,
  status: row.status,
  engine: row.engine,
  createdAt: row.createdAt.toISOString(),
  updatedAt: row.updatedAt.toISOString(),
});

const toTurn = (row: typeof draftTurns.$inferSelect): DraftTurn => ({
  id: row.id,
  sessionId: row.sessionId,
  phase: row.phase as DraftPhase,
  role: row.role as DraftTurnRole,
  content: row.content,
  metadata: (row.metadata as DraftTurnMetadata | null) ?? null,
  createdAt: row.createdAt.toISOString(),
});

export const draftsRouter = new Hono()
  .get('/sessions', async (c) => {
    const rows = await db.select().from(draftSessions).orderBy(desc(draftSessions.createdAt));
    return c.json(rows.map(toSession));
  })
  .post('/sessions', zValidator('json', createSessionSchema), async (c) => {
    const { title, engine } = c.req.valid('json');
    const [row] = await db
      .insert(draftSessions)
      .values({
        title: title ?? `新しい NDA ドラフト${engine === 'v2' ? ' [v2]' : ''}`,
        engine: engine ?? 'v1',
      })
      .returning();
    if (!row) throw new Error('failed to insert draft session');
    return c.json(toSession(row));
  })
  .get('/sessions/:id', async (c) => {
    const sessionId = c.req.param('id');
    const [session] = await db.select().from(draftSessions).where(eq(draftSessions.id, sessionId));
    if (!session) return c.notFound();

    const turns = await db
      .select()
      .from(draftTurns)
      .where(eq(draftTurns.sessionId, sessionId))
      .orderBy(asc(draftTurns.createdAt));

    const result: DraftSessionWithTurns = {
      ...toSession(session),
      turns: turns.map(toTurn),
    };
    return c.json(result);
  })
  .post('/sessions/:id/messages', zValidator('json', postHearingSchema), async (c) => {
    const sessionId = c.req.param('id');
    const { content } = c.req.valid('json');

    const [session] = await db.select().from(draftSessions).where(eq(draftSessions.id, sessionId));
    if (!session) return c.notFound();
    if (session.status === 'completed') {
      return c.json({ error: 'session is already completed; create a new session' }, 400);
    }

    const [userTurn] = await db
      .insert(draftTurns)
      .values({ sessionId, phase: 'hearing', role: 'user', content })
      .returning();
    if (!userTurn) throw new Error('failed to insert user turn');

    const allTurns = await db
      .select()
      .from(draftTurns)
      .where(eq(draftTurns.sessionId, sessionId))
      .orderBy(asc(draftTurns.createdAt));

    // hearing phase の (user/assistant) ターンだけを AI に渡す。
    // 直前で挿入した user turn は content として別途渡しているので除外。
    const history = allTurns
      .filter((t) => t.phase === 'hearing' && t.id !== userTurn.id)
      .map((t) => ({
        role: t.role === 'assistant' ? ('assistant' as const) : ('user' as const),
        content: t.content,
      }));

    // engine 別に v1 / v2 のクライアントを呼び分ける
    // (レスポンス shape は同一なので呼び出し側からは透過)
    const hearingFn = session.engine === 'v2' ? draftHearingTurnV2 : draftHearingTurn;
    const ai = await hearingFn({
      history,
      userMessage: content,
      currentRequirements: session.requirements,
    });

    const assistantMetadata: DraftTurnMetadata = {
      pendingQuestion: ai.pendingQuestion ?? undefined,
      missingField: (ai.missingField as keyof RequirementsDraft | null) ?? undefined,
    };

    const [assistantTurn] = await db
      .insert(draftTurns)
      .values({
        sessionId,
        phase: 'hearing',
        role: 'assistant',
        content: ai.assistantMessage,
        metadata: assistantMetadata,
      })
      .returning();
    if (!assistantTurn) throw new Error('failed to insert assistant turn');

    await db
      .update(draftSessions)
      .set({
        requirements: ai.requirements,
        status: ai.isComplete ? 'completed' : 'hearing',
        updatedAt: new Date(),
      })
      .where(eq(draftSessions.id, sessionId));

    const result: PostDraftHearingResponse = {
      userTurn: toTurn(userTurn),
      assistantTurn: toTurn(assistantTurn),
      requirements: ai.requirements,
      status: ai.isComplete ? 'completed' : 'hearing',
    };
    return c.json(result);
  })
  .post('/sessions/:id/generate', async (c) => {
    const sessionId = c.req.param('id');
    const [session] = await db.select().from(draftSessions).where(eq(draftSessions.id, sessionId));
    if (!session) return c.notFound();

    const generateFn = session.engine === 'v2' ? draftGenerateFullV2 : draftGenerateFull;
    const ai = await generateFn({ requirements: session.requirements });

    // 3 phase 分の turn を一括 insert (順番が崩れないよう createdAt を 1ms ずつ後ろにずらす)。
    const baseTime = new Date();
    const turnsToInsert = [
      {
        sessionId,
        phase: 'draft' as DraftPhase,
        role: 'assistant' as DraftTurnRole,
        content: ai.draftV1,
        metadata: null,
        createdAt: new Date(baseTime.getTime()),
      },
      {
        sessionId,
        phase: 'review' as DraftPhase,
        role: 'assistant' as DraftTurnRole,
        content: ai.reviewSummary,
        metadata: { risks: ai.risks satisfies DraftRisk[] } as DraftTurnMetadata,
        createdAt: new Date(baseTime.getTime() + 1),
      },
      {
        sessionId,
        phase: 'revised' as DraftPhase,
        role: 'assistant' as DraftTurnRole,
        content: ai.finalDraft,
        metadata: null,
        createdAt: new Date(baseTime.getTime() + 2),
      },
    ];

    const inserted = await db.insert(draftTurns).values(turnsToInsert).returning();
    const [draftV1Row, reviewRow, finalRow] = inserted;
    if (!draftV1Row || !reviewRow || !finalRow) {
      throw new Error('failed to insert generate turns');
    }

    await db
      .update(draftSessions)
      .set({ status: 'completed', updatedAt: new Date() })
      .where(eq(draftSessions.id, sessionId));

    const result: GenerateDraftResponse = {
      draftV1Turn: toTurn(draftV1Row),
      reviewTurn: toTurn(reviewRow),
      finalTurn: toTurn(finalRow),
    };
    return c.json(result);
  });

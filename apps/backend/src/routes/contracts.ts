import { zValidator } from '@hono/zod-validator';
import type { ContractReviewResult, ContractRisk } from '@legal-ai-agent/shared-types';
import { desc, eq } from 'drizzle-orm';
import { Hono } from 'hono';
import { z } from 'zod';
import { db } from '../db/client.js';
import { contractReviews, contracts } from '../db/schema.js';
import { reviewContract } from '../services/ai-client.js';

const reviewBodySchema = z.object({
  title: z.string().min(1).max(200),
  body: z.string().min(1).max(200_000),
});

export const contractsRouter = new Hono()
  .post('/review', zValidator('json', reviewBodySchema), async (c) => {
    const { title, body } = c.req.valid('json');

    const [contract] = await db.insert(contracts).values({ title, body }).returning();
    if (!contract) throw new Error('failed to insert contract');

    const aiResult = await reviewContract({ title, body });

    const [review] = await db
      .insert(contractReviews)
      .values({
        contractId: contract.id,
        model: aiResult.model,
        summary: aiResult.summary,
        risks: aiResult.risks satisfies ContractRisk[],
      })
      .returning();
    if (!review) throw new Error('failed to insert review');

    const result: ContractReviewResult = {
      reviewId: review.id,
      contractId: contract.id,
      model: review.model,
      summary: review.summary,
      risks: review.risks,
      createdAt: review.createdAt.toISOString(),
    };
    return c.json(result);
  })
  .get('/:id/reviews', async (c) => {
    const contractId = c.req.param('id');
    const rows = await db
      .select()
      .from(contractReviews)
      .where(eq(contractReviews.contractId, contractId))
      .orderBy(desc(contractReviews.createdAt));

    return c.json(
      rows.map<ContractReviewResult>((r) => ({
        reviewId: r.id,
        contractId: r.contractId,
        model: r.model,
        summary: r.summary,
        risks: r.risks,
        createdAt: r.createdAt.toISOString(),
      })),
    );
  });

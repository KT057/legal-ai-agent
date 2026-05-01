import type { ContractReviewResult, ContractRisk } from '@legal-ai-agent/shared-types';
import { desc, eq } from 'drizzle-orm';
import { Hono } from 'hono';
import { db } from '../db/client.js';
import { contractReviews, contracts } from '../db/schema.js';
import { reviewContract } from '../services/ai-client.js';

const MAX_TITLE_LEN = 200;
const MAX_BODY_LEN = 200_000;
const MAX_PDF_BYTES = 10 * 1024 * 1024;
const ALLOWED_PDF_MIME = new Set(['application/pdf', 'application/x-pdf']);

export const contractsRouter = new Hono()
  .post('/review', async (c) => {
    const form = await c.req.parseBody({ all: false });
    const title = typeof form.title === 'string' ? form.title.trim() : '';
    if (!title || title.length > MAX_TITLE_LEN) {
      return c.json({ error: `title is required (1-${MAX_TITLE_LEN} chars)` }, 400);
    }

    const rawBody = typeof form.body === 'string' ? form.body : '';
    const fileField = form.file;
    const file = fileField instanceof File && fileField.size > 0 ? fileField : null;

    if (!file && !rawBody.trim()) {
      return c.json({ error: "either 'body' or 'file' is required" }, 400);
    }
    if (file) {
      if (file.size > MAX_PDF_BYTES) {
        return c.json({ error: `PDF too large (max ${MAX_PDF_BYTES} bytes)` }, 400);
      }
      if (file.type && !ALLOWED_PDF_MIME.has(file.type)) {
        return c.json({ error: `unsupported file type: ${file.type} (PDF only)` }, 400);
      }
    }
    if (!file && rawBody.length > MAX_BODY_LEN) {
      return c.json({ error: `body too long (max ${MAX_BODY_LEN} chars)` }, 400);
    }

    // 契約レコード本体は AI 抽出後のテキストで保存したいが、PDF の場合は AI に投げないと
    // テキストが手に入らない。先に AI を呼んで、戻ってきたテキスト（=リクエスト本文）と
    // model 出力の両方を保存する設計でも良いが、現状 contracts.body は元入力を保持する
    // 役割なので、PDF の場合は filename を body 代替として保存する（最小変更）。
    const placeholderBody = file ? `[PDF] ${file.name}` : rawBody;
    const [contract] = await db
      .insert(contracts)
      .values({ title, body: placeholderBody })
      .returning();
    if (!contract) throw new Error('failed to insert contract');

    const aiResult = await reviewContract({
      title,
      body: file ? undefined : rawBody,
      file: file ? { blob: file, filename: file.name } : undefined,
    });

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

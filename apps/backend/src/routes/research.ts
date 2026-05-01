import { zValidator } from '@hono/zod-validator';
import type { ResearchResult } from '@legal-ai-agent/shared-types';
import { Hono } from 'hono';
import { z } from 'zod';
import { research } from '../services/ai-client.js';

const researchSchema = z.object({
  question: z.string().min(1).max(4000),
});

export const researchRouter = new Hono().post(
  '/',
  zValidator('json', researchSchema),
  async (c) => {
    const { question } = c.req.valid('json');
    const ai = await research({ question });
    const result: ResearchResult = {
      model: ai.model,
      content: ai.content,
      iterations: ai.iterations,
      citations: ai.citations.map((cite) => ({
        lawId: cite.law_id,
        lawTitle: cite.law_title,
        lawNum: cite.law_num,
        articleNo: cite.article_no,
        articleTitle: cite.article_title,
        body: cite.body,
        sourceUrl: cite.source_url,
        score: cite.score,
      })),
    };
    return c.json(result);
  },
);

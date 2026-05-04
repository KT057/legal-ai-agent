import { sql } from 'drizzle-orm';
import {
  bigserial,
  date,
  index,
  integer,
  jsonb,
  pgTable,
  text,
  timestamp,
  uuid,
  vector,
} from 'drizzle-orm/pg-core';
import type {
  ContractRisk,
  DraftPhase,
  DraftTurnMetadata,
  DraftTurnRole,
  RequirementsDraft,
} from '@legal-ai-agent/shared-types';

export const contracts = pgTable('contracts', {
  id: uuid('id')
    .primaryKey()
    .default(sql`gen_random_uuid()`),
  title: text('title').notNull(),
  body: text('body').notNull(),
  createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
});

export const contractReviews = pgTable('contract_reviews', {
  id: uuid('id')
    .primaryKey()
    .default(sql`gen_random_uuid()`),
  contractId: uuid('contract_id')
    .notNull()
    .references(() => contracts.id, { onDelete: 'cascade' }),
  model: text('model').notNull(),
  summary: text('summary').notNull(),
  risks: jsonb('risks').$type<ContractRisk[]>().notNull(),
  createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
});

export const chatThreads = pgTable('chat_threads', {
  id: uuid('id')
    .primaryKey()
    .default(sql`gen_random_uuid()`),
  title: text('title').notNull(),
  createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
});

export const chatMessages = pgTable('chat_messages', {
  id: uuid('id')
    .primaryKey()
    .default(sql`gen_random_uuid()`),
  threadId: uuid('thread_id')
    .notNull()
    .references(() => chatThreads.id, { onDelete: 'cascade' }),
  role: text('role', { enum: ['user', 'assistant'] }).notNull(),
  content: text('content').notNull(),
  createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
});

export const lawDocuments = pgTable('law_documents', {
  id: text('id').primaryKey(),
  lawNum: text('law_num').notNull(),
  title: text('title').notNull(),
  lawType: text('law_type').notNull(),
  promulgationDate: date('promulgation_date'),
  sourceUrl: text('source_url').notNull(),
  rawXml: text('raw_xml'),
  fetchedAt: timestamp('fetched_at', { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp('updated_at', { withTimezone: true }).notNull().defaultNow(),
});

export const draftSessions = pgTable('draft_sessions', {
  id: uuid('id')
    .primaryKey()
    .default(sql`gen_random_uuid()`),
  title: text('title').notNull(),
  requirements: jsonb('requirements').$type<RequirementsDraft>().notNull().default({}),
  status: text('status', { enum: ['hearing', 'completed'] })
    .notNull()
    .default('hearing'),
  createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp('updated_at', { withTimezone: true }).notNull().defaultNow(),
});

export const draftTurns = pgTable(
  'draft_turns',
  {
    id: uuid('id')
      .primaryKey()
      .default(sql`gen_random_uuid()`),
    sessionId: uuid('session_id')
      .notNull()
      .references(() => draftSessions.id, { onDelete: 'cascade' }),
    phase: text('phase', { enum: ['hearing', 'draft', 'review', 'revised'] })
      .$type<DraftPhase>()
      .notNull(),
    role: text('role', { enum: ['user', 'assistant', 'system'] })
      .$type<DraftTurnRole>()
      .notNull(),
    content: text('content').notNull(),
    metadata: jsonb('metadata').$type<DraftTurnMetadata>(),
    createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => ({
    sessionIdIdx: index('draft_turns_session_id_idx').on(table.sessionId),
  }),
);

export const lawChunks = pgTable(
  'law_chunks',
  {
    id: bigserial('id', { mode: 'bigint' }).primaryKey(),
    lawId: text('law_id')
      .notNull()
      .references(() => lawDocuments.id, { onDelete: 'cascade' }),
    articleNo: text('article_no'),
    articleTitle: text('article_title'),
    body: text('body').notNull(),
    tokenCount: integer('token_count').notNull(),
    embedding: vector('embedding', { dimensions: 1024 }).notNull(),
    createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => ({
    lawIdIdx: index('law_chunks_law_id_idx').on(table.lawId),
    embeddingHnswIdx: index('law_chunks_embedding_hnsw')
      .using('hnsw', table.embedding.op('vector_cosine_ops'))
      .with({ m: 16, ef_construction: 64 }),
  }),
);

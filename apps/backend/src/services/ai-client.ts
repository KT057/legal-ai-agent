import type {
  ChatMessage,
  ContractRisk,
  DraftRisk,
  RequirementsDraft,
} from '@legal-ai-agent/shared-types';
import { env } from '../env.js';

export interface AiContractReviewResponse {
  model: string;
  summary: string;
  risks: ContractRisk[];
}

export interface AiChatResponse {
  model: string;
  content: string;
}

export async function reviewContract(input: {
  title: string;
  body?: string;
  file?: { blob: Blob; filename: string };
}): Promise<AiContractReviewResponse> {
  const form = new FormData();
  form.append('title', input.title);
  if (input.file) {
    form.append('file', input.file.blob, input.file.filename);
  } else if (input.body) {
    form.append('body', input.body);
  }
  const res = await fetch(`${env.AI_SERVICE_URL}/review`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) {
    throw new Error(`AI service /review failed: ${res.status} ${await res.text()}`);
  }
  return (await res.json()) as AiContractReviewResponse;
}

export async function chat(input: {
  messages: Pick<ChatMessage, 'role' | 'content'>[];
}): Promise<AiChatResponse> {
  const res = await fetch(`${env.AI_SERVICE_URL}/chat`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    throw new Error(`AI service /chat failed: ${res.status} ${await res.text()}`);
  }
  return (await res.json()) as AiChatResponse;
}

export interface AiResearchCitation {
  law_id: string;
  law_title: string;
  law_num: string;
  article_no: string | null;
  article_title: string | null;
  body: string;
  source_url: string;
  score: number;
}

export interface AiResearchResponse {
  model: string;
  content: string;
  iterations: number;
  citations: AiResearchCitation[];
}

const RESEARCH_MAX_ITERATIONS = 5;

export async function research(input: { question: string }): Promise<AiResearchResponse> {
  const res = await fetch(`${env.AI_SERVICE_URL}/research`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      question: input.question,
      max_iterations: RESEARCH_MAX_ITERATIONS,
    }),
  });
  if (!res.ok) {
    throw new Error(`AI service /research failed: ${res.status} ${await res.text()}`);
  }
  return (await res.json()) as AiResearchResponse;
}

export interface AiDraftHearingResponse {
  model: string;
  assistantMessage: string;
  requirements: RequirementsDraft;
  isComplete: boolean;
  pendingQuestion: string | null;
  missingField: string | null;
}

export async function draftHearingTurn(input: {
  history: { role: 'user' | 'assistant'; content: string }[];
  userMessage: string;
  currentRequirements: RequirementsDraft;
}): Promise<AiDraftHearingResponse> {
  const res = await fetch(`${env.AI_SERVICE_URL}/draft/hearing`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      history: input.history,
      userMessage: input.userMessage,
      currentRequirements: input.currentRequirements,
    }),
  });
  if (!res.ok) {
    throw new Error(`AI service /draft/hearing failed: ${res.status} ${await res.text()}`);
  }
  return (await res.json()) as AiDraftHearingResponse;
}

export interface AiDraftGenerateResponse {
  model: string;
  draftV1: string;
  risks: DraftRisk[];
  reviewSummary: string;
  finalDraft: string;
  latencyMs: number;
}

export async function draftGenerateFull(input: {
  requirements: RequirementsDraft;
}): Promise<AiDraftGenerateResponse> {
  const res = await fetch(`${env.AI_SERVICE_URL}/draft/generate`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ requirements: input.requirements }),
  });
  if (!res.ok) {
    throw new Error(`AI service /draft/generate failed: ${res.status} ${await res.text()}`);
  }
  return (await res.json()) as AiDraftGenerateResponse;
}

// ─── v2 (LangGraph) 版 ──────────────────────────────────────────────
// レスポンス shape は v1 と完全に同じ。エンドポイントだけ /draft-v2/* に向ける。

export async function draftHearingTurnV2(input: {
  history: { role: 'user' | 'assistant'; content: string }[];
  userMessage: string;
  currentRequirements: RequirementsDraft;
}): Promise<AiDraftHearingResponse> {
  const res = await fetch(`${env.AI_SERVICE_URL}/draft-v2/hearing`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      history: input.history,
      userMessage: input.userMessage,
      currentRequirements: input.currentRequirements,
    }),
  });
  if (!res.ok) {
    throw new Error(`AI service /draft-v2/hearing failed: ${res.status} ${await res.text()}`);
  }
  return (await res.json()) as AiDraftHearingResponse;
}

export async function draftGenerateFullV2(input: {
  requirements: RequirementsDraft;
}): Promise<AiDraftGenerateResponse> {
  const res = await fetch(`${env.AI_SERVICE_URL}/draft-v2/generate`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ requirements: input.requirements }),
  });
  if (!res.ok) {
    throw new Error(`AI service /draft-v2/generate failed: ${res.status} ${await res.text()}`);
  }
  return (await res.json()) as AiDraftGenerateResponse;
}

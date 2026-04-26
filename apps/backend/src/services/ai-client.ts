import type { ChatMessage, ContractRisk } from '@legal-ai-agent/shared-types';
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
  body: string;
}): Promise<AiContractReviewResponse> {
  const res = await fetch(`${env.AI_SERVICE_URL}/review`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(input),
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

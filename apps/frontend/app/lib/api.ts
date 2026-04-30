import type {
  ChatThread,
  ChatThreadWithMessages,
  ContractReviewResult,
  PostChatMessageResponse,
} from '@legal-ai-agent/shared-types';

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:3001';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      'content-type': 'application/json',
      ...init?.headers,
    },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${path} failed: ${res.status} ${text}`);
  }
  return (await res.json()) as T;
}

export const api = {
  reviewContract: (input: { title: string; body: string }) =>
    request<ContractReviewResult>('/api/contracts/review', {
      method: 'POST',
      body: JSON.stringify(input),
    }),
  listThreads: () => request<ChatThread[]>('/api/chat/threads'),
  createThread: (input: { title?: string }) =>
    request<ChatThread>('/api/chat/threads', {
      method: 'POST',
      body: JSON.stringify(input),
    }),
  getThread: (id: string) => request<ChatThreadWithMessages>(`/api/chat/threads/${id}`),
  postMessage: (threadId: string, content: string) =>
    request<PostChatMessageResponse>(`/api/chat/threads/${threadId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    }),
};

import type {
  ChatThread,
  ChatThreadWithMessages,
  ContractReviewResult,
  PostChatMessageResponse,
  ResearchResult,
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

async function requestMultipart<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${path} failed: ${res.status} ${text}`);
  }
  return (await res.json()) as T;
}

export const api = {
  reviewContract: (input: { title: string; body?: string; file?: File }) => {
    const form = new FormData();
    form.append('title', input.title);
    if (input.file) {
      form.append('file', input.file, input.file.name);
    } else if (input.body) {
      form.append('body', input.body);
    }
    return requestMultipart<ContractReviewResult>('/api/contracts/review', form);
  },
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
  postResearch: (input: { question: string }) =>
    request<ResearchResult>('/api/research', {
      method: 'POST',
      body: JSON.stringify(input),
    }),
};

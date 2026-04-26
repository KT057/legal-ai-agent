export type RiskSeverity = 'low' | 'medium' | 'high';

export interface ContractRisk {
  clause: string;
  severity: RiskSeverity;
  reason: string;
  suggestion: string;
}

export interface ContractReviewRequest {
  title: string;
  body: string;
}

export interface ContractReviewResult {
  reviewId: string;
  contractId: string;
  model: string;
  summary: string;
  risks: ContractRisk[];
  createdAt: string;
}

export type ChatRole = 'user' | 'assistant';

export interface ChatMessage {
  id: string;
  threadId: string;
  role: ChatRole;
  content: string;
  createdAt: string;
}

export interface ChatThread {
  id: string;
  title: string;
  createdAt: string;
}

export interface ChatThreadWithMessages extends ChatThread {
  messages: ChatMessage[];
}

export interface CreateChatThreadRequest {
  title?: string;
}

export interface PostChatMessageRequest {
  content: string;
}

export interface PostChatMessageResponse {
  userMessage: ChatMessage;
  assistantMessage: ChatMessage;
}

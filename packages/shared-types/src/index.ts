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

export interface ResearchCitation {
  lawId: string;
  lawTitle: string;
  lawNum: string;
  articleNo: string | null;
  articleTitle: string | null;
  body: string;
  sourceUrl: string;
  score: number;
}

export interface ResearchRequest {
  question: string;
}

export interface ResearchResult {
  model: string;
  content: string;
  iterations: number;
  citations: ResearchCitation[];
}

export type DraftPhase = 'hearing' | 'draft' | 'review' | 'revised';
export type DraftTurnRole = 'user' | 'assistant' | 'system';
export type DraftStatus = 'hearing' | 'completed';

export interface RequirementsDraft {
  disclosingParty?: string;
  receivingParty?: string;
  purpose?: string;
  confidentialInfoScope?: string;
  termMonths?: number;
  governingLaw?: string;
}

export const REQUIREMENT_FIELDS: ReadonlyArray<keyof RequirementsDraft> = [
  'disclosingParty',
  'receivingParty',
  'purpose',
  'confidentialInfoScope',
  'termMonths',
  'governingLaw',
] as const;

export interface DraftRisk {
  clause: string;
  severity: RiskSeverity;
  reason: string;
  suggestion: string;
}

export interface DraftTurnMetadata {
  risks?: DraftRisk[];
  citations?: ResearchCitation[];
  pendingQuestion?: string;
  missingField?: keyof RequirementsDraft;
}

export interface DraftSession {
  id: string;
  title: string;
  requirements: RequirementsDraft;
  status: DraftStatus;
  createdAt: string;
  updatedAt: string;
}

export interface DraftTurn {
  id: string;
  sessionId: string;
  phase: DraftPhase;
  role: DraftTurnRole;
  content: string;
  metadata: DraftTurnMetadata | null;
  createdAt: string;
}

export interface DraftSessionWithTurns extends DraftSession {
  turns: DraftTurn[];
}

export interface CreateDraftSessionRequest {
  title?: string;
}

export interface PostDraftHearingRequest {
  content: string;
}

export interface PostDraftHearingResponse {
  userTurn: DraftTurn;
  assistantTurn: DraftTurn;
  requirements: RequirementsDraft;
  status: DraftStatus;
}

export interface GenerateDraftResponse {
  draftV1Turn: DraftTurn;
  reviewTurn: DraftTurn;
  finalTurn: DraftTurn;
}

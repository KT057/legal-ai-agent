import {
  REQUIREMENT_FIELDS,
  type DraftRisk,
  type DraftSessionWithTurns,
  type DraftTurn,
  type RequirementsDraft,
  type RiskSeverity,
} from '@legal-ai-agent/shared-types';
import { Fragment } from 'react';
import { Form, Link, redirect, useLoaderData, useNavigation } from 'react-router';
import { api } from '~/lib/api';
import type { Route } from './+types/draft';

export function meta() {
  return [{ title: 'NDA ドラフト生成 — Legal AI Agent' }];
}

const FIELD_LABELS_JA: Record<keyof RequirementsDraft, string> = {
  disclosingParty: '開示者 (秘密情報を渡す側)',
  receivingParty: '受領者 (秘密情報を受け取る側)',
  purpose: '開示目的',
  confidentialInfoScope: '秘密情報の範囲',
  termMonths: '有効期間 (月)',
  governingLaw: '準拠法',
};

export async function loader({ request }: Route.LoaderArgs) {
  const url = new URL(request.url);
  const sessionId = url.searchParams.get('session');
  const sessions = await api.listDraftSessions();
  const active = sessionId ? await api.getDraftSession(sessionId).catch(() => null) : null;
  return { sessions, active };
}

export async function action({ request }: Route.ActionArgs) {
  const formData = await request.formData();
  const intent = String(formData.get('intent') ?? '');

  if (intent === 'create-session') {
    const title = String(formData.get('title') ?? '').trim() || undefined;
    const session = await api.createDraftSession({ title });
    return redirect(`/draft?session=${session.id}`);
  }

  if (intent === 'send-message') {
    const sessionId = String(formData.get('sessionId') ?? '');
    const content = String(formData.get('content') ?? '').trim();
    if (!sessionId || !content) {
      return redirect(`/draft?session=${sessionId}`);
    }
    await api.postDraftMessage(sessionId, content);
    return redirect(`/draft?session=${sessionId}`);
  }

  if (intent === 'generate') {
    const sessionId = String(formData.get('sessionId') ?? '');
    if (!sessionId) {
      return redirect('/draft');
    }
    await api.generateDraft(sessionId);
    return redirect(`/draft?session=${sessionId}`);
  }

  return null;
}

export default function DraftRoute() {
  const { sessions, active } = useLoaderData<typeof loader>();
  const navigation = useNavigation();
  const isBusy = navigation.state !== 'idle';

  return (
    <main
      style={{
        display: 'grid',
        gridTemplateColumns: '260px 1fr',
        gap: 16,
        maxWidth: 1200,
        margin: '24px auto',
        padding: '0 24px',
        height: 'calc(100vh - 48px)',
      }}
    >
      <aside
        style={{
          background: '#fff',
          border: '1px solid #e5e7eb',
          borderRadius: 8,
          padding: 12,
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          overflow: 'auto',
        }}
      >
        <Link to="/" style={{ color: '#2563eb', fontSize: 13 }}>
          ← ホーム
        </Link>
        <Form method="post">
          <input type="hidden" name="intent" value="create-session" />
          <button type="submit" style={primaryButton}>
            + 新規セッション
          </button>
        </Form>
        <div style={{ display: 'grid', gap: 4, marginTop: 8 }}>
          {sessions.map((s) => (
            <Link
              key={s.id}
              to={`/draft?session=${s.id}`}
              style={{
                display: 'block',
                padding: '8px 10px',
                borderRadius: 6,
                textDecoration: 'none',
                color: 'inherit',
                background: active?.id === s.id ? '#eef2ff' : 'transparent',
                fontSize: 14,
              }}
            >
              <div style={{ fontWeight: 600 }}>{s.title}</div>
              <div style={{ fontSize: 11, color: '#6b7280' }}>
                {s.status === 'completed' ? '完了' : 'ヒアリング中'}
              </div>
            </Link>
          ))}
          {sessions.length === 0 && (
            <span style={{ fontSize: 13, color: '#9ca3af', padding: 8 }}>
              セッションはまだありません
            </span>
          )}
        </div>
      </aside>

      <section
        style={{
          background: '#fff',
          border: '1px solid #e5e7eb',
          borderRadius: 8,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {active ? (
          <ActiveSession session={active} isBusy={isBusy} />
        ) : (
          <div style={{ padding: 24, color: '#6b7280' }}>
            左から既存セッションを選ぶか、「+ 新規セッション」を押してください。
            <br />
            まず NDA の要件をヒアリングし、揃ったら「ドラフトを生成」で draft → セルフレビュー →
            修正版 を一気に生成します。
          </div>
        )}
      </section>
    </main>
  );
}

function ActiveSession({ session, isBusy }: { session: DraftSessionWithTurns; isBusy: boolean }) {
  const hearingTurns = session.turns.filter((t) => t.phase === 'hearing');
  const draftTurn = session.turns.find((t) => t.phase === 'draft');
  const reviewTurn = session.turns.find((t) => t.phase === 'review');
  const revisedTurn = session.turns.find((t) => t.phase === 'revised');
  const requirementsComplete = REQUIREMENT_FIELDS.every((k) => isFilled(session.requirements[k]));
  const hasGenerated = !!draftTurn;

  return (
    <>
      <header
        style={{
          padding: '12px 16px',
          borderBottom: '1px solid #e5e7eb',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <div style={{ fontWeight: 600 }}>{session.title}</div>
        <div style={{ fontSize: 12, color: '#6b7280' }}>
          status: <strong>{session.status}</strong>
        </div>
      </header>

      <div
        style={{
          flex: 1,
          overflow: 'auto',
          padding: 16,
          display: 'flex',
          flexDirection: 'column',
          gap: 16,
        }}
      >
        <RequirementsPanel requirements={session.requirements} />

        <section>
          <SectionTitle>ヒアリング</SectionTitle>
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 12,
              marginTop: 8,
            }}
          >
            {hearingTurns.map((t) => (
              <Bubble key={t.id} turn={t} />
            ))}
            {hearingTurns.length === 0 && (
              <div style={{ color: '#9ca3af', fontSize: 13 }}>
                最初のメッセージを送信してください (例:
                「AIスタートアップA社と事業会社B社の共同検証用 NDA を作りたい」)
              </div>
            )}
          </div>
        </section>

        {hasGenerated && draftTurn && (
          <section>
            <SectionTitle>ドラフト v1 (初版)</SectionTitle>
            <Markdown content={draftTurn.content} />
          </section>
        )}

        {hasGenerated && reviewTurn && (
          <section>
            <SectionTitle>セルフレビュー</SectionTitle>
            {reviewTurn.content && (
              <p style={{ fontSize: 14, color: '#374151', marginTop: 8 }}>{reviewTurn.content}</p>
            )}
            <RisksList risks={(reviewTurn.metadata?.risks ?? []) as DraftRisk[]} />
          </section>
        )}

        {hasGenerated && revisedTurn && (
          <section>
            <SectionTitle>最終版 (revised)</SectionTitle>
            <Markdown content={revisedTurn.content} />
          </section>
        )}
      </div>

      {!hasGenerated && (
        <div
          style={{
            borderTop: '1px solid #e5e7eb',
            padding: 12,
            display: 'flex',
            gap: 8,
            flexDirection: 'column',
          }}
        >
          <Form method="post" style={{ display: 'flex', gap: 8 }}>
            <input type="hidden" name="intent" value="send-message" />
            <input type="hidden" name="sessionId" value={session.id} />
            <input
              name="content"
              placeholder="ヒアリングへの回答を入力…"
              required
              disabled={isBusy}
              style={{
                flex: 1,
                padding: '10px 12px',
                border: '1px solid #d1d5db',
                borderRadius: 6,
                fontSize: 14,
              }}
            />
            <button type="submit" disabled={isBusy} style={primaryButton}>
              {isBusy ? '送信中…' : '送信'}
            </button>
          </Form>

          <Form method="post">
            <input type="hidden" name="intent" value="generate" />
            <input type="hidden" name="sessionId" value={session.id} />
            <button
              type="submit"
              disabled={!requirementsComplete || isBusy}
              style={{
                ...primaryButton,
                width: '100%',
                background: requirementsComplete ? '#16a34a' : '#9ca3af',
                cursor: requirementsComplete ? 'pointer' : 'not-allowed',
              }}
              data-testid="generate-button"
            >
              {isBusy
                ? '生成中… (90〜180 秒)'
                : requirementsComplete
                  ? 'ドラフトを生成 (draft → review → revise)'
                  : '必須項目を埋めてください'}
            </button>
          </Form>
        </div>
      )}
    </>
  );
}

function RequirementsPanel({ requirements }: { requirements: RequirementsDraft }) {
  return (
    <section
      style={{
        border: '1px solid #e5e7eb',
        borderRadius: 8,
        padding: 12,
        background: '#f9fafb',
      }}
      data-testid="requirements-panel"
    >
      <SectionTitle>要件サマリ</SectionTitle>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '180px 1fr',
          gap: '6px 12px',
          marginTop: 8,
          fontSize: 13,
        }}
      >
        {REQUIREMENT_FIELDS.map((key) => {
          const filled = isFilled(requirements[key]);
          return (
            <Fragment key={key}>
              <div style={{ color: '#6b7280' }}>
                {filled ? '✓ ' : '○ '}
                {FIELD_LABELS_JA[key]}
              </div>
              <div
                style={{
                  color: filled ? '#111827' : '#9ca3af',
                  fontFamily: 'monospace',
                  fontSize: 12,
                }}
                data-testid={`requirement-${key}`}
              >
                {filled ? String(requirements[key]) : '(未入力)'}
              </div>
            </Fragment>
          );
        })}
      </div>
    </section>
  );
}

function Bubble({ turn }: { turn: DraftTurn }) {
  const isUser = turn.role === 'user';
  return (
    <div
      style={{
        alignSelf: isUser ? 'flex-end' : 'flex-start',
        maxWidth: '78%',
        background: isUser ? '#2563eb' : '#f3f4f6',
        color: isUser ? '#fff' : '#111827',
        padding: '10px 14px',
        borderRadius: 12,
        whiteSpace: 'pre-wrap',
        fontSize: 14,
      }}
    >
      {turn.content}
    </div>
  );
}

function RisksList({ risks }: { risks: DraftRisk[] }) {
  if (risks.length === 0) {
    return (
      <p style={{ color: '#16a34a', fontSize: 13, marginTop: 8 }}>検出されたリスクはありません。</p>
    );
  }
  return (
    <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
      {risks.map((r, i) => (
        <div
          key={i}
          style={{
            border: `1px solid ${severityColor(r.severity).border}`,
            borderRadius: 6,
            padding: 10,
            background: severityColor(r.severity).bg,
          }}
        >
          <div
            style={{
              fontSize: 11,
              fontWeight: 700,
              color: severityColor(r.severity).fg,
              textTransform: 'uppercase',
              letterSpacing: 0.5,
            }}
          >
            {r.severity}
          </div>
          <div style={{ fontSize: 13, fontWeight: 600, marginTop: 2 }}>{r.clause}</div>
          <div style={{ fontSize: 13, color: '#374151', marginTop: 4 }}>{r.reason}</div>
          <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>
            <strong>対応方針: </strong>
            {r.suggestion}
          </div>
        </div>
      ))}
    </div>
  );
}

function Markdown({ content }: { content: string }) {
  return (
    <pre
      style={{
        marginTop: 8,
        padding: 12,
        background: '#fafafa',
        border: '1px solid #e5e7eb',
        borderRadius: 6,
        fontSize: 13,
        lineHeight: 1.6,
        whiteSpace: 'pre-wrap',
        fontFamily: 'inherit',
      }}
    >
      {content}
    </pre>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h2 style={{ fontSize: 15, margin: 0, color: '#111827', fontWeight: 700 }}>{children}</h2>;
}

function isFilled(v: string | number | undefined | null): boolean {
  if (v === undefined || v === null) return false;
  if (typeof v === 'string') return v.trim().length > 0;
  if (typeof v === 'number') return v > 0;
  return true;
}

function severityColor(s: RiskSeverity) {
  switch (s) {
    case 'high':
      return { bg: '#fef2f2', border: '#fecaca', fg: '#b91c1c' };
    case 'medium':
      return { bg: '#fffbeb', border: '#fde68a', fg: '#b45309' };
    default:
      return { bg: '#f0f9ff', border: '#bae6fd', fg: '#075985' };
  }
}

const primaryButton: React.CSSProperties = {
  padding: '8px 14px',
  background: '#2563eb',
  color: '#fff',
  border: 'none',
  borderRadius: 6,
  fontSize: 14,
  fontWeight: 600,
  cursor: 'pointer',
};

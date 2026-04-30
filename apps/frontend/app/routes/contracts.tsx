import type { ContractReviewResult, RiskSeverity } from '@legal-ai-agent/shared-types';
import { Form, Link, useActionData, useNavigation } from 'react-router';
import { api } from '~/lib/api';
import type { Route } from './+types/contracts';

export function meta() {
  return [{ title: '契約書レビュー — Legal AI Agent' }];
}

type ActionResult = { ok: true; result: ContractReviewResult } | { ok: false; error: string };

export async function action({ request }: Route.ActionArgs): Promise<ActionResult> {
  const formData = await request.formData();
  const title = String(formData.get('title') ?? '').trim();
  const body = String(formData.get('body') ?? '').trim();
  if (!title || !body) {
    return { ok: false, error: 'タイトルと本文を入力してください' };
  }
  try {
    const result = await api.reviewContract({ title, body });
    return { ok: true, result };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}

const severityColor: Record<RiskSeverity, string> = {
  high: '#dc2626',
  medium: '#d97706',
  low: '#2563eb',
};

const severityLabel: Record<RiskSeverity, string> = {
  high: '高',
  medium: '中',
  low: '低',
};

export default function ContractsRoute() {
  const navigation = useNavigation();
  const data = useActionData<typeof action>();
  const isSubmitting = navigation.state === 'submitting';

  return (
    <main style={{ maxWidth: 960, margin: '40px auto', padding: '0 24px' }}>
      <Link to="/" style={{ color: '#2563eb', fontSize: 14 }}>
        ← ホーム
      </Link>
      <h1 style={{ fontSize: 28, margin: '12px 0 24px' }}>契約書レビュー</h1>

      <Form method="post" style={{ display: 'grid', gap: 12 }}>
        <label style={{ display: 'grid', gap: 4 }}>
          <span style={{ fontSize: 14, color: '#374151' }}>契約書タイトル</span>
          <input name="title" placeholder="例: 業務委託契約書" required style={inputStyle} />
        </label>
        <label style={{ display: 'grid', gap: 4 }}>
          <span style={{ fontSize: 14, color: '#374151' }}>契約書本文</span>
          <textarea
            name="body"
            rows={16}
            placeholder="契約書の全文をここに貼り付けてください"
            required
            style={{ ...inputStyle, fontFamily: 'ui-monospace, monospace' }}
          />
        </label>
        <button type="submit" disabled={isSubmitting} style={buttonStyle}>
          {isSubmitting ? 'レビュー中…' : 'レビューを実行'}
        </button>
      </Form>

      {data && !data.ok && <p style={{ color: '#dc2626', marginTop: 16 }}>{data.error}</p>}

      {data?.ok && (
        <section style={{ marginTop: 32 }}>
          <h2 style={{ fontSize: 20, marginBottom: 8 }}>所感</h2>
          <p
            style={{
              background: '#fff',
              padding: 16,
              borderRadius: 8,
              border: '1px solid #e5e7eb',
              whiteSpace: 'pre-wrap',
            }}
          >
            {data.result.summary}
          </p>
          <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>
            model: {data.result.model}
          </div>

          <h2 style={{ fontSize: 20, margin: '24px 0 8px' }}>
            指摘事項 ({data.result.risks.length})
          </h2>
          <div style={{ display: 'grid', gap: 12 }}>
            {data.result.risks.map((risk, i) => (
              <article
                key={i}
                style={{
                  background: '#fff',
                  padding: 16,
                  borderRadius: 8,
                  border: '1px solid #e5e7eb',
                  borderLeft: `4px solid ${severityColor[risk.severity]}`,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span
                    style={{
                      background: severityColor[risk.severity],
                      color: '#fff',
                      padding: '2px 8px',
                      borderRadius: 999,
                      fontSize: 12,
                    }}
                  >
                    深刻度 {severityLabel[risk.severity]}
                  </span>
                  <strong>{risk.clause}</strong>
                </div>
                <p style={{ marginTop: 8 }}>
                  <strong>理由:</strong> {risk.reason}
                </p>
                <p style={{ marginTop: 4 }}>
                  <strong>提案:</strong> {risk.suggestion}
                </p>
              </article>
            ))}
            {data.result.risks.length === 0 && (
              <p style={{ color: '#6b7280' }}>指摘すべき重大なリスクは検出されませんでした。</p>
            )}
          </div>
        </section>
      )}
    </main>
  );
}

const inputStyle: React.CSSProperties = {
  padding: '10px 12px',
  border: '1px solid #d1d5db',
  borderRadius: 6,
  fontSize: 14,
  background: '#fff',
};

const buttonStyle: React.CSSProperties = {
  padding: '10px 16px',
  background: '#2563eb',
  color: '#fff',
  border: 'none',
  borderRadius: 6,
  fontSize: 14,
  fontWeight: 600,
  cursor: 'pointer',
  justifySelf: 'start',
};

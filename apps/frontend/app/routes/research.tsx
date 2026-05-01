import type { ResearchResult } from '@legal-ai-agent/shared-types';
import { Form, Link, useActionData, useNavigation } from 'react-router';
import { api } from '~/lib/api';
import type { Route } from './+types/research';

export function meta() {
  return [{ title: '法務リサーチ — Legal AI Agent' }];
}

type ActionResult = { ok: true; result: ResearchResult } | { ok: false; error: string };

export async function action({ request }: Route.ActionArgs): Promise<ActionResult> {
  const formData = await request.formData();
  const question = String(formData.get('question') ?? '').trim();
  if (!question) {
    return { ok: false, error: '質問を入力してください' };
  }
  try {
    const result = await api.postResearch({ question });
    return { ok: true, result };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}

export default function ResearchRoute() {
  const navigation = useNavigation();
  const data = useActionData<typeof action>();
  const isSubmitting = navigation.state === 'submitting';

  return (
    <main style={{ maxWidth: 960, margin: '40px auto', padding: '0 24px' }}>
      <Link to="/" style={{ color: '#2563eb', fontSize: 14 }}>
        ← ホーム
      </Link>
      <h1 style={{ fontSize: 28, margin: '12px 0 8px' }}>法務リサーチ (ReAct)</h1>
      <p style={{ color: '#6b7280', fontSize: 14, marginBottom: 24 }}>
        AI が法令データベースを反復検索 (最大 5 回) し、結論と根拠条文をまとめて返します。/chat の 1
        回検索に対し、初期クエリが弱くても 観点を変えて掘り下げられるのが特徴です。
      </p>

      <Form method="post" style={{ display: 'grid', gap: 12 }}>
        <label style={{ display: 'grid', gap: 4 }}>
          <span style={{ fontSize: 14, color: '#374151' }}>質問</span>
          <textarea
            name="question"
            rows={6}
            placeholder="例: 取締役の解任に必要な株主総会決議は？"
            required
            style={{ ...inputStyle, fontFamily: 'inherit' }}
          />
        </label>
        <button type="submit" disabled={isSubmitting} style={buttonStyle}>
          {isSubmitting ? 'リサーチ中…' : 'リサーチを実行'}
        </button>
      </Form>

      {data && !data.ok && <p style={{ color: '#dc2626', marginTop: 16 }}>{data.error}</p>}

      {data?.ok && (
        <section style={{ marginTop: 32 }}>
          <h2 style={{ fontSize: 20, marginBottom: 8 }}>回答</h2>
          <div
            style={{
              background: '#fff',
              padding: 16,
              borderRadius: 8,
              border: '1px solid #e5e7eb',
              whiteSpace: 'pre-wrap',
            }}
          >
            {data.result.content}
          </div>
          <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>
            model: {data.result.model} ・ iterations: {data.result.iterations}
          </div>

          <h2 style={{ fontSize: 20, margin: '24px 0 8px' }}>
            参考法令 ({data.result.citations.length})
          </h2>
          <div style={{ display: 'grid', gap: 12 }}>
            {data.result.citations.map((cite, i) => (
              <article
                key={`${cite.lawId}-${cite.articleNo ?? i}-${i}`}
                style={{
                  background: '#fff',
                  padding: 16,
                  borderRadius: 8,
                  border: '1px solid #e5e7eb',
                  borderLeft: '4px solid #2563eb',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <span
                    style={{
                      background: '#2563eb',
                      color: '#fff',
                      padding: '2px 8px',
                      borderRadius: 999,
                      fontSize: 12,
                    }}
                  >
                    [{i + 1}]
                  </span>
                  <strong>{cite.lawTitle}</strong>
                  <span style={{ color: '#6b7280', fontSize: 13 }}>{cite.lawNum}</span>
                </div>
                {(cite.articleNo || cite.articleTitle) && (
                  <div style={{ marginTop: 6, fontSize: 14, color: '#374151' }}>
                    {cite.articleNo}
                    {cite.articleTitle ? `（${cite.articleTitle}）` : ''}
                  </div>
                )}
                <p
                  style={{
                    marginTop: 8,
                    whiteSpace: 'pre-wrap',
                    color: '#1f2937',
                    fontSize: 14,
                  }}
                >
                  {cite.body}
                </p>
                <div
                  style={{
                    marginTop: 8,
                    display: 'flex',
                    justifyContent: 'space-between',
                    fontSize: 12,
                    color: '#6b7280',
                  }}
                >
                  <a
                    href={cite.sourceUrl}
                    target="_blank"
                    rel="noreferrer"
                    style={{ color: '#2563eb' }}
                  >
                    出典 e-Gov
                  </a>
                  <span>score: {cite.score.toFixed(3)}</span>
                </div>
              </article>
            ))}
            {data.result.citations.length === 0 && (
              <p style={{ color: '#6b7280' }}>
                参考法令は見つかりませんでした (RAG_ENABLED=false の可能性)。
              </p>
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

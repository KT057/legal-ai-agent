import type { ContractReviewResult, RiskSeverity } from '@legal-ai-agent/shared-types';
import { useRef, useState } from 'react';
import { Form, Link, useActionData, useNavigation } from 'react-router';
import { api } from '~/lib/api';
import type { Route } from './+types/contracts';

export function meta() {
  return [{ title: '契約書レビュー — Legal AI Agent' }];
}

type ActionResult = { ok: true; result: ContractReviewResult } | { ok: false; error: string };

const MAX_PDF_BYTES = 10 * 1024 * 1024;

export async function action({ request }: Route.ActionArgs): Promise<ActionResult> {
  const formData = await request.formData();
  const title = String(formData.get('title') ?? '').trim();
  const body = String(formData.get('body') ?? '').trim();
  const fileField = formData.get('file');
  const file = fileField instanceof File && fileField.size > 0 ? fileField : null;

  if (!title) {
    return { ok: false, error: 'タイトルを入力してください' };
  }
  if (!file && !body) {
    return { ok: false, error: '本文を貼り付けるか、PDF をアップロードしてください' };
  }
  if (file) {
    if (file.size > MAX_PDF_BYTES) {
      return { ok: false, error: `PDF が大きすぎます（最大 ${MAX_PDF_BYTES / 1024 / 1024}MB）` };
    }
    if (file.type && file.type !== 'application/pdf') {
      return { ok: false, error: 'PDF ファイルのみアップロードできます' };
    }
  }

  try {
    const result = await api.reviewContract({
      title,
      body: file ? undefined : body,
      file: file ?? undefined,
    });
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

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [dropError, setDropError] = useState<string | null>(null);

  // ドロップされた / 選ばれたファイルを実 input にも反映する。
  // <Form> はネイティブ submit なので、最終的に input.files に乗っていれば multipart で送られる。
  const assignFile = (file: File | null) => {
    setSelectedFile(file);
    setDropError(null);
    const input = fileInputRef.current;
    if (!input) return;
    if (!file) {
      input.value = '';
      return;
    }
    const dt = new DataTransfer();
    dt.items.add(file);
    input.files = dt.files;
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(false);
    const dropped = e.dataTransfer.files?.[0];
    if (!dropped) return;
    if (dropped.type && dropped.type !== 'application/pdf') {
      setDropError('PDF ファイルのみアップロードできます');
      return;
    }
    if (dropped.size > 10 * 1024 * 1024) {
      setDropError('PDF が大きすぎます（最大 10MB）');
      return;
    }
    assignFile(dropped);
  };

  return (
    <main style={{ maxWidth: 960, margin: '40px auto', padding: '0 24px' }}>
      <Link to="/" style={{ color: '#2563eb', fontSize: 14 }}>
        ← ホーム
      </Link>
      <h1 style={{ fontSize: 28, margin: '12px 0 24px' }}>契約書レビュー</h1>

      <Form method="post" encType="multipart/form-data" style={{ display: 'grid', gap: 12 }}>
        <label style={{ display: 'grid', gap: 4 }}>
          <span style={{ fontSize: 14, color: '#374151' }}>契約書タイトル</span>
          <input name="title" placeholder="例: 業務委託契約書" required style={inputStyle} />
        </label>

        <div style={{ display: 'grid', gap: 4 }}>
          <span style={{ fontSize: 14, color: '#374151' }}>
            PDF アップロード <span style={{ color: '#6b7280' }}>(任意・最大 10MB)</span>
          </span>
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragOver(true);
            }}
            onDragLeave={() => setIsDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                fileInputRef.current?.click();
              }
            }}
            style={{
              ...dropZoneStyle,
              borderColor: isDragOver ? '#2563eb' : '#d1d5db',
              background: isDragOver ? '#eff6ff' : '#fff',
            }}
          >
            {selectedFile ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 14 }}>📄 {selectedFile.name}</span>
                <span style={{ fontSize: 12, color: '#6b7280' }}>
                  ({Math.round(selectedFile.size / 1024)} KB)
                </span>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    assignFile(null);
                  }}
                  style={removeButtonStyle}
                >
                  削除
                </button>
              </div>
            ) : (
              <div style={{ color: '#6b7280', fontSize: 14, textAlign: 'center' }}>
                ここに PDF をドラッグ&ドロップ、またはクリックして選択
              </div>
            )}
            <input
              ref={fileInputRef}
              name="file"
              type="file"
              accept="application/pdf"
              onChange={(e) => assignFile(e.target.files?.[0] ?? null)}
              style={{ display: 'none' }}
            />
          </div>
          {dropError && <span style={{ fontSize: 12, color: '#dc2626' }}>{dropError}</span>}
          <span style={{ fontSize: 12, color: '#6b7280' }}>
            PDF を選んだ場合は下の本文欄は無視されます。スキャン PDF（画像のみ）は非対応。
          </span>
        </div>

        <label style={{ display: 'grid', gap: 4 }}>
          <span style={{ fontSize: 14, color: '#374151' }}>
            契約書本文 <span style={{ color: '#6b7280' }}>(PDF を使わない場合のみ)</span>
          </span>
          <textarea
            name="body"
            rows={12}
            placeholder="契約書の全文をここに貼り付けてください"
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

const dropZoneStyle: React.CSSProperties = {
  padding: '24px 16px',
  border: '2px dashed #d1d5db',
  borderRadius: 6,
  cursor: 'pointer',
  transition: 'background-color 0.15s, border-color 0.15s',
};

const removeButtonStyle: React.CSSProperties = {
  marginLeft: 'auto',
  padding: '4px 10px',
  background: '#fff',
  color: '#dc2626',
  border: '1px solid #dc2626',
  borderRadius: 4,
  fontSize: 12,
  cursor: 'pointer',
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

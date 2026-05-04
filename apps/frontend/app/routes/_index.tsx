import { Link } from 'react-router';

export function meta() {
  return [{ title: 'Legal AI Agent' }];
}

export default function IndexRoute() {
  return (
    <main
      style={{
        maxWidth: 720,
        margin: '64px auto',
        padding: '0 24px',
      }}
    >
      <h1 style={{ fontSize: 32, marginBottom: 8 }}>Legal AI Agent</h1>
      <p style={{ color: '#4b5563', marginBottom: 32 }}>
        法務業務をサポートする AI エージェントです。利用したい機能を選んでください。
      </p>
      <div style={{ display: 'grid', gap: 16 }}>
        <Card
          to="/contracts"
          title="契約書レビュー"
          description="契約書の本文を貼り付けると、リスク条項と修正提案を返します。"
        />
        <Card
          to="/chat"
          title="法務相談チャット"
          description="法律・社内規程に関する質問に AI が回答します。"
        />
        <Card
          to="/research"
          title="法務リサーチ (ReAct)"
          description="AI が法令データベースを反復検索し、結論と根拠条文をまとめて返します。"
        />
        <Card
          to="/draft"
          title="NDA ドラフト生成"
          description="ヒアリング → ドラフト → セルフレビュー → 修正、の 4 段ワークフローで NDA を起案します。"
        />
      </div>
    </main>
  );
}

function Card({ to, title, description }: { to: string; title: string; description: string }) {
  return (
    <Link
      to={to}
      style={{
        display: 'block',
        padding: 24,
        background: '#fff',
        borderRadius: 12,
        boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
        textDecoration: 'none',
        color: 'inherit',
        border: '1px solid #e5e7eb',
      }}
    >
      <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 4 }}>{title}</div>
      <div style={{ color: '#6b7280', fontSize: 14 }}>{description}</div>
    </Link>
  );
}

import type { ChatThreadWithMessages } from '@legal-ai-agent/shared-types';
import { Form, Link, redirect, useLoaderData, useNavigation } from 'react-router';
import { api } from '~/lib/api';
import type { Route } from './+types/chat';

export function meta() {
  return [{ title: '法務相談チャット — Legal AI Agent' }];
}

export async function loader({ request }: Route.LoaderArgs) {
  const url = new URL(request.url);
  const threadId = url.searchParams.get('thread');

  const threads = await api.listThreads();
  const active = threadId ? await api.getThread(threadId).catch(() => null) : null;
  return { threads, active };
}

export async function action({ request }: Route.ActionArgs) {
  const formData = await request.formData();
  const intent = String(formData.get('intent') ?? '');

  if (intent === 'create-thread') {
    const title = String(formData.get('title') ?? '').trim() || undefined;
    const thread = await api.createThread({ title });
    return redirect(`/chat?thread=${thread.id}`);
  }

  if (intent === 'send-message') {
    const threadId = String(formData.get('threadId') ?? '');
    const content = String(formData.get('content') ?? '').trim();
    if (!threadId || !content) {
      return redirect(`/chat?thread=${threadId}`);
    }
    await api.postMessage(threadId, content);
    return redirect(`/chat?thread=${threadId}`);
  }

  return null;
}

export default function ChatRoute() {
  const { threads, active } = useLoaderData<typeof loader>();
  const navigation = useNavigation();
  const isBusy = navigation.state !== 'idle';

  return (
    <main
      style={{
        display: 'grid',
        gridTemplateColumns: '260px 1fr',
        gap: 16,
        maxWidth: 1100,
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
          <input type="hidden" name="intent" value="create-thread" />
          <button type="submit" style={primaryButton}>
            + 新規スレッド
          </button>
        </Form>
        <div style={{ display: 'grid', gap: 4, marginTop: 8 }}>
          {threads.map((t) => (
            <Link
              key={t.id}
              to={`/chat?thread=${t.id}`}
              style={{
                display: 'block',
                padding: '8px 10px',
                borderRadius: 6,
                textDecoration: 'none',
                color: 'inherit',
                background: active?.id === t.id ? '#eef2ff' : 'transparent',
                fontSize: 14,
              }}
            >
              {t.title}
            </Link>
          ))}
          {threads.length === 0 && (
            <span style={{ fontSize: 13, color: '#9ca3af', padding: 8 }}>
              スレッドはまだありません
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
          <ActiveThread thread={active} isBusy={isBusy} />
        ) : (
          <div style={{ padding: 24, color: '#6b7280' }}>
            左のメニューからスレッドを選ぶか、新規スレッドを作成してください。
          </div>
        )}
      </section>
    </main>
  );
}

function ActiveThread({ thread, isBusy }: { thread: ChatThreadWithMessages; isBusy: boolean }) {
  return (
    <>
      <header
        style={{
          padding: '12px 16px',
          borderBottom: '1px solid #e5e7eb',
          fontWeight: 600,
        }}
      >
        {thread.title}
      </header>
      <div
        style={{
          flex: 1,
          overflow: 'auto',
          padding: 16,
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
        }}
      >
        {thread.messages.map((m) => (
          <div
            key={m.id}
            style={{
              alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
              maxWidth: '78%',
              background: m.role === 'user' ? '#2563eb' : '#f3f4f6',
              color: m.role === 'user' ? '#fff' : '#111827',
              padding: '10px 14px',
              borderRadius: 12,
              whiteSpace: 'pre-wrap',
              fontSize: 14,
            }}
          >
            {m.content}
          </div>
        ))}
        {thread.messages.length === 0 && (
          <div style={{ color: '#9ca3af', textAlign: 'center', marginTop: 32 }}>
            最初の質問を入力してください
          </div>
        )}
      </div>
      <Form
        method="post"
        style={{
          borderTop: '1px solid #e5e7eb',
          padding: 12,
          display: 'flex',
          gap: 8,
        }}
      >
        <input type="hidden" name="intent" value="send-message" />
        <input type="hidden" name="threadId" value={thread.id} />
        <input
          name="content"
          placeholder="法務に関する質問を入力…"
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
    </>
  );
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

import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '../api/client';
import { applyToChat } from '../api/chatReducer';
import type { Chat } from '../api/types';
import MessageView from '../components/MessageView';
import StatusBadge from '../components/StatusBadge';

/** The user opens a chat and asks. The agent looks at the system's servers through the server tools. */
export default function ChatPage() {
  const { systemId = '', chatId = 'new' } = useParams();
  const navigate = useNavigate();
  const [chat, setChat] = useState<Chat | null>(null);
  const [sendError, setSendError] = useState('');
  const [draft, setDraft] = useState('');
  const pendingText = useRef<string | null>(null); // first message of a new chat, sent after navigation
  const stopStream = useRef<(() => void) | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (chatId === 'new') {
      setChat(null);
      return;
    }
    let active = true;
    (async () => {
      try {
        const c = await api.getChat(chatId);
        if (active) setChat(c);
      } catch {
        if (active) navigate(`/${systemId}/chats/new`, { replace: true });
      }
    })();
    return () => {
      active = false;
    };
  }, [chatId, systemId, navigate]);

  useEffect(() => () => stopStream.current?.(), []);

  const startAgent = (id: string, text: string) => {
    stopStream.current?.();
    stopStream.current = api.sendMessage(id, text, (event) => {
      setChat((c) => (c && c.id === id ? applyToChat(c, event) : c));
    });
  };

  // A new chat was just created: send its first message once it is loaded.
  useEffect(() => {
    if (chat && pendingText.current) {
      const text = pendingText.current;
      pendingText.current = null;
      startAgent(chat.id, text);
    }
  }, [chat?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chat?.messages]);

  const send = async (e?: FormEvent) => {
    e?.preventDefault();
    const text = draft.trim();
    if (!text) return;
    setDraft('');
    setSendError('');
    if (!chat) {
      try {
        const created = await api.createChat(systemId);
        pendingText.current = text;
        navigate(`/${systemId}/chats/${created.id}`);
      } catch (err) {
        setDraft(text);
        setSendError(err instanceof Error ? err.message : String(err));
      }
    } else {
      startAgent(chat.id, text);
    }
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  };

  const working = chat?.status === 'working';

  return (
    <>
      <section className="chat-col" aria-label="Chat">
        <div className="chat-head">
          <h1>{chat ? chat.title : 'New chat'}</h1>
          {chat && chat.messages.length > 0 && <StatusBadge status={chat.status} />}
        </div>

        <div className="messages">
          {!chat || chat.messages.length === 0 ? (
            <div className="empty-chat">
              <h2>What do you need?</h2>
              <p>Ask about {systemId}: logs, containers, config. The agent looks at its servers and asks you before each step.</p>
            </div>
          ) : (
            chat.messages.map((m) => (
              <MessageView key={m.id} message={m} onAnswer={(callId, answer) => void api.answerToolCall(chat.id, callId, answer)} />
            ))
          )}
          <div ref={bottom} />
        </div>

        <div className="composer">
          <form onSubmit={send}>
            <label htmlFor="msg" style={{ position: 'absolute', left: -9999 }}>Message</label>
            <textarea
              id="msg"
              rows={3}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="e.g. why does orders-service keep restarting?"
            />
            <div className="row">
              <span className="muted" style={{ fontSize: 12 }}>{systemId} · dev · Enter to send</span>
              <button type="submit" className="send" aria-label="Send" disabled={!draft.trim() || working}>↑</button>
            </div>
          </form>
          {sendError && <p className="form-error" role="alert">{sendError}</p>}
        </div>
      </section>
    </>
  );
}

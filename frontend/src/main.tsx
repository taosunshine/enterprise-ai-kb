import { FormEvent, ReactNode, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { api, AUTH_EXPIRED_EVENT, ChatSession, Citation, DocumentItem, KnowledgeBase, RecycleBinItem } from "./api";
import "./styles.css";

type Message = { role: "user" | "assistant"; content: string; citations?: Citation[] };
type View = "chat" | "creation" | "documents" | "trash";
type CreationTemplate = {
  id: string;
  title: string;
  subtitle: string;
  description: string;
  placeholder: string;
  buildPrompt: (topic: string, requirements: string) => string;
};
type IconName = "spark" | "search" | "book" | "plus" | "upload" | "chat" | "file" | "grid" | "send" | "logout" | "chevron" | "check" | "more" | "trash" | "refresh" | "edit";

const creationTemplates: CreationTemplate[] = [
  {
    id: "selling-points",
    title: "产品卖点",
    subtitle: "SELLING POINTS",
    description: "从资料中提炼差异化价值、目标客群与可信支撑。",
    placeholder: "例如：面向制造业客户的 Atlas 企业知识助手",
    buildPrompt: (topic, requirements) => `基于知识库资料，为“${topic}”提炼产品卖点。请输出：核心定位、目标用户、5 个差异化卖点、每个卖点的资料依据、适合销售使用的一句话表达。额外要求：${requirements || "语言专业、清晰、可直接用于销售沟通。"}`
  },
  {
    id: "marketing-copy",
    title: "营销文案",
    subtitle: "MARKETING COPY",
    description: "生成有依据的标题、正文、行动号召与渠道版本。",
    placeholder: "例如：Atlas 新品发布微信公众号推文",
    buildPrompt: (topic, requirements) => `基于知识库资料，为“${topic}”生成营销文案。请输出：3 个标题、核心正文、3 条短文案、行动号召，并确保关键事实与数字来自资料。额外要求：${requirements || "语气有吸引力但不夸大，不编造资料中不存在的信息。"}`
  },
  {
    id: "video-script",
    title: "短视频脚本",
    subtitle: "VIDEO SCRIPT",
    description: "生成开场钩子、分镜、口播、字幕与结尾行动号召。",
    placeholder: "例如：60 秒介绍 Atlas 的核心价值",
    buildPrompt: (topic, requirements) => `基于知识库资料，为“${topic}”生成短视频脚本。请用表格输出时间段、画面、口播、字幕，并包含开场钩子、核心信息和结尾行动号召。额外要求：${requirements || "时长约 60 秒，口语自然，事实准确。"}`
  },
  {
    id: "prompt-reference",
    title: "Prompt 参考",
    subtitle: "PROMPT REFERENCE",
    description: "根据目标任务生成可复用、结构化的高质量 Prompt。",
    placeholder: "例如：让 AI 根据企业资料生成客户方案",
    buildPrompt: (topic, requirements) => `基于知识库资料，为“${topic}”设计一个可复用的高质量 Prompt。请输出：角色、任务目标、输入变量、约束条件、执行步骤、输出格式、完整 Prompt 示例和使用建议。额外要求：${requirements || "结构清晰，可直接复制使用。"}`
  }
];

const icons: Record<IconName, ReactNode> = {
  spark: <><path d="m12 3-1.2 4.1a5.4 5.4 0 0 1-3.7 3.7L3 12l4.1 1.2a5.4 5.4 0 0 1 3.7 3.7L12 21l1.2-4.1a5.4 5.4 0 0 1 3.7-3.7L21 12l-4.1-1.2a5.4 5.4 0 0 1-3.7-3.7L12 3Z"/></>,
  search: <><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></>,
  book: <><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21.5v-16Z"/><path d="M4 19a2 2 0 0 1 2-2h14"/></>,
  plus: <><path d="M12 5v14M5 12h14"/></>,
  upload: <><path d="M12 16V4m0 0L7 9m5-5 5 5"/><path d="M5 15v4h14v-4"/></>,
  chat: <><path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4v8Z"/></>,
  file: <><path d="M6 2h8l4 4v16H6z"/><path d="M14 2v5h5M9 13h6M9 17h6"/></>,
  grid: <><rect x="4" y="4" width="6" height="6" rx="1"/><rect x="14" y="4" width="6" height="6" rx="1"/><rect x="4" y="14" width="6" height="6" rx="1"/><rect x="14" y="14" width="6" height="6" rx="1"/></>,
  send: <><path d="m22 2-7 20-4-9-9-4 20-7Z"/><path d="M22 2 11 13"/></>,
  logout: <><path d="M10 17l5-5-5-5M15 12H3"/><path d="M15 3h5v18h-5"/></>,
  chevron: <><path d="m9 18 6-6-6-6"/></>,
  check: <><path d="m5 12 4 4L19 6"/></>,
  more: <><circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/></>,
  trash: <><path d="M4 7h16M10 11v6M14 11v6M6 7l1 14h10l1-14M9 7V4h6v3"/></>,
  refresh: <><path d="M20 6v5h-5M4 18v-5h5"/><path d="M18.5 9A7 7 0 0 0 6 6.5L4 11m16 2-2 4.5A7 7 0 0 1 5.5 15"/></>,
  edit: <><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z"/></>
};

function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>{icons[name]}</svg>;
}

function Login({ onReady, notice }: { onReady: () => void; notice?: string }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  const submit = async (event: FormEvent, register = false) => {
    event.preventDefault();
    setError("");
    try {
      const result = await api.login(email, password, register);
      localStorage.setItem("token", result.access_token);
      onReady();
    } catch (value) {
      setError(value instanceof Error ? value.message : "登录失败");
    }
  };

  return (
    <main className="login-shell">
      <section className="login-story">
        <div className="brand brand-light"><span className="brand-mark"><Icon name="spark" /></span><strong>知境</strong><em>AI Knowledge</em></div>
        <div className="story-copy">
          <span className="kicker">ENTERPRISE KNOWLEDGE, ACTIVATED</span>
          <h1>让每一份资料<br />都成为<span>生产力</span></h1>
          <p>统一管理企业知识，用可信引用辅助问答、创作与决策。</p>
          <div className="story-stats"><div><b>01</b><span>上传企业资料</span></div><div><b>02</b><span>建立专属知识库</span></div><div><b>03</b><span>获得可信答案</span></div></div>
        </div>
        <div className="story-orb orb-one" /><div className="story-orb orb-two" />
      </section>
      <section className="login-form-wrap">
        <form className="login-panel" onSubmit={submit}>
          <div className="mobile-brand"><span className="brand-mark"><Icon name="spark" /></span><strong>知境</strong></div>
          <span className="kicker">WELCOME BACK</span>
          <h2>登录知识工作台</h2>
          <p>继续探索企业知识，让创作更有依据。</p>
          {notice && <div className="error">{notice}</div>}
          <label>工作邮箱<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} /></label>
          <label>登录密码<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
          {error && <div className="error">{error}</div>}
          <button className="primary-button wide" type="submit">进入工作台 <Icon name="chevron" /></button>
          <button className="text-button" type="button" onClick={(e) => submit(e as unknown as FormEvent, true)}>首次使用？创建一个账号</button>
          <small>登录即表示你同意服务协议与隐私政策</small>
        </form>
      </section>
    </main>
  );
}

function Sidebar({ items, selectedId, sessions, activeSessionId, view, onView, onSelect, onCreate, onNewChat, onSelectSession, onDeleteSession }: { items: KnowledgeBase[]; selectedId?: number; sessions: ChatSession[]; activeSessionId?: number; view: View; onView: (view: View) => void; onSelect: (id: number) => void; onCreate: () => void; onNewChat: () => void; onSelectSession: (id: number) => void; onDeleteSession: (session: ChatSession) => void }) {
  return <aside className="sidebar">
    <div className="brand"><span className="brand-mark"><Icon name="spark" /></span><strong>知境</strong><em>AI Knowledge</em></div>
    <button className="new-chat" onClick={onNewChat}><Icon name="plus" /> 发起新对话 <kbd>Ctrl K</kbd></button>
    <nav className="main-nav">
      <button className={view === "chat" ? "active" : ""} onClick={() => onView("chat")}><Icon name="chat" />智能问答</button>
      <button className={view === "creation" ? "active" : ""} onClick={() => onView("creation")}><Icon name="grid" />创作中心<span className="soon ready">4 个模板</span></button>
      <button className={view === "documents" ? "active" : ""} onClick={() => onView("documents")}><Icon name="file" />文档管理</button>
      <button className={view === "trash" ? "active" : ""} onClick={() => onView("trash")}><Icon name="trash" />回收站</button>
    </nav>
    <div className="nav-heading"><span>我的知识库</span><button onClick={onCreate} title="新建知识库"><Icon name="plus" size={15} /></button></div>
    <nav className="kb-nav">
      {items.map((item, index) => <button className={selectedId === item.id ? "active" : ""} key={item.id} onClick={() => onSelect(item.id)}>
        <span className={`kb-symbol tone-${index % 4}`}><Icon name="book" size={15} /></span>
        <span><strong>{item.name}</strong><small>{item.description || "个人知识库"}</small></span>
        {selectedId === item.id && <Icon name="chevron" size={14} />}
      </button>)}
      {!items.length && <div className="kb-empty">创建第一个知识库，开始沉淀企业资料。</div>}
    </nav>
    <div className="history-section">
      <div className="nav-heading"><span>问答历史</span><small>{sessions.length}</small></div>
      <nav className="history-nav">
        {sessions.map((session) => <div className={`history-item ${activeSessionId === session.id ? "active" : ""}`} key={session.id}>
          <button className="history-open" onClick={() => onSelectSession(session.id)}>
            <Icon name="chat" size={14} />
            <span><strong>{session.title}</strong><small>{session.message_count} 条消息 · {new Date(session.last_message_at || session.created_at).toLocaleDateString("zh-CN")}</small></span>
          </button>
          <button className="history-delete" title="删除会话" onClick={() => onDeleteSession(session)}><Icon name="trash" size={13} /></button>
        </div>)}
        {!sessions.length && <div className="history-empty">当前知识库还没有历史对话</div>}
      </nav>
    </div>
    <div className="sidebar-footer">
      <button><span className="avatar">知</span><span><strong>当前用户</strong><small>个人工作区</small></span><Icon name="more" size={16} /></button>
    </div>
  </aside>;
}

function SourcePanel({ documents, citations, onUpload }: { documents: DocumentItem[]; citations: Citation[]; onUpload: (files?: FileList) => void }) {
  return <aside className="source-panel">
    <div className="source-head"><div><span className="kicker">KNOWLEDGE SOURCE</span><h3>资料与引用</h3></div><button className="icon-button"><Icon name="more" /></button></div>
    <div className="source-stat"><div className="progress-ring"><span>{documents.length}</span></div><div><strong>知识库资料</strong><small>{documents.filter((item) => item.status === "ready").length} 份已完成解析</small></div></div>
    <label className="dropzone"><input type="file" multiple accept=".pdf,.docx,.md,.txt,.csv,.html,.htm,.png,.jpg,.jpeg,.webp" onChange={(e) => onUpload(e.target.files || undefined)} /><Icon name="upload" /><strong>添加资料</strong><span>可批量上传文档、表格或图片资料</span></label>
    <div className="panel-section-title"><span>{citations.length ? "本轮引用" : "最近资料"}</span><small>{citations.length || documents.length}</small></div>
    <div className="source-list">
      {citations.map((citation) => <div className="citation-card" key={citation.chunk_id}><span className="file-icon"><Icon name="file" /></span><div><strong>{citation.filename}{citation.page_number ? ` · 第 ${citation.page_number} 页` : ""}</strong><p>{citation.excerpt}</p><small>相关度 {Math.round(citation.score * 100)}%</small></div></div>)}
      {!citations.length && documents.slice(0, 5).map((document) => <div className="document-card" key={document.id}><span className="file-icon"><Icon name="file" /></span><div><strong>{document.filename}</strong><small><i className={document.status} />{document.status === "ready" ? "已解析" : document.status === "failed" ? "解析失败" : "处理中"}</small></div></div>)}
      {!citations.length && !documents.length && <div className="source-empty"><Icon name="file" size={24} /><p>还没有资料</p><span>上传后，回答将在这里展示引用依据。</span></div>}
    </div>
    <div className="trust-note"><span><Icon name="check" size={14} /></span><p><strong>可信回答模式</strong>答案仅基于当前知识库资料生成。</p></div>
  </aside>;
}

function DocumentManager({ documents, selected, onUpload, onDelete, onReprocess }: { documents: DocumentItem[]; selected?: KnowledgeBase; onUpload: (files?: FileList) => void; onDelete: (document: DocumentItem) => void; onReprocess: (document: DocumentItem) => void }) {
  return <section className="document-manager">
    <div className="manager-hero"><div><span className="kicker">DOCUMENT MANAGEMENT</span><h1>管理知识库资料</h1><p>上传、检查并维护「{selected?.name || "未选择知识库"}」中的文档。</p></div><label className="manager-upload"><input type="file" multiple accept=".pdf,.docx,.md,.txt,.csv,.html,.htm,.png,.jpg,.jpeg,.webp" onChange={(e) => onUpload(e.target.files || undefined)} /><Icon name="upload" />批量上传资料</label></div>
    <div className="manager-summary"><div><strong>{documents.length}</strong><span>全部资料</span></div><div><strong>{documents.filter((item) => item.status === "ready").length}</strong><span>解析完成</span></div><div><strong>{documents.filter((item) => item.status === "processing").length}</strong><span>处理中</span></div><div><strong>{documents.filter((item) => item.status === "failed").length}</strong><span>解析失败</span></div></div>
    <div className="document-table">
      <div className="table-head"><span>文件名称</span><span>状态</span><span>上传时间</span><span>操作</span></div>
      {documents.map((document) => <div className="table-row" key={document.id}><span className="table-file"><span className="file-icon"><Icon name="file" /></span><span><strong>{document.filename}</strong><small>知识库文档</small></span></span><span><i className={`status-pill ${document.status}`}>{document.status === "ready" ? "解析完成" : document.status === "failed" ? "解析失败" : "处理中"}</i></span><span className="table-date">{new Date(document.created_at).toLocaleDateString("zh-CN")}</span><span className="table-actions"><button title="重新解析" onClick={() => onReprocess(document)}><Icon name="refresh" size={15} /></button><button title="删除文档" onClick={() => onDelete(document)}><Icon name="trash" size={15} /></button></span></div>)}
      {!documents.length && <div className="manager-empty"><Icon name="file" size={28} /><strong>知识库还是空的</strong><span>上传 PDF、DOCX、Markdown、TXT、CSV 或 HTML，系统会自动解析并生成向量。</span></div>}
    </div>
  </section>;
}

function TrashManager({ items, onRefresh, onRestore, onPurge }: { items: RecycleBinItem[]; onRefresh: () => void; onRestore: (item: RecycleBinItem) => void; onPurge: (item: RecycleBinItem) => void }) {
  return <section className="document-manager">
    <div className="manager-hero">
      <div><span className="kicker">RECYCLE BIN</span><h1>回收站</h1><p>删除的知识库和文档默认保留 30 天，可恢复；永久删除需要再次输入完整名称。</p></div>
      <button className="manager-upload" onClick={onRefresh} type="button"><Icon name="refresh" />刷新</button>
    </div>
    <div className="manager-summary trash-summary">
      <div><strong>{items.length}</strong><span>回收站项目</span></div>
      <div><strong>{items.filter((item) => item.item_type === "knowledge-base").length}</strong><span>知识库</span></div>
      <div><strong>{items.filter((item) => item.item_type === "document").length}</strong><span>文档</span></div>
      <div><strong>30</strong><span>默认保留天数</span></div>
    </div>
    <div className="document-table trash-table">
      <div className="table-head"><span>名称</span><span>类型</span><span>剩余</span><span>操作</span></div>
      {items.map((item) => <div className="table-row" key={`${item.item_type}-${item.item_id}`}>
        <span className="table-file"><span className="file-icon"><Icon name={item.item_type === "knowledge-base" ? "book" : "file"} /></span><span><strong>{item.name}</strong><small>删除时间 {new Date(item.deleted_at).toLocaleString("zh-CN")}</small></span></span>
        <span><i className="status-pill">{item.item_type === "knowledge-base" ? "知识库" : "文档"}</i></span>
        <span className="table-date">{item.remaining_days} 天</span>
        <span className="table-actions"><button title="恢复" onClick={() => onRestore(item)}><Icon name="refresh" size={15} /></button><button title="永久删除" onClick={() => onPurge(item)}><Icon name="trash" size={15} /></button></span>
      </div>)}
      {!items.length && <div className="manager-empty"><Icon name="trash" size={28} /><strong>回收站为空</strong><span>删除知识库或文档后，会在这里保留 30 天。</span></div>}
    </div>
  </section>;
}

function CreationCenter({ selectedId, selected, onComplete }: { selectedId?: number; selected?: KnowledgeBase; onComplete: () => void }) {
  const [templateId, setTemplateId] = useState(creationTemplates[0].id);
  const [topic, setTopic] = useState("");
  const [requirements, setRequirements] = useState("");
  const [result, setResult] = useState("");
  const [citations, setCitations] = useState<Citation[]>([]);
  const [status, setStatus] = useState("");
  const template = creationTemplates.find((item) => item.id === templateId) || creationTemplates[0];

  const generate = async (event: FormEvent) => {
    event.preventDefault();
    if (!selectedId || !topic.trim()) return;
    setResult("");
    setCitations([]);
    setStatus("正在检索知识库并生成内容...");
    try {
      await api.askStream(selectedId, template.buildPrompt(topic.trim(), requirements.trim()), undefined, {
        onStatus: setStatus,
        onToken: (content) => setResult((value) => value + content),
        onCitations: setCitations,
        onDone: () => onComplete()
      });
      setStatus("");
    } catch (e) { setStatus(e instanceof Error ? e.message : "生成失败"); }
  };

  return <section className="creation-center">
    <div className="creation-hero">
      <div><span className="kicker">KNOWLEDGE-BASED CREATION</span><h1>创作中心</h1><p>选择模板，基于「{selected?.name || "未选择知识库"}」中的可信资料生成内容。</p></div>
      <span className="creation-badge"><Icon name="spark" size={15} />知识库增强创作</span>
    </div>
    <div className="template-grid">
      {creationTemplates.map((item, index) => <button className={`template-card ${item.id === templateId ? "active" : ""}`} key={item.id} onClick={() => setTemplateId(item.id)}>
        <span className={`template-number tone-${index}`}>0{index + 1}</span>
        <span><small>{item.subtitle}</small><strong>{item.title}</strong><p>{item.description}</p></span>
        <Icon name="chevron" size={15} />
      </button>)}
    </div>
    <div className="creation-workbench">
      <form className="creation-form" onSubmit={generate}>
        <div className="creation-form-head"><span className="template-number tone-0"><Icon name="spark" size={16} /></span><div><small>{template.subtitle}</small><h2>{template.title}</h2></div></div>
        <label>创作主题<input value={topic} onChange={(event) => setTopic(event.target.value)} placeholder={template.placeholder} /></label>
        <label>额外要求<textarea rows={6} value={requirements} onChange={(event) => setRequirements(event.target.value)} placeholder="例如：面向企业管理者，语气专业，控制在 500 字以内" /></label>
        <button className="creation-submit" disabled={!selectedId || !topic.trim()}><Icon name="spark" size={16} />开始生成</button>
        {!selectedId && <small className="creation-hint">请先创建或选择一个知识库。</small>}
      </form>
      <div className="creation-result">
        <div className="creation-result-head"><div><span className="kicker">GENERATED RESULT</span><h3>创作结果</h3></div>{citations.length > 0 && <span>{citations.length} 条资料引用</span>}</div>
        {status && <div className="status"><span className="status-dot" />{status}</div>}
        {result ? <pre>{result}</pre> : <div className="creation-empty"><Icon name="spark" size={28} /><strong>准备开始创作</strong><span>填写主题并选择模板，生成结果将在这里逐字展示。</span></div>}
        {citations.length > 0 && <div className="creation-citations">{citations.map((citation) => <div key={citation.chunk_id}><Icon name="book" size={13} /><span><strong>{citation.filename}</strong><small>{citation.excerpt}</small></span></div>)}</div>}
      </div>
    </div>
  </section>;
}

function Workspace() {
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [selectedId, setSelectedId] = useState<number>();
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [trashItems, setTrashItems] = useState<RecycleBinItem[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [sessionId, setSessionId] = useState<number>();
  const [status, setStatus] = useState("");
  const [view, setView] = useState<View>("chat");
  const messagesEnd = useRef<HTMLDivElement>(null);

  const selected = knowledgeBases.find((item) => item.id === selectedId);
  const citations = [...messages].reverse().find((item) => item.citations?.length)?.citations || [];

  const refresh = async () => {
    const items = await api.listKnowledgeBases();
    setKnowledgeBases(items);
    if (!selectedId && items[0]) setSelectedId(items[0].id);
  };

  const refreshDocuments = async (id?: number) => {
    if (!id) return setDocuments([]);
    try { setDocuments(await api.listDocuments(id)); } catch (e) { setStatus(e instanceof Error ? e.message : "加载资料失败"); }
  };
  const refreshSessions = async (id?: number) => {
    if (!id) return setSessions([]);
    try { setSessions(await api.listChatSessions(id)); } catch (e) { setStatus(e instanceof Error ? e.message : "加载历史失败"); }
  };
  const refreshTrash = async () => {
    try { setTrashItems(await api.listTrash()); } catch (e) { setStatus(e instanceof Error ? e.message : "加载回收站失败"); }
  };

  useEffect(() => { refresh().catch((e) => setStatus(e.message)); }, []);
  useEffect(() => { refreshDocuments(selectedId); refreshSessions(selectedId); }, [selectedId]);
  useEffect(() => { if (view === "trash") refreshTrash(); }, [view]);
  useEffect(() => { messagesEnd.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);
  useEffect(() => {
    const handleShortcut = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        newChat();
      }
    };
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, []);

  const selectKb = (id: number) => { setSelectedId(id); setMessages([]); setSessionId(undefined); setStatus(""); };
  const newChat = () => { setMessages([]); setSessionId(undefined); setStatus(""); setView("chat"); };
  const selectSession = async (id: number) => {
    setStatus("正在加载历史对话...");
    try {
      const detail = await api.getChatSession(id);
      if (detail.knowledge_base_id !== selectedId) setSelectedId(detail.knowledge_base_id);
      setSessionId(detail.id);
      setMessages(detail.messages.map((message) => ({ role: message.role, content: message.content })));
      setView("chat");
      setStatus("");
    } catch (e) { setStatus(e instanceof Error ? e.message : "加载会话失败"); }
  };
  const deleteSession = async (session: ChatSession) => {
    if (!window.confirm(`确认删除会话“${session.title}”吗？`)) return;
    await api.deleteChatSession(session.id);
    if (sessionId === session.id) newChat();
    await refreshSessions(selectedId);
  };
  const createKb = async () => {
    const name = window.prompt("知识库名称");
    if (!name) return;
    const item = await api.createKnowledgeBase(name, "个人知识库");
    await refresh();
    selectKb(item.id);
  };
  const editKb = async () => {
    if (!selected) return;
    const name = window.prompt("修改知识库名称", selected.name);
    if (!name) return;
    const description = window.prompt("修改知识库描述", selected.description) ?? selected.description;
    await api.updateKnowledgeBase(selected.id, name, description);
    await refresh();
  };
  const deleteKb = async () => {
    if (!selected) return;
    const confirmation = window.prompt(`删除知识库前，请输入完整名称「${selected.name}」确认：`);
    if (confirmation !== selected.name) {
      if (confirmation !== null) setStatus("知识库名称不匹配，已取消删除。");
      return;
    }
    await api.deleteKnowledgeBase(selected.id, confirmation);
    setSelectedId(undefined);
    setDocuments([]);
    setStatus("知识库已移入回收站，将保留 30 天。");
    await refresh();
    await refreshTrash();
  };
  const upload = async (files?: FileList) => {
    if (!files?.length || !selectedId) return;
    const selectedFiles = Array.from(files);
    setStatus(`正在提交 ${selectedFiles.length} 份资料...`);
    try {
      for (const file of selectedFiles) await api.uploadDocument(selectedId, file);
      await refreshDocuments(selectedId);
      setStatus(`${selectedFiles.length} 份资料已提交，解析完成后即可提问。`);
      window.setTimeout(() => refreshDocuments(selectedId), 1200);
    } catch (e) { setStatus(e instanceof Error ? e.message : "上传失败"); }
  };
  const askQuestion = async (value: string) => {
    if (!selectedId || !value.trim()) return;
    setQuestion("");
    setMessages((items) => [...items, { role: "user", content: value }, { role: "assistant", content: "" }]);
    setStatus("正在检索知识库并组织答案...");
    try {
      await api.askStream(selectedId, value, sessionId, {
        onStatus: setStatus,
        onToken: (content) => setMessages((items) => items.map((item, index) => index === items.length - 1 ? { ...item, content: item.content + content } : item)),
        onCitations: (citations) => setMessages((items) => items.map((item, index) => index === items.length - 1 ? { ...item, citations } : item)),
        onDone: (id) => { setSessionId(id); refreshSessions(selectedId); }
      });
      setStatus("");
    } catch (e) { setStatus(e instanceof Error ? e.message : "问答失败"); }
  };
  const ask = (event: FormEvent) => { event.preventDefault(); askQuestion(question); };
  const deleteDocument = async (document: DocumentItem) => {
    if (!window.confirm(`确认将「${document.filename}」移入回收站吗？将保留 30 天。`)) return;
    await api.deleteDocument(document.id);
    setStatus("文档已移入回收站，将保留 30 天。");
    await refreshDocuments(selectedId);
    await refreshTrash();
  };
  const restoreTrashItem = async (item: RecycleBinItem) => {
    await api.restoreTrashItem(item.item_type, item.item_id);
    setStatus(`已恢复「${item.name}」。`);
    await refresh();
    await refreshDocuments(selectedId);
    await refreshTrash();
  };
  const purgeTrashItem = async (item: RecycleBinItem) => {
    const confirmation = window.prompt(`永久删除不可恢复。请输入完整名称「${item.name}」确认：`);
    if (confirmation !== item.name) {
      if (confirmation !== null) setStatus("名称不匹配，已取消永久删除。");
      return;
    }
    await api.purgeTrashItem(item.item_type, item.item_id, confirmation);
    setStatus(`已永久删除「${item.name}」。`);
    await refreshTrash();
  };
  const reprocessDocument = async (document: DocumentItem) => {
    setStatus(`正在重新解析 ${document.filename}...`);
    await api.reprocessDocument(document.id);
    await refreshDocuments(selectedId);
    window.setTimeout(() => refreshDocuments(selectedId), 1200);
  };
  const suggestions = ["总结这份资料的核心内容", "提炼产品的三个关键卖点", "基于资料生成营销文案"];

  return <div className="app-shell">
    <Sidebar items={knowledgeBases} selectedId={selectedId} sessions={sessions} activeSessionId={sessionId} view={view} onView={setView} onSelect={selectKb} onCreate={createKb} onNewChat={newChat} onSelectSession={selectSession} onDeleteSession={deleteSession} />
    <main className="workspace">
      <header className="topbar">
        <div className="breadcrumb"><span>{view === "chat" ? "智能问答" : view === "creation" ? "创作中心" : view === "trash" ? "回收站" : "文档管理"}</span><Icon name="chevron" size={13} /><strong>{view === "trash" ? `${trashItems.length} 个项目` : selected?.name || "未选择知识库"}</strong></div>
        <div className="top-actions"><button className="search-button"><Icon name="search" size={16} />搜索 <kbd>⌘ /</kbd></button><button className="icon-button" title="编辑知识库" disabled={!selected} onClick={editKb}><Icon name="edit" /></button><button className="icon-button danger" title="删除知识库" disabled={!selected} onClick={deleteKb}><Icon name="trash" /></button><button className="logout-button" title="退出登录" onClick={() => { localStorage.removeItem("token"); location.reload(); }}><Icon name="logout" /></button></div>
      </header>
      {view === "documents" ? <DocumentManager documents={documents} selected={selected} onUpload={upload} onDelete={deleteDocument} onReprocess={reprocessDocument} /> : view === "trash" ? <TrashManager items={trashItems} onRefresh={refreshTrash} onRestore={restoreTrashItem} onPurge={purgeTrashItem} /> : view === "creation" ? <CreationCenter selectedId={selectedId} selected={selected} onComplete={() => refreshSessions(selectedId)} /> : <><section className="conversation">
        {!messages.length ? <div className="welcome">
          <div className="welcome-icon"><Icon name="spark" size={27} /></div>
          <span className="kicker">KNOWLEDGE ASSISTANT</span>
          <h1>{selected ? `与「${selected.name}」对话` : "创建你的第一个知识库"}</h1>
          <p>{selected ? "我会检索当前知识库，并用清晰的引用告诉你答案来自哪里。" : "将分散的资料汇聚起来，让知识真正参与工作。"}</p>
          <div className="suggestions">{suggestions.map((item, index) => <button key={item} disabled={!selectedId} onClick={() => askQuestion(item)}><span>0{index + 1}</span>{item}<Icon name="chevron" size={15} /></button>)}</div>
        </div> : <div className="message-stream">
          {messages.map((message, index) => <article className={`message ${message.role}`} key={index}>
            <div className="message-avatar">{message.role === "user" ? "你" : <Icon name="spark" size={16} />}</div>
            <div className="message-body"><div className="message-meta"><strong>{message.role === "user" ? "你" : "知识助手"}</strong><span>刚刚</span></div><p>{message.content}</p>{!!message.citations?.length && <button className="citation-count"><Icon name="book" size={14} />查看 {message.citations.length} 条引用依据</button>}</div>
          </article>)}
          <div ref={messagesEnd} />
        </div>}
      </section>
      <form className="composer" onSubmit={ask}>
        {status && <div className="status"><span className="status-dot" />{status}</div>}
        <div className="composer-box"><textarea rows={1} value={question} onChange={(e) => setQuestion(e.target.value)} placeholder={selectedId ? "向知识库提问，或描述你想创作的内容..." : "请先创建或选择知识库"} /><div className="composer-tools"><div><button type="button" className="tool-button"><Icon name="plus" size={17} /></button><span>仅依据知识库回答</span></div><button className="send-button" disabled={!selectedId || !question.trim()}><Icon name="send" size={17} /></button></div></div>
        <small>AI 生成内容可能存在误差，请结合引用资料核验重要信息。</small>
      </form></>}
    </main>
    <SourcePanel documents={documents} citations={citations} onUpload={upload} />
  </div>;
}

function App() {
  const [ready, setReady] = useState(Boolean(localStorage.getItem("token")));
  const [notice, setNotice] = useState("");
  useEffect(() => {
    const expire = () => {
      setReady(false);
      setNotice("登录状态已过期，请重新登录。知识库资料仍保存在服务器中。");
    };
    window.addEventListener(AUTH_EXPIRED_EVENT, expire);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, expire);
  }, []);
  return ready ? <Workspace /> : <Login notice={notice} onReady={() => { setNotice(""); setReady(true); }} />;
}

createRoot(document.getElementById("root")!).render(<App />);

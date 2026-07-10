import type { ReactNode } from "react";
import {
  Activity,
  ArrowRight,
  Bot,
  Boxes,
  Braces,
  ClipboardCheck,
  Code2,
  Database,
  FileCheck2,
  FileSearch,
  FolderKanban,
  GitBranch,
  Layers3,
  LockKeyhole,
  Network,
  Route,
  Server,
  ShieldCheck,
  SquareTerminal,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import { cx } from "../../shared/lib/className";

const repositoryUrl = "https://github.com/yv1ing/Z3r0";
const docsOverviewUrl = "https://github.com/yv1ing/Z3r0/blob/main/docs/en/guide/overview.md";
const egressModes = ["Direct", "HTTP", "HTTPS", "SOCKS5"];

type LandingPrimaryAction = {
  label: string;
  href?: string;
  external?: boolean;
  onSelect?: () => void;
};

type LandingContentProps = {
  logoSrc: string;
  primaryAction: LandingPrimaryAction;
};

type CardItem = {
  title: string;
  text: string;
  icon: LucideIcon;
  kicker?: string;
  items?: string[];
};

type AgentItem = {
  code: string;
  name: string;
  role: string;
  detail: string;
  icon: LucideIcon;
};

const planes: CardItem[] = [
  {
    title: "控制平面",
    kicker: "FastAPI",
    text: "管理用户、会话、项目、智能体、主机和系统配置的认证资源。",
    icon: Braces,
    items: ["REST 资源", "WebSocket 会话", "访问控制"],
  },
  {
    title: "运行时平面",
    kicker: "多智能体会话",
    text: "协调主管与专家智能体，流式传输标准化事件，维护时间线连续性，并在后台任务完成时恢复执行。",
    icon: Workflow,
    items: ["会话运行时", "智能体关系图", "可回放时间线"],
  },
  {
    title: "证据平面",
    kicker: "WorkProject",
    text: "通过持久化的资产、漏洞发现、关系图边、攻击路径、任务和智能体摘要，将评估状态保持在模型上下文之外。",
    icon: FileCheck2,
    items: ["资产与范围", "发现与关系图", "攻击路径"],
  },
  {
    title: "执行平面",
    kicker: "本地 Shell",
    text: "在本地 Kali 环境中直接执行命令，提供 Shell、文件操作、后台任务和知识库集成。",
    icon: SquareTerminal,
    items: ["本地命令执行", "后台任务管理", "知识库集成"],
  },
];

const runtimePath: CardItem[] = [
  {
    title: "操作台",
    text: "React 控制台整合了聊天、项目记录、关系图、终端和文件操作。",
    icon: Layers3,
  },
  {
    title: "控制平面",
    text: "FastAPI 接收 REST 和 WebSocket 流量，解析会话、项目、用户边界。",
    icon: Braces,
  },
  {
    title: "会话运行时",
    text: "运行时执行选定的智能体关系图，将模型输出转为应用级事件。",
    icon: Bot,
  },
  {
    title: "工具层",
    text: "智能体工作到达项目记录、知识库、委派专家或本地执行环境。",
    icon: Workflow,
  },
  {
    title: "持久化",
    text: "PostgreSQL 存储时间线帧、项目证据、资源状态和后台任务状态。",
    icon: Database,
  },
];

const evidenceNodes: CardItem[] = [
  { title: "范围", text: "声明的目标和项目边界", icon: ShieldCheck },
  { title: "资产", text: "服务、域名、网络、二进制文件", icon: Boxes },
  { title: "关系", text: "结构和攻击关系图边", icon: GitBranch },
  { title: "发现", text: "证据、影响、严重度、状态", icon: FileSearch },
  { title: "攻击路径", text: "从访问入口到影响的有序遍历", icon: Route },
  { title: "审查", text: "记录、关系图、时间线回放", icon: ClipboardCheck },
];

const workbenchSurfaces: CardItem[] = [
  { title: "Playground", text: "实时对话、智能体选择、流式状态、子代理面板和本地命令执行。", icon: Activity },
  { title: "Work Projects", text: "项目元数据、所有者、范围资产、会话、记录、关系图和攻击路径。", icon: FolderKanban },
  { title: "System Users", text: "系统用户和角色管理。", icon: Server },
  { title: "System Config", text: "系统运行参数配置。", icon: Braces },
];

const agents: AgentItem[] = [
  { code: "cso", name: "玄幕", role: "安全主管 · 任务分解与协调", detail: "任务分解、团队协调、结果整合。", icon: Workflow },
  { code: "cae", name: "守拙", role: "代码审计专家", detail: "源码审计、依赖审查、修复验证。", icon: ClipboardCheck },
  { code: "cie", name: "观星", role: "情报侦察专家", detail: "情报收集、资产发现、关系测绘。", icon: FileSearch },
  { code: "cpe", name: "破军", role: "渗透测试专家", detail: "渗透测试、漏洞验证、影响确认。", icon: ShieldCheck },
  { code: "cre", name: "溯源", role: "逆向分析专家", detail: "逆向分析、固件反汇编、二进制脱壳。", icon: Code2 },
  { code: "cce", name: "破阵", role: "密码分析专家", detail: "密码分析、密钥审查、安全评估。", icon: LockKeyhole },
];

export function LandingContent({ logoSrc, primaryAction }: LandingContentProps) {
  return (
    <main className="landing-page">
      <div className="landing-grid" aria-hidden="true" />
      <div className="landing-scanline" aria-hidden="true" />

      <section className="landing-hero" aria-label="XuanMu landing page">
        <div className="landing-hero-copy">
          <img className="landing-hero-logo" src={logoSrc} width="1000" height="1000" alt="XuanMu logo" />
          <span className="page-eyebrow">开源红队智能体协作平台</span>
          <h1>XuanMu RedTeam Agent</h1>
          <p>面向授权渗透测试、漏洞挖掘、代码审计与安全研究的开源红队协作智能体平台。</p>
          <div className="landing-actions">
            <ActionLink action={primaryAction} primary />
            <ActionLink action={{ label: "GitHub", href: repositoryUrl, external: true }} icon={GitBranch} ghost />
          </div>
        </div>
        <ArchitecturePanel />
      </section>

      <Section eyebrow="四层架构" title="控制平面、运行时、证据、执行四层分离。"
        description="每一层映射到实际应用资源：API 路由和服务、会话运行时、WorkProject 记录、本地执行环境、PostgreSQL 持久化。">
        <div className="landing-card-grid landing-card-grid-4">
          {planes.map((item) => <Card key={item.title} item={item} accent />)}
        </div>
      </Section>

      <Section eyebrow="运行链路" title="实时交互、后台工作、时间线回放共享同一应用事件模型。">
        <div className="landing-card-grid landing-card-grid-5">
          {runtimePath.map((item, index) => <Card key={item.title} item={item} index={index} arrow={index < runtimePath.length - 1} />)}
        </div>
      </Section>

      <Section
        eyebrow="证据模型"
        title="WorkProject 将临时的调查输出转化为可复核的审查材料。"
        description="资产是关系图节点，关系是有向边，发现携带证据和影响，攻击路径重构访问或影响如何在图中推进。"
      >
        <div className="landing-card-grid landing-card-grid-6">
          {evidenceNodes.map((item, index) => <Card key={item.title} item={item} index={index} arrow={index < evidenceNodes.length - 1} />)}
        </div>
      </Section>

      <Section eyebrow="本地执行环境" title="命令执行、后台任务与知识库集成，直接在本地运行。">
        <div className="landing-panel landing-topology-copy">
          <h3>命令直接在本机执行，无需 Docker 沙箱。</h3>
          <p>所有 Shell 命令通过 Python asyncio 子进程在本地 Kali 环境直接运行。支持同步执行、后台长任务、输出文件读取和任务取消。</p>
          <p>知识库系统提供结构化的安全分析方法论，智能体可在执行前后查阅参考。</p>
        </div>
      </Section>

      <Section eyebrow="操作台" title="前端展示与后端控制平面相同的资源模型。">
        <div className="landing-card-grid landing-card-grid-3">
          {workbenchSurfaces.map((item) => <Card key={item.title} item={item} />)}
        </div>
      </Section>

      <Section eyebrow="智能体团队" title="专业角色映射了专业安全评估中的分工。">
        <div className="landing-card-grid landing-card-grid-3">
          {agents.map((agent) => <AgentCard key={agent.code} agent={agent} />)}
        </div>
      </Section>

      <Section className="landing-security" eyebrow="使用边界" title="仅限授权使用。">
        <div className="landing-panel landing-boundary">
          <p>玄幕红队智能体（XuanMu RedTeam Agent）仅限在合法且获得明确授权的范围内用于安全测试、风险评估、代码审计和研究。不授予测试、扫描、访问或影响任何第三方系统、网络、服务、账户或数据的权限。</p>
          <a className="landing-inline-link" href={docsOverviewUrl} target="_blank" rel="noopener noreferrer">
            Read the documentation
            <ArrowRight size={16} />
          </a>
        </div>
      </Section>
    </main>
  );
}

function Section({
  children,
  className = "",
  description,
  eyebrow,
  title,
}: {
  children: ReactNode;
  className?: string;
  description?: string;
  eyebrow: string;
  title: string;
}) {
  return (
    <section className={cx("landing-section", className)}>
      <div className="landing-section-heading">
        <span className="page-eyebrow">{eyebrow}</span>
        <h2>{title}</h2>
        {description ? <p>{description}</p> : null}
      </div>
      {children}
    </section>
  );
}

function ArchitecturePanel() {
  return (
    <div className="landing-panel landing-architecture-panel" aria-label="Z3r0 architecture overview">
      <div className="landing-panel-heading">
        <span className="page-eyebrow">System model</span>
        <h2>Workbench, API, runtime, evidence, sandbox, egress, and persistence are explicit layers.</h2>
      </div>
      <div className="landing-architecture-canvas">
        <div className="landing-diagram-node landing-diagram-wide">Authorized Operator</div>
        <div className="landing-api-row">
          <div className="landing-diagram-node">React Workbench</div>
          <ArrowRight size={17} />
          <div className="landing-diagram-node">FastAPI Control Plane</div>
        </div>
        <div className="landing-plane-row">
          {planes.map(({ icon: Icon, title }) => (
            <div className="landing-diagram-node landing-plane-node" key={title}>
              <Icon size={18} />
              <span>{title}</span>
            </div>
          ))}
        </div>
        <div className="landing-diagram-node landing-diagram-wide">
          <Database size={18} />
          <span>PostgreSQL persistence</span>
        </div>
      </div>
    </div>
  );
}

function Card({ accent = false, arrow, index, item }: { accent?: boolean; arrow?: boolean; index?: number; item: CardItem }) {
  const Icon = item.icon;
  return (
    <article className={cx("landing-card", accent && "landing-card-accent")}>
      <div className="landing-card-topline">
        <span>{item.kicker ?? (index != null ? String(index + 1).padStart(2, "0") : "")}</span>
        <Icon size={20} />
      </div>
      <h3>{item.title}</h3>
      <p>{item.text}</p>
      {item.items ? <ul>{item.items.map((entry) => <li key={entry}>{entry}</li>)}</ul> : null}
      {arrow ? <ArrowRight className="landing-card-arrow" size={18} aria-hidden="true" /> : null}
    </article>
  );
}

function AgentCard({ agent }: { agent: AgentItem }) {
  const Icon = agent.icon;
  return (
    <article className="landing-card landing-card-agent">
      <div className="landing-card-topline">
        <span>{agent.code}</span>
        <Icon size={18} />
      </div>
      <strong>{agent.name}</strong>
      <h3>{agent.role}</h3>
      <p>{agent.detail}</p>
    </article>
  );
}

function ActionLink({ action, ghost = false, icon: Icon = ShieldCheck, primary = false }: {
  action: LandingPrimaryAction;
  ghost?: boolean;
  icon?: LucideIcon;
  primary?: boolean;
}) {
  const className = cx(
    "landing-action-link",
    primary ? "landing-action-primary" : ghost ? "landing-action-ghost" : "landing-action-secondary",
  );

  const content = (
    <>
      <Icon size={17} />
      <span>{action.label}</span>
    </>
  );

  if (action.href) {
    return (
      <a className={className} href={action.href} target={action.external ? "_blank" : undefined} rel={action.external ? "noopener noreferrer" : undefined}>
        {content}
      </a>
    );
  }

  return <button className={className} type="button" onClick={action.onSelect}>{content}</button>;
}

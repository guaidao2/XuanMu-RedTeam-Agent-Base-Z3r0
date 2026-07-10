import { AtSign, Sparkles } from "lucide-react";
import { useMemo, useState, type RefObject } from "react";
import type { AgentImageInputPart, AgentInfo, AgentInputPart } from "../../shared/api/types";
import { formatDateTime } from "../../shared/lib/date";
import { ImagePreview, imageDataUrl, type ImagePreviewState } from "./ImagePreview";
import type { AgentTranscript, ChatNode } from "./chatState";
import { TranscriptContent } from "./Transcript";
import { emptyAgentTranscript, isTranscriptEmpty } from "./transcriptView";
import type { SubagentSelection } from "./subagentView";

type ChatStreamProps = {
  nodes: ChatNode[];
  streaming: boolean;
  agents: AgentInfo[];
  selectedSubagent: SubagentSelection | null;
  tailRef: RefObject<HTMLDivElement | null>;
  onOpenSubagent: (selection: SubagentSelection) => void;
};

type RenderedChatNode =
  | { kind: "user"; node: Extract<ChatNode, { kind: "user" }>; targetName: string }
  | { kind: "agent"; node: Extract<ChatNode, { kind: "agent" }>; agentName: string; live: boolean };

export function ChatStream({
  nodes,
  streaming,
  agents,
  selectedSubagent,
  tailRef,
  onOpenSubagent,
}: ChatStreamProps) {
  const [preview, setPreview] = useState<ImagePreviewState>(null);
  const agentNameByCode = useMemo(
    () => new Map(agents.map((a) => [a.code, a.name])),
    [agents],
  );
  const renderedNodes = useMemo(
    () => buildRenderedChatNodes(nodes, streaming, agentNameByCode),
    [agentNameByCode, nodes, streaming],
  );

  const openImagePreview = (image: AgentImageInputPart, index: number) => {
    setPreview({
      src: imageDataUrl(image),
      alt: `User attachment ${index + 1}`,
    });
  };

  const lastIndex = nodes.length - 1;
  const lastNode = nodes[lastIndex];

  return (
    <div className="chat-stream">
      {nodes.length === 0 ? <ChatEmptyState /> : renderedNodes.map((item) => {
        if (item.kind === "user") {
          return (
            <UserBubble
              key={item.node.id}
              content={item.node.content}
              displayText={item.node.displayText}
              targetName={item.targetName}
              createdAt={item.node.createdAt}
              onPreviewImage={openImagePreview}
            />
          );
        }
        return (
          <AgentBlock
            key={item.node.id}
            agentName={item.agentName}
            transcript={item.node}
            live={item.live}
            selectedSubagent={selectedSubagent}
            onOpenSubagent={onOpenSubagent}
          />
        );
      })}
      {streaming && lastNode?.kind === "user" ? (
        <AgentBlock
          key="pending-agent"
          agentName={resolveAgentName(agentNameByCode, lastNode.targetAgentCode)}
          transcript={emptyAgentTranscript()}
          live
          selectedSubagent={selectedSubagent}
          onOpenSubagent={onOpenSubagent}
        />
      ) : null}
      <div ref={tailRef} className="chat-tail" />
      <ImagePreview preview={preview} onClose={() => setPreview(null)} />
    </div>
  );
}

function ChatEmptyState() {
  return (
    <div className="chat-empty">
      <div className="chat-empty-mark">
        <Sparkles size={28} />
      </div>
      <h2>Start a new conversation</h2>
      <p>
        Ask the security operations agent anything
        <br />
        - penetration tests, code audits, or threat triage.
      </p>
    </div>
  );
}

function buildRenderedChatNodes(
  nodes: ChatNode[],
  streaming: boolean,
  agentNameByCode: Map<string, string>,
): RenderedChatNode[] {
  const rendered: RenderedChatNode[] = [];
  const lastIndex = nodes.length - 1;
  let lastTargetName = "";

  nodes.forEach((node, index) => {
    if (node.kind === "user") {
      lastTargetName = resolveAgentName(agentNameByCode, node.targetAgentCode);
      rendered.push({ kind: "user", node, targetName: lastTargetName });
      return;
    }

    const live = streaming && index === lastIndex;
    if (!live && isTranscriptEmpty(node)) return;
    rendered.push({ kind: "agent", node, agentName: node.agentName || lastTargetName, live });
  });

  return rendered;
}

function MessageTimestamp({ value }: { value: string }) {
  return <time className="message-timestamp" dateTime={value}>{formatDateTime(value)}</time>;
}

function resolveAgentName(agentNameByCode: Map<string, string>, agentCode: string) {
  return agentNameByCode.get(agentCode) ?? agentCode;
}

function UserBubble({
  content,
  displayText,
  targetName,
  createdAt,
  onPreviewImage,
}: {
  content: AgentInputPart[];
  displayText: string;
  targetName: string;
  createdAt: string;
  onPreviewImage: (image: AgentImageInputPart, index: number) => void;
}) {
  const textParts = content.filter((part): part is Extract<AgentInputPart, { type: "text" }> => part.type === "text");
  const imageParts = content.filter((part): part is AgentImageInputPart => part.type === "image");
  return (
    <div className="chat-row chat-row-user">
      <div className="chat-message chat-message-user">
        <MessageTimestamp value={createdAt} />
        <div className="user-bubble">
          {targetName ? (
            <span className="user-bubble-mention">
              <AtSign size={11} />
              <span>{targetName}</span>
            </span>
          ) : null}
          {textParts.length ? (
            <span className="user-bubble-text">{textParts.map((part) => part.text).join("\n\n")}</span>
          ) : displayText ? (
            <span className="user-bubble-text">{displayText}</span>
          ) : null}
          {imageParts.length ? (
            <div className="user-bubble-images">
              {imageParts.map((part, index) => (
                <button
                  key={`${part.media_type}:${index}:${part.data.length}`}
                  type="button"
                  className="user-bubble-image-button"
                  onClick={() => onPreviewImage(part, index)}
                  aria-label={`Preview attachment ${index + 1}`}
                >
                  <img
                    className="user-bubble-image"
                    src={imageDataUrl(part)}
                    alt="User attachment"
                  />
                </button>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function AgentBlock({
  agentName,
  transcript,
  live,
  selectedSubagent,
  onOpenSubagent,
}: {
  agentName: string;
  transcript: AgentTranscript;
  live: boolean;
  selectedSubagent: SubagentSelection | null;
  onOpenSubagent: (selection: SubagentSelection) => void;
}) {
  return (
    <div className="chat-row chat-row-agent">
      <div className="agent-block">
        <div className="agent-header">
          {agentName ? <span>{agentName}</span> : null}
          {live ? <span className="agent-pulse" /> : null}
          {transcript.createdAt ? <MessageTimestamp value={transcript.createdAt} /> : null}
        </div>
        <TranscriptContent
          transcript={transcript}
          live={live}
          pendingEmpty
          selectedSubagent={selectedSubagent}
          onOpenSubagent={onOpenSubagent}
        />
      </div>
    </div>
  );
}

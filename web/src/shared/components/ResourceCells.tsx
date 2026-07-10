import { Button, Tooltip } from "@douyinfe/semi-ui";
import { Eye, EyeOff, User } from "lucide-react";
import type { ReactNode } from "react";

type ResourceIdentityProps = {
  before?: ReactNode;
  icon?: ReactNode;
  title: ReactNode;
  detail?: ReactNode;
};

export function ResourceIdentity({ before, detail, icon, title }: ResourceIdentityProps) {
  return (
    <div className="resource-identity">
      {before}
      {icon ? <div className="resource-avatar">{icon}</div> : null}
      <div>
        <strong>{title}</strong>
        {detail ? <span>{detail}</span> : null}
      </div>
    </div>
  );
}

export function OwnerCell({ children }: { children: ReactNode }) {
  return (
    <span className="resource-inline-cell">
      <User size={13} />
      {children}
    </span>
  );
}

export function ResourceText({ children, title }: { children: ReactNode; title?: string }) {
  return <span className="resource-description" title={title}>{children}</span>;
}

export function SecretCell({
  hiddenText = "********",
  id,
  maskEmpty = false,
  onToggle,
  value,
  visible,
}: {
  hiddenText?: string;
  id: string;
  maskEmpty?: boolean;
  onToggle: () => void;
  value?: string;
  visible: boolean;
}) {
  const hasValue = Boolean(value);
  const label = `${visible ? "Hide" : "Show"} secret for ${id}`;

  return (
    <div className="resource-secret-cell">
      <code>{visible ? (value || "-") : hasValue || maskEmpty ? hiddenText : "-"}</code>
      <Tooltip content={visible ? "Hide secret" : "Show secret"}>
        <Button
          icon={visible ? <EyeOff size={14} /> : <Eye size={14} />}
          theme="borderless"
          type="tertiary"
          aria-label={label}
          onClick={onToggle}
        />
      </Tooltip>
    </div>
  );
}

export function RowActions({ children }: { children: ReactNode }) {
  return <div className="row-actions">{children}</div>;
}

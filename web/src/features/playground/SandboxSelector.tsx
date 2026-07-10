import { Select, Spin, Tag } from "@douyinfe/semi-ui";
import { Box } from "lucide-react";
import { useMemo } from "react";
import { SANDBOX_CONTAINER_STATUS } from "../../shared/api/generated/constants";
import type { SandboxContainer } from "../../shared/api/types";
import { cx } from "../../shared/lib/className";
import { SANDBOX_CONTAINER_STATUS_COLOR, SANDBOX_CONTAINER_STATUS_LABEL } from "../../shared/lib/labels";

type SandboxSelectorProps = {
  containers: SandboxContainer[];
  loading: boolean;
  value: number | null;
  className?: string;
  onChange: (containerId: number | null) => void;
};

const CONTAINER_ID_PREVIEW_LENGTH = 12;

export function SandboxSelector({ containers, loading, value, className = "", onChange }: SandboxSelectorProps) {
  const runningContainers = useMemo(
    () => containers.filter((container) => container.status === SANDBOX_CONTAINER_STATUS.RUNNING),
    [containers],
  );

  const optionList = runningContainers.map((container) => ({
    label: renderContainerOption(container),
    value: container.id,
  }));
  const selectedContainer = containers.find((container) => container.id === value) ?? null;

  return (
    <div className={cx("sandbox-selector", className)}>
      <Select
        prefix={<Box size={15} />}
        value={value ?? undefined}
        optionList={optionList}
        renderSelectedItem={() => renderContainerId(selectedContainer?.container_hash ?? "")}
        placeholder={loading ? "Loading sandboxes" : "Select sandbox"}
        emptyContent={loading ? <Spin size="small" /> : "No running sandbox"}
        disabled={loading || runningContainers.length === 0}
        showClear
        onClear={() => onChange(null)}
        onChange={(nextValue) => onChange(typeof nextValue === "number" ? nextValue : null)}
      />
    </div>
  );
}

function renderContainerOption(container: SandboxContainer) {
  return (
    <div className="sandbox-selector-option">
      <span>{container.container_name}</span>
      <small>Container ID: {renderContainerId(container.container_hash)}</small>
      <Tag color={SANDBOX_CONTAINER_STATUS_COLOR[container.status]}>
        {SANDBOX_CONTAINER_STATUS_LABEL[container.status]}
      </Tag>
    </div>
  );
}

function renderContainerId(containerHash: string) {
  if (!containerHash) return "Pending create";
  return containerHash.slice(0, CONTAINER_ID_PREVIEW_LENGTH);
}

import { Input, InputNumber, Select } from "@douyinfe/semi-ui";
import { Network, Package, Route } from "lucide-react";
import { useEffect, useState } from "react";
import type { CreateSandboxImageRequest } from "../../shared/api/types";
import { ResourceModal } from "../../shared/components/ResourceModal";

type SandboxImageFormModalProps = {
  open: boolean;
  saving: boolean;
  onCancel: () => void;
  onSubmit: (payload: CreateSandboxImageRequest) => Promise<void>;
};

const EMPTY: CreateSandboxImageRequest = {
  image_name: "sandbox-runtime:latest",
  control_proxy_port: 8000,
  supports_tor: false,
};

export function SandboxImageFormModal({ open, saving, onCancel, onSubmit }: SandboxImageFormModalProps) {
  const [values, setValues] = useState<CreateSandboxImageRequest>(EMPTY);

  useEffect(() => {
    if (open) setValues(EMPTY);
  }, [open]);

  return (
    <ResourceModal
      open={open}
      title="Create Sandbox Image"
      saving={saving}
      submitLabel="Create"
      submitDisabled={!values.image_name.trim() || values.control_proxy_port < 1 || values.control_proxy_port > 65535}
      onCancel={onCancel}
      onSubmit={() => onSubmit({
        image_name: values.image_name.trim(),
        control_proxy_port: values.control_proxy_port,
        supports_tor: values.supports_tor,
      })}
    >
      <label>
        <span>Image Name</span>
        <Input prefix={<Package size={16} />} value={values.image_name}
          placeholder="ghcr.io/org/image:latest" maxLength={255} required
          onChange={(image_name) => setValues((current) => ({ ...current, image_name }))}
        />
      </label>
      <label>
        <span>Control Port</span>
        <InputNumber
          prefix={<Network size={16} />}
          value={values.control_proxy_port}
          min={1}
          max={65535}
          onChange={(control_proxy_port) => {
            if (typeof control_proxy_port === "number") setValues((current) => ({ ...current, control_proxy_port }));
          }}
        />
      </label>
      <label>
        <span>Tor</span>
        <Select
          prefix={<Route size={16} />}
          value={values.supports_tor ? "supported" : "unsupported"}
          optionList={[
            { label: "Unsupported", value: "unsupported" },
            { label: "Supported", value: "supported" },
          ]}
          onChange={(value) => {
            if (value === "supported" || value === "unsupported") {
              setValues((current) => ({ ...current, supports_tor: value === "supported" }));
            }
          }}
        />
      </label>
    </ResourceModal>
  );
}

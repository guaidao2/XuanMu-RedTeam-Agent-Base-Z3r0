import { Input, InputNumber, Select, TextArea } from "@douyinfe/semi-ui";
import { KeyRound, Network, PlugZap, Server, ShieldCheck, User } from "lucide-react";
import { useEffect, useState } from "react";
import type { CreateManagedHostRequest, ManagedHost, UpdateManagedHostRequest } from "../../shared/api/types";
import { ResourceModal } from "../../shared/components/ResourceModal";

type HostFormValues = CreateManagedHostRequest;

const DEFAULT_LOCAL_HOST_ID = 1;
const DEFAULT_DOCKER_PLAIN_PORT = 2375;
const DEFAULT_DOCKER_TLS_PORT = 2376;

type HostFormModalProps = {
  open: boolean;
  host: ManagedHost | null;
  saving: boolean;
  onCancel: () => void;
  onCreate: (payload: CreateManagedHostRequest) => Promise<void>;
  onUpdate: (host: ManagedHost, payload: UpdateManagedHostRequest) => Promise<void>;
};

const TLS_OPTIONS = [
  { label: "Plain", value: "plain" },
  { label: "TLS", value: "tls" },
];

const CERT_FIELDS = [
  { field: "docker_client_ca_cert", label: "Docker Client CA Certificate" },
  { field: "docker_client_cert", label: "Docker Client Certificate" },
  { field: "docker_client_key", label: "Docker Client Key" },
] as const;

type HostCertField = (typeof CERT_FIELDS)[number]["field"];

const EMPTY_CERTIFICATES: Pick<HostFormValues, HostCertField> = {
  docker_client_ca_cert: "",
  docker_client_cert: "",
  docker_client_key: "",
};

const EMPTY: HostFormValues = {
  ip_address: "",
  ssh_port: 22,
  host_account: "root",
  host_password: "",
  docker_management_port: DEFAULT_DOCKER_PLAIN_PORT,
  docker_tls_enabled: false,
  ...EMPTY_CERTIFICATES,
};

function initial(host: ManagedHost | null): HostFormValues {
  if (!host) return EMPTY;
  return {
    ip_address: host.ip_address,
    ssh_port: host.ssh_port,
    host_account: host.host_account,
    host_password: host.host_password,
    docker_management_port: host.docker_management_port,
    docker_tls_enabled: host.docker_tls_enabled,
    docker_client_ca_cert: host.docker_client_ca_cert,
    docker_client_cert: host.docker_client_cert,
    docker_client_key: host.docker_client_key,
  };
}

export function HostFormModal({ open, host, saving, onCancel, onCreate, onUpdate }: HostFormModalProps) {
  const [values, setValues] = useState<HostFormValues>(() => initial(host));
  const editing = Boolean(host);
  const isLocalHostEdit = host?.id === DEFAULT_LOCAL_HOST_ID;

  useEffect(() => {
    if (open) setValues(initial(host));
  }, [open, host]);

  const setValue = <K extends keyof HostFormValues>(field: K, value: HostFormValues[K]) => {
    setValues((current) => ({ ...current, [field]: value }));
  };

  const setTlsMode = (mode: unknown) => {
    if (mode !== "plain" && mode !== "tls") return;
    setValues((current) => ({
      ...current,
      docker_tls_enabled: mode === "tls",
      docker_management_port: nextDockerPort(current.docker_management_port, mode),
      ...(mode === "plain" ? EMPTY_CERTIFICATES : {}),
    }));
  };

  const submit = async () => {
    const hostPayload = {
      ip_address: values.ip_address.trim(),
      ssh_port: values.ssh_port,
      host_account: values.host_account.trim(),
      host_password: values.host_password,
    };
    const dockerPayload = {
      docker_management_port: values.docker_management_port,
      docker_tls_enabled: values.docker_tls_enabled,
      ...(values.docker_tls_enabled ? trimmedCertificates(values) : EMPTY_CERTIFICATES),
    };

    if (!host) {
      await onCreate({ ...hostPayload, ...dockerPayload });
      return;
    }

    await onUpdate(host, { ...(isLocalHostEdit ? {} : hostPayload), ...dockerPayload });
  };

  const submitDisabled = (
    (!isLocalHostEdit && (
      !values.ip_address.trim()
      || !values.host_account.trim()
      || !values.host_password
      || invalidPort(values.ssh_port)
    ))
    || invalidPort(values.docker_management_port)
    || (values.docker_tls_enabled && certificatesMissing(values))
  );

  return (
    <ResourceModal
      open={open}
      title={editing ? "Edit Host" : "Create Host"}
      saving={saving}
      submitLabel={editing ? "Save" : "Create"}
      submitDisabled={submitDisabled}
      width={640}
      className="host-form-modal"
      onCancel={onCancel}
      onSubmit={submit}
    >
      <div className="host-form-row">
        <label>
          <span>IP Address</span>
          <Input prefix={<Server size={16} />} value={values.ip_address} maxLength={255} required
            autoComplete="off"
            disabled={isLocalHostEdit}
            onChange={(value) => setValue("ip_address", value)}
          />
        </label>
        <label>
          <span>SSH Port</span>
          <InputNumber prefix={<Network size={16} />} value={values.ssh_port} min={1} max={65535}
            disabled={isLocalHostEdit}
            onChange={(value) => typeof value === "number" && setValue("ssh_port", value)}
          />
        </label>
      </div>
      <div className="host-form-row">
        <label>
          <span>Host Account</span>
          <Input prefix={<User size={16} />} value={values.host_account} maxLength={128} required
            autoComplete="off"
            disabled={isLocalHostEdit}
            onChange={(value) => setValue("host_account", value)}
          />
        </label>
        <label>
          <span>Host Password</span>
          <Input mode="password" prefix={<KeyRound size={16} />} value={values.host_password} maxLength={512} required
            autoComplete="new-password"
            disabled={isLocalHostEdit}
            onChange={(value) => setValue("host_password", value)}
          />
        </label>
      </div>
      <div className="host-form-row">
        <label>
          <span>Docker Management Port</span>
          <InputNumber prefix={<PlugZap size={16} />} value={values.docker_management_port} min={1} max={65535}
            onChange={(value) => typeof value === "number" && setValue("docker_management_port", value)}
          />
        </label>
        <label>
          <span>Docker TLS Mode</span>
          <Select
            prefix={<ShieldCheck size={16} />}
            value={values.docker_tls_enabled ? "tls" : "plain"}
            optionList={TLS_OPTIONS}
            onChange={setTlsMode}
          />
        </label>
      </div>
      {values.docker_tls_enabled ? CERT_FIELDS.map(({ field, label }) => (
        <label key={field}>
          <span>{label}</span>
          <TextArea className="host-cert-textarea" value={values[field]} rows={4} resize="none" required
            onChange={(value) => setValue(field, value)}
          />
        </label>
      )) : null}
    </ResourceModal>
  );
}

function trimmedCertificates(values: HostFormValues): Pick<HostFormValues, HostCertField> {
  return {
    docker_client_ca_cert: values.docker_client_ca_cert.trim(),
    docker_client_cert: values.docker_client_cert.trim(),
    docker_client_key: values.docker_client_key.trim(),
  };
}

function certificatesMissing(values: HostFormValues) {
  return CERT_FIELDS.some(({ field }) => !values[field].trim());
}

function nextDockerPort(currentPort: number, mode: "plain" | "tls") {
  if (mode === "tls" && currentPort === DEFAULT_DOCKER_PLAIN_PORT) return DEFAULT_DOCKER_TLS_PORT;
  if (mode === "plain" && currentPort === DEFAULT_DOCKER_TLS_PORT) return DEFAULT_DOCKER_PLAIN_PORT;
  return currentPort;
}

function invalidPort(port: number) {
  return port < 1 || port > 65535;
}

import { Select } from "@douyinfe/semi-ui";
import { Boxes, Network, Route, Server, User } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { SANDBOX_CONTAINER_EGRESS_MODE } from "../../shared/api/generated/constants";
import type { CreateSandboxContainerRequest, EgressProxy, ManagedHost, SandboxContainerEgressMode, SandboxImage, SystemUser } from "../../shared/api/types";
import { ResourceModal } from "../../shared/components/ResourceModal";
import {
  createEmptyPortMapping,
  PortMappingEditor,
  type PortMappingFormValue,
} from "./PortMappingEditor";

type SandboxContainerFormModalProps = {
  open: boolean;
  saving: boolean;
  images: SandboxImage[];
  imagesLoading: boolean;
  hosts: ManagedHost[];
  hostsLoading: boolean;
  users: SystemUser[];
  usersLoading: boolean;
  egressProxies: EgressProxy[];
  egressProxiesLoading: boolean;
  currentUserId: number;
  onCancel: () => void;
  onSubmit: (payload: CreateSandboxContainerRequest) => Promise<void>;
};

export function SandboxContainerFormModal({
  open,
  saving,
  images,
  imagesLoading,
  hosts,
  hostsLoading,
  users,
  usersLoading,
  egressProxies,
  egressProxiesLoading,
  currentUserId,
  onCancel,
  onSubmit,
}: SandboxContainerFormModalProps) {
  const availableImages = useMemo(() => images, [images]);
  const [hostId, setHostId] = useState<number | undefined>();
  const [imageId, setImageId] = useState<number | undefined>();
  const [egressMode, setEgressMode] = useState<SandboxContainerEgressMode>(SANDBOX_CONTAINER_EGRESS_MODE.DIRECT);
  const [egressProxyId, setEgressProxyId] = useState<number | undefined>();
  const [ownerId, setOwnerId] = useState<number | undefined>();
  const [portMappings, setPortMappings] = useState<PortMappingFormValue[]>([]);
  const selectedImage = useMemo(() => images.find((image) => image.id === imageId), [imageId, images]);

  useEffect(() => {
    if (!open) return;
    setHostId(undefined);
    setImageId(undefined);
    setEgressMode(SANDBOX_CONTAINER_EGRESS_MODE.DIRECT);
    setEgressProxyId(undefined);
    setOwnerId(currentUserId);
    setPortMappings([]);
  }, [open, currentUserId]);

  const submit = () => onSubmit({
    host_id: hostId || 0,
    image_id: imageId || 0,
    egress_mode: egressMode,
    egress_proxy_id: egressMode === SANDBOX_CONTAINER_EGRESS_MODE.PROXY ? egressProxyId : undefined,
    owner_id: ownerId !== currentUserId ? ownerId : undefined,
    port_mappings: portMappings.map(({ container_port, host_port, protocol }) => ({
      container_port,
      host_port,
      protocol,
    })),
  });

  const updateMapping = (id: string, patch: Partial<PortMappingFormValue>) => {
    setPortMappings((current) => current.map((mapping) => (
      mapping.id === id ? { ...mapping, ...patch } : mapping
    )));
  };

  const removeMapping = (id: string) => {
    setPortMappings((current) => current.filter((item) => item.id !== id));
  };

  const addMapping = () => {
    setPortMappings((current) => [...current, createEmptyPortMapping()]);
  };

  const selectImage = (value: unknown) => {
    if (typeof value !== "number") return;
    const nextImage = images.find((image) => image.id === value);
    setImageId(value);
    if (!nextImage?.supports_tor && egressMode === SANDBOX_CONTAINER_EGRESS_MODE.TOR) {
      setEgressMode(SANDBOX_CONTAINER_EGRESS_MODE.DIRECT);
    }
  };

  const submitDisabled = (
    !hostId
    || !imageId
    || (egressMode === SANDBOX_CONTAINER_EGRESS_MODE.PROXY && !egressProxyId)
    || (egressMode === SANDBOX_CONTAINER_EGRESS_MODE.TOR && !selectedImage?.supports_tor)
  );

  return (
    <ResourceModal
      open={open}
      title="Create Sandbox Container"
      saving={saving}
      submitLabel="Create"
      submitDisabled={submitDisabled}
      width={640}
      onCancel={onCancel}
      onSubmit={submit}
    >
      <label>
        <span>Host</span>
        <Select
          prefix={<Server size={16} />}
          value={hostId}
          loading={hostsLoading}
          disabled={hosts.length === 0}
          placeholder="Select managed host"
          onChange={(value) => typeof value === "number" && setHostId(value)}
          optionList={hosts.map((host) => ({ label: `${host.ip_address}:${host.docker_management_port}`, value: host.id }))}
        />
      </label>

      <label>
        <span>Image</span>
        <Select
          prefix={<Boxes size={16} />}
          value={imageId}
          loading={imagesLoading}
          disabled={availableImages.length === 0}
          placeholder="Select a sandbox image"
          onChange={selectImage}
          optionList={availableImages.map((image) => ({
            label: `${image.image_name} · control ${image.control_proxy_port}`,
            value: image.id,
          }))}
        />
      </label>

      <label>
        <span>Owner</span>
        <Select
          prefix={<User size={16} />}
          value={ownerId}
          loading={usersLoading}
          placeholder="Select container owner"
          onChange={(value) => typeof value === "number" && setOwnerId(value)}
          optionList={users.map((u) => ({ label: u.username, value: u.id }))}
        />
      </label>

      <label>
        <span>Egress Mode</span>
        <Select
          prefix={<Route size={16} />}
          value={egressMode}
          optionList={[
            { label: "Direct", value: SANDBOX_CONTAINER_EGRESS_MODE.DIRECT },
            { label: "Managed Proxy", value: SANDBOX_CONTAINER_EGRESS_MODE.PROXY },
            { label: "Tor", value: SANDBOX_CONTAINER_EGRESS_MODE.TOR, disabled: !selectedImage?.supports_tor },
          ]}
          onChange={(value) => {
            if (typeof value !== "string") return;
            const next = value as SandboxContainerEgressMode;
            setEgressMode(next);
            if (next !== SANDBOX_CONTAINER_EGRESS_MODE.PROXY) setEgressProxyId(undefined);
          }}
        />
      </label>

      {egressMode === SANDBOX_CONTAINER_EGRESS_MODE.PROXY ? (
        <label>
          <span>Managed Proxy</span>
          <Select
            prefix={<Network size={16} />}
            value={egressProxyId}
            loading={egressProxiesLoading}
            placeholder="Select an egress proxy"
            emptyContent="No egress proxies"
            onChange={(value) => setEgressProxyId(typeof value === "number" ? value : undefined)}
            optionList={egressProxies.map((proxy) => ({ label: egressProxyOptionLabel(proxy), value: proxy.id }))}
          />
        </label>
      ) : null}

      <PortMappingEditor
        mappings={portMappings}
        onAdd={addMapping}
        onRemove={removeMapping}
        onChange={updateMapping}
      />
    </ResourceModal>
  );
}

function egressProxyOptionLabel(proxy: EgressProxy) {
  return `${proxy.proxy_type}://${proxy.proxy_host}:${proxy.proxy_port}`;
}

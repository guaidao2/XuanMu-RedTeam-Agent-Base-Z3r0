import { Button, Modal, Popconfirm, Select, Tag, Tooltip } from "@douyinfe/semi-ui";
import { Box, Boxes, Fingerprint, FolderOpen, Monitor, Network, Play, Route, Square, SquareTerminal, Trash2, User } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { queryEgressProxies } from "../../shared/api/egressProxies";
import { canOpenContainerNoVNC, createSandboxContainer, deleteSandboxContainer, querySandboxContainers, startSandboxContainer, stopSandboxContainer, updateSandboxContainerEgress } from "../../shared/api/sandboxContainers";
import { queryManagedHosts } from "../../shared/api/hosts";
import { querySandboxImages } from "../../shared/api/sandboxImages";
import { querySystemUsers } from "../../shared/api/systemUsers";
import { showApiError } from "../../shared/api/feedback";
import { SANDBOX_CONTAINER_EGRESS_MODE, SANDBOX_CONTAINER_STATUS } from "../../shared/api/generated/constants";
import type { CreateSandboxContainerRequest, EgressProxy, ManagedHost, SandboxContainer, SandboxContainerEgressMode, SandboxImage, SystemUser } from "../../shared/api/types";
import { ResourcePageShell } from "../../shared/components/ResourcePageShell";
import { ResourceTable, type ResourceColumn } from "../../shared/components/ResourceTable";
import { OwnerCell, ResourceIdentity, ResourceText, RowActions } from "../../shared/components/ResourceCells";
import { useAdminResourceHeader } from "../../shared/hooks/useAdminResourceHeader";
import { useOptionList } from "../../shared/hooks/useOptionList";
import { usePagedResourceList } from "../../shared/hooks/usePagedResourceList";
import { useResourceAction } from "../../shared/hooks/useResourceAction";
import { useResourceSubmit } from "../../shared/hooks/useResourceSubmit";
import { useAuth } from "../../shared/auth/AuthProvider";
import { formatDateTime } from "../../shared/lib/date";
import { SANDBOX_CONTAINER_STATUS_COLOR, SANDBOX_CONTAINER_STATUS_LABEL } from "../../shared/lib/labels";
import { UI_TEXT } from "../../shared/lib/uiText";
import { useContainerShell } from "../container-shell/ContainerShellProvider";
import { SandboxContainerFormModal } from "./SandboxContainerFormModal";

export function SandboxContainersPage() {
  const { user } = useAuth();
  const {
    items: containers, page, keyword, loading, loadItems: loadContainers, total, rangeStart, rangeEnd,
    setKeyword, search, previous, next, canGoBack, canGoNext,
  } = usePagedResourceList<SandboxContainer>({ query: querySandboxContainers });
  const [modalOpen, setModalOpen] = useState(false);
  const {
    items: images,
    loading: imagesLoading,
    load: loadReadyImages,
  } = useOptionList<SandboxImage>({ query: querySandboxImages });
  const {
    items: hosts,
    loading: hostsLoading,
    load: loadHosts,
  } = useOptionList<ManagedHost>({ query: queryManagedHosts });
  const {
    items: users,
    loading: usersLoading,
    load: loadUsers,
  } = useOptionList<SystemUser>({ query: querySystemUsers });
  const {
    items: egressProxies,
    loading: egressProxiesLoading,
    load: loadEgressProxies,
  } = useOptionList<EgressProxy>({ query: queryEgressProxies });
  const [egressModalContainer, setEgressModalContainer] = useState<SandboxContainer | null>(null);
  const { openFileManager, openNoVNC, openShell } = useContainerShell();

  const refreshAll = useCallback(async () => {
    await loadContainers();
    await loadReadyImages();
    await loadHosts();
    await loadUsers();
    await loadEgressProxies();
  }, [loadContainers, loadReadyImages, loadHosts, loadUsers, loadEgressProxies]);

  const { run: startContainer, busyId: startingId } = useResourceAction<SandboxContainer>(
    (container) => startSandboxContainer(container.id), loadContainers,
  );
  const { run: stopContainer, busyId: stoppingId } = useResourceAction<SandboxContainer>(
    (container) => stopSandboxContainer(container.id), loadContainers,
  );
  const { run: deleteContainer, busyId: deletingId } = useResourceAction<SandboxContainer>(
    (container) => deleteSandboxContainer(container.id), loadContainers,
  );

  useAdminResourceHeader({
    createLabel: "Create Container",
    refreshLabel: "Refresh sandbox containers",
    loading: loading || imagesLoading || hostsLoading || usersLoading || egressProxiesLoading,
    onCreate: () => setModalOpen(true),
    onRefresh: refreshAll,
  });

  const { saving, submit } = useResourceSubmit({
    onSuccess: async () => {
      setModalOpen(false);
      await loadContainers();
    },
  });

  const summary = useMemo(
    () => containers.reduce(
      (acc, container) => ({
        running: acc.running + (container.status === SANDBOX_CONTAINER_STATUS.RUNNING ? 1 : 0),
        created: acc.created + (container.status === SANDBOX_CONTAINER_STATUS.CREATED ? 1 : 0),
        stopped: acc.stopped + (container.status === SANDBOX_CONTAINER_STATUS.STOPPED ? 1 : 0),
      }),
      { running: 0, created: 0, stopped: 0 },
    ),
    [containers],
  );

  const handleCreate = (payload: CreateSandboxContainerRequest) => submit(() => createSandboxContainer(payload));

  const columns: ResourceColumn<SandboxContainer>[] = [
    {
      key: "container", header: "Container", width: "minmax(0, 0.88fr)",
      render: (container) => (
        <ResourceIdentity
          icon={<Box size={18} />}
          title={container.container_name}
          detail={<span className="container-hash"><Fingerprint size={13} />{renderContainerHash(container.container_hash)}</span>}
        />
      ),
    },
    {
      key: "status", header: "Status", width: "84px",
      render: (container) => (
        <Tag color={SANDBOX_CONTAINER_STATUS_COLOR[container.status]}>{SANDBOX_CONTAINER_STATUS_LABEL[container.status]}</Tag>
      ),
    },
    {
      key: "host", header: "Host", width: "150px",
      render: (container) => <ResourceText title={container.host_ip_address}>{container.host_ip_address}</ResourceText>,
    },
    {
      key: "image", header: "Image", width: "minmax(0, 0.62fr)",
      render: (container) => <ResourceText title={container.image_name}>{container.image_name}</ResourceText>,
    },
    {
      key: "owner", header: "Owner", width: "minmax(0, 0.58fr)",
      render: (container) => <OwnerCell>{container.owner_username}</OwnerCell>,
    },
    {
      key: "ports", header: "Ports", width: "minmax(0, 0.56fr)",
      render: (container) => renderContainerPorts(container),
    },
    {
      key: "egress", header: "Egress", width: "minmax(0, 0.48fr)",
      render: (container) => (
        <Tag color={egressTagColor(container.egress_mode)}>{container.egress_label || container.egress_mode.toUpperCase()}</Tag>
      ),
    },
    { key: "updated", header: "Updated", width: "200px", render: (c) => formatDateTime(c.updated_at) },
    {
      key: "actions", header: "Actions", width: "150px",
      render: (container) => (
        <RowActions>
          <Button icon={<FolderOpen size={15} />} theme="borderless" type="tertiary"
            disabled={container.status !== SANDBOX_CONTAINER_STATUS.RUNNING || container.control_proxy_host_port <= 0}
            aria-label={`Browse files for ${container.container_name}`} onClick={() => openFileManager(container)}
          />
          <Button icon={<SquareTerminal size={15} />} theme="borderless" type="tertiary"
            disabled={container.status !== SANDBOX_CONTAINER_STATUS.RUNNING || container.control_proxy_host_port <= 0}
            aria-label={`Connect shell for ${container.container_name}`} onClick={() => openShell(container)}
          />
          <Button icon={<Monitor size={15} />} theme="borderless" type="tertiary"
            disabled={container.status !== SANDBOX_CONTAINER_STATUS.RUNNING || !canOpenContainerNoVNC(container)}
            aria-label={`Connect screen for ${container.container_name}`} onClick={() => openNoVNC(container)}
          />
          <Button icon={<Network size={15} />} theme="borderless" type="tertiary"
            disabled={container.control_proxy_host_port <= 0}
            aria-label={`Set egress for ${container.container_name}`} onClick={() => setEgressModalContainer(container)}
          />
          <Button icon={<Play size={15} />} theme="borderless" type="primary"
            disabled={container.status !== SANDBOX_CONTAINER_STATUS.CREATED && container.status !== SANDBOX_CONTAINER_STATUS.STOPPED}
            loading={startingId === container.id}
            aria-label={`Start ${container.container_name}`} onClick={() => void startContainer(container)}
          />
          <Button icon={<Square size={15} />} theme="borderless" type="danger"
            disabled={container.status !== SANDBOX_CONTAINER_STATUS.RUNNING} loading={stoppingId === container.id}
            aria-label={`Stop ${container.container_name}`} onClick={() => void stopContainer(container)}
          />
          <Popconfirm title="Delete container" content={`Delete ${container.container_name}?`} okType="danger" cancelText={UI_TEXT.cancel} onConfirm={() => void deleteContainer(container)}>
            <Button icon={<Trash2 size={15} />} theme="borderless" type="danger"
              loading={deletingId === container.id} aria-label={`Delete ${container.container_name}`}
            />
          </Popconfirm>
        </RowActions>
      ),
    },
  ];

  return (
    <>
      <ResourcePageShell
        searchPlaceholder="Search container, image, owner, ports, or status"
        keyword={keyword}
        loading={loading}
        metrics={[
          { label: "Total", value: total },
          { label: "Running", value: summary.running },
          { label: "Created", value: summary.created },
          { label: "Stopped", value: summary.stopped },
        ]}
        empty={containers.length === 0}
        emptyIcon={<Boxes size={42} />}
        emptyTitle="No containers found"
        page={page}
        rangeStart={rangeStart}
        rangeEnd={rangeEnd}
        total={total}
        canGoBack={canGoBack}
        canGoNext={canGoNext}
        onKeywordChange={setKeyword}
        onSearch={search}
        onPrevious={previous}
        onNext={next}
      >
        <ResourceTable<SandboxContainer>
          ariaLabel="Sandbox containers"
          className="sandbox-containers-table"
          columns={columns}
          rows={containers}
          rowKey={(container) => container.id}
        />
      </ResourcePageShell>

      <SandboxContainerFormModal
        open={modalOpen}
        saving={saving}
        images={images}
        imagesLoading={imagesLoading}
        hosts={hosts}
        hostsLoading={hostsLoading}
        users={users}
        usersLoading={usersLoading}
        egressProxies={egressProxies}
        egressProxiesLoading={egressProxiesLoading}
        currentUserId={user?.id ?? 0}
        onCancel={() => setModalOpen(false)}
        onSubmit={handleCreate}
      />
      <ContainerEgressModal
        container={egressModalContainer}
        egressProxies={egressProxies}
        loading={egressProxiesLoading}
        onClose={() => setEgressModalContainer(null)}
        onSaved={async () => {
          setEgressModalContainer(null);
          await loadContainers();
        }}
      />
    </>
  );
}

function ContainerEgressModal({
  container,
  egressProxies,
  loading,
  onClose,
  onSaved,
}: {
  container: SandboxContainer | null;
  egressProxies: EgressProxy[];
  loading: boolean;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const [egressMode, setEgressMode] = useState<SandboxContainerEgressMode>(SANDBOX_CONTAINER_EGRESS_MODE.DIRECT);
  const [selectedProxyId, setSelectedProxyId] = useState<number | undefined>();
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setEgressMode(container?.egress_mode ?? SANDBOX_CONTAINER_EGRESS_MODE.DIRECT);
    setSelectedProxyId(container?.egress_proxy_id ?? undefined);
  }, [container]);

  const save = async () => {
    if (!container) return;
    setSaving(true);
    try {
      await updateSandboxContainerEgress(container.id, {
        egress_mode: egressMode,
        egress_proxy_id: egressMode === SANDBOX_CONTAINER_EGRESS_MODE.PROXY ? selectedProxyId : undefined,
      });
      await onSaved();
    } catch (error) {
      showApiError(error);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title={container ? `Egress: ${container.container_name}` : "Egress"}
      visible={Boolean(container)}
      width={460}
      okText={UI_TEXT.save}
      cancelText={UI_TEXT.cancel}
      confirmLoading={saving}
      okButtonProps={{
        type: "primary",
        disabled: egressMode === SANDBOX_CONTAINER_EGRESS_MODE.PROXY && !selectedProxyId,
      }}
      onOk={() => void save()}
      onCancel={onClose}
    >
      <div className="resource-form">
        <label>
          <span>Egress Mode</span>
          <Select
            prefix={<Route size={16} />}
            value={egressMode}
            optionList={[
              { label: "Direct", value: SANDBOX_CONTAINER_EGRESS_MODE.DIRECT },
              { label: "Managed Proxy", value: SANDBOX_CONTAINER_EGRESS_MODE.PROXY },
              { label: "Tor", value: SANDBOX_CONTAINER_EGRESS_MODE.TOR, disabled: !container?.supports_tor },
            ]}
            onChange={(value) => {
              if (typeof value !== "string") return;
              const next = value as SandboxContainerEgressMode;
              setEgressMode(next);
              if (next !== SANDBOX_CONTAINER_EGRESS_MODE.PROXY) setSelectedProxyId(undefined);
            }}
          />
        </label>
        {egressMode === SANDBOX_CONTAINER_EGRESS_MODE.PROXY ? (
          <label>
            <span>Managed Proxy</span>
            <Select
              prefix={<Network size={16} />}
              value={selectedProxyId}
              loading={loading}
              placeholder="Select an egress proxy"
              emptyContent="No egress proxies"
              optionList={egressProxies.map((proxy) => ({ label: egressProxyOptionLabel(proxy), value: proxy.id }))}
              onChange={(value) => setSelectedProxyId(typeof value === "number" ? value : undefined)}
            />
          </label>
        ) : null}
      </div>
    </Modal>
  );
}

function renderContainerHash(containerHash: string) {
  if (!containerHash) return <>Pending create</>;
  return <Tooltip content={containerHash}>{containerHash.slice(0, 12)}</Tooltip>;
}

function renderContainerPorts(container: SandboxContainer) {
  return (
    <div className="port-mapping-list">
      <Tag color="green">
        control {container.control_proxy_host_port}:{container.control_proxy_port}/tcp
      </Tag>
      {container.port_mappings.map((mapping) => (
        <Tag key={`${mapping.host_port}-${mapping.container_port}-${mapping.protocol}`} color="blue">
          {mapping.host_port}:{mapping.container_port}/{mapping.protocol}
        </Tag>
      ))}
    </div>
  );
}

function egressProxyOptionLabel(proxy: EgressProxy) {
  return `${proxy.proxy_type}://${proxy.proxy_host}:${proxy.proxy_port}`;
}

function egressTagColor(mode: SandboxContainerEgressMode) {
  if (mode === SANDBOX_CONTAINER_EGRESS_MODE.TOR) return "violet";
  if (mode === SANDBOX_CONTAINER_EGRESS_MODE.PROXY) return "blue";
  return "grey";
}

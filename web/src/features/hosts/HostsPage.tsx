import { Button, Modal, Popconfirm, Select, Table, Tag } from "@douyinfe/semi-ui";
import { Boxes, Download, Pencil, Server, SquareTerminal, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { createManagedHost, deleteManagedHost, listManagedHostImages, pullManagedHostImages, removeManagedHostImage, queryManagedHosts, updateManagedHost } from "../../shared/api/hosts";
import { querySandboxImages } from "../../shared/api/sandboxImages";
import { showApiError, showApiSuccess } from "../../shared/api/feedback";
import type { ManagedHost, ManagedHostImage, SandboxImage } from "../../shared/api/types";
import { ResourcePageShell } from "../../shared/components/ResourcePageShell";
import { ResourceTable, type ResourceColumn } from "../../shared/components/ResourceTable";
import { OwnerCell, ResourceIdentity, RowActions, SecretCell } from "../../shared/components/ResourceCells";
import { useAdminResourceHeader } from "../../shared/hooks/useAdminResourceHeader";
import { usePagedResourceList } from "../../shared/hooks/usePagedResourceList";
import { useResourceAction } from "../../shared/hooks/useResourceAction";
import { useResourceSubmit } from "../../shared/hooks/useResourceSubmit";
import { useVisibleResourceIds } from "../../shared/hooks/useVisibleResourceIds";
import { formatDateTime } from "../../shared/lib/date";
import { formatBytes } from "../../shared/lib/number";
import { UI_TEXT } from "../../shared/lib/uiText";
import { useContainerShell } from "../container-shell/ContainerShellProvider";
import { HostFormModal } from "./HostFormModal";

type ModalState = { mode: "create" } | { mode: "edit"; host: ManagedHost } | null;

export function HostsPage() {
  const {
    items: hosts, page, keyword, loading, loadItems: loadHosts, total, rangeStart, rangeEnd,
    setKeyword, search, previous, next, canGoBack, canGoNext,
  } = usePagedResourceList<ManagedHost>({ query: queryManagedHosts });
  const [modal, setModal] = useState<ModalState>(null);
  const [imageModalHost, setImageModalHost] = useState<ManagedHost | null>(null);
  const secrets = useVisibleResourceIds(hosts);
  const { openHostShell } = useContainerShell();
  const { run: deleteHost, busyId: deletingHostId } = useResourceAction<ManagedHost>(
    (host) => deleteManagedHost(host.id),
    loadHosts,
  );

  useAdminResourceHeader({
    createLabel: "Create Host",
    refreshLabel: "Refresh hosts",
    loading,
    onCreate: () => setModal({ mode: "create" }),
    onRefresh: loadHosts,
  });

  const { saving, submit } = useResourceSubmit({
    onSuccess: async () => {
      setModal(null);
      await loadHosts();
    },
  });

  const summary = useMemo(
    () => hosts.reduce(
      (acc, host) => ({
        ssh: acc.ssh + (host.ssh_port > 0 ? 1 : 0),
        docker: acc.docker + (host.docker_management_port > 0 ? 1 : 0),
      }),
      { ssh: 0, docker: 0 },
    ),
    [hosts],
  );

  const columns: ResourceColumn<ManagedHost>[] = [
    {
      key: "host", header: "Host", width: "minmax(0, 0.7fr)",
      render: (host) => (
        <ResourceIdentity icon={<Server size={18} />} title={host.ip_address} detail={`SSH ${host.ssh_port}`} />
      ),
    },
    {
      key: "account", header: "Account", width: "minmax(0, 0.5fr)",
      render: (host) => <OwnerCell>{host.host_account}</OwnerCell>,
    },
    {
      key: "password", header: "Password", width: "minmax(0, 0.6fr)",
      render: (host) => (
        <SecretCell id={host.ip_address} value={host.host_password} visible={secrets.isVisible(host.id)} maskEmpty onToggle={() => secrets.toggle(host.id)} />
      ),
    },
    {
      key: "docker", header: "Docker Port", width: "110px",
      render: (host) => host.docker_management_port,
    },
    {
      key: "tls", header: "Mode", width: "90px",
      render: (host) => (
        <Tag color={host.docker_tls_enabled ? "green" : "grey"}>
          {host.docker_tls_enabled ? "TLS" : "Plain"}
        </Tag>
      ),
    },
    { key: "updated", header: "Updated", width: "minmax(0, 0.7fr)", render: (host) => formatDateTime(host.updated_at) },
    {
      key: "actions", header: "Actions", width: "140px",
      render: (host) => (
        <RowActions>
          <Button icon={<SquareTerminal size={15} />} theme="borderless" type="tertiary"
            aria-label={`Connect shell for ${host.ip_address}`} onClick={() => openHostShell(host)}
          />
          <Button icon={<Boxes size={15} />} theme="borderless" type="tertiary"
            aria-label={`Manage images for ${host.ip_address}`} onClick={() => setImageModalHost(host)}
          />
          <Button icon={<Pencil size={15} />} theme="borderless" type="tertiary"
            aria-label={`Edit ${host.ip_address}`} onClick={() => setModal({ mode: "edit", host })}
          />
          <Popconfirm title="Delete host" content={`Delete ${host.ip_address}?`} okType="danger" cancelText={UI_TEXT.cancel} onConfirm={() => void deleteHost(host)}>
            <Button icon={<Trash2 size={15} />} theme="borderless" type="danger"
              loading={deletingHostId === host.id} aria-label={`Delete ${host.ip_address}`}
            />
          </Popconfirm>
        </RowActions>
      ),
    },
  ];

  return (
    <>
      <ResourcePageShell
        searchPlaceholder="Search IP, account, SSH port, or Docker port"
        keyword={keyword}
        loading={loading}
        metrics={[
          { label: "Total", value: total },
          { label: "SSH", value: summary.ssh },
          { label: "Docker Ports", value: summary.docker },
        ]}
        empty={hosts.length === 0}
        emptyIcon={<Server size={42} />}
        emptyTitle="No hosts found"
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
        <ResourceTable<ManagedHost>
          ariaLabel="Managed hosts"
          columns={columns}
          rows={hosts}
          rowKey={(host) => host.id}
        />
      </ResourcePageShell>

      <HostFormModal
        open={Boolean(modal)}
        host={modal?.mode === "edit" ? modal.host : null}
        saving={saving}
        onCancel={() => setModal(null)}
        onCreate={(payload) => submit(() => createManagedHost(payload))}
        onUpdate={(host, payload) => submit(() => updateManagedHost(host.id, payload))}
      />
      <HostImagesModal host={imageModalHost} onClose={() => setImageModalHost(null)} />
    </>
  );
}

function HostImagesModal({ host, onClose }: { host: ManagedHost | null; onClose: () => void }) {
  const [hostImages, setHostImages] = useState<ManagedHostImage[]>([]);
  const [systemImages, setSystemImages] = useState<SandboxImage[]>([]);
  const [selectedImageNames, setSelectedImageNames] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [pulling, setPulling] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);

  useEffect(() => {
    if (!host) return;
    setSelectedImageNames([]);
    setLoading(true);
    Promise.all([
      listManagedHostImages(host.id),
      querySandboxImages({ page: 1, size: 100, keyword: "" }),
    ])
      .then(([hostResponse, imageResponse]) => {
        setHostImages(hostResponse.data?.items ?? []);
        setSystemImages(imageResponse.data?.items ?? []);
      })
      .catch(showApiError)
      .finally(() => setLoading(false));
  }, [host]);

  const pullSelected = async () => {
    if (!host || selectedImageNames.length === 0) return;
    setPulling(true);
    try {
      const response = await pullManagedHostImages(host.id, { image_names: selectedImageNames });
      showApiSuccess(response);
      const refreshed = await listManagedHostImages(host.id);
      setHostImages(refreshed.data?.items ?? []);
      setSelectedImageNames([]);
    } catch (error) {
      showApiError(error);
    } finally {
      setPulling(false);
    }
  };

  const removeImage = async (image: ManagedHostImage) => {
    if (!host) return;
    setRemovingId(image.image_id);
    try {
      await removeManagedHostImage(host.id, { image_id: image.image_id, force: false });
      setHostImages((current) => current.filter((i) => i.image_id !== image.image_id));
    } catch (error) {
      showApiError(error);
    } finally {
      setRemovingId(null);
    }
  };

  return (
    <Modal
      title={host ? `Images on ${host.ip_address}` : "Host Images"}
      visible={Boolean(host)}
      width={680}
      footer={null}
      onCancel={onClose}
      className="host-images-modal"
    >
      <div className="host-images-toolbar">
        <Select
          multiple
          value={selectedImageNames}
          placeholder="Select images to pull"
          optionList={systemImages.map((image) => ({ label: image.image_name, value: image.image_name }))}
          onChange={(value) => setSelectedImageNames(Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [])}
        />
        <Button icon={<Download size={15} />} theme="solid" type="primary" loading={pulling} disabled={selectedImageNames.length === 0} onClick={() => void pullSelected()}>
          Pull
        </Button>
      </div>
      <Table
        loading={loading}
        dataSource={hostImages}
        pagination={false}
        size="small"
        rowKey={(record?: ManagedHostImage) => record?.image_id || record?.image_name || ""}
        columns={[
          { title: "Image", dataIndex: "image_name" },
          { title: "Hash", dataIndex: "image_hash", width: 120, render: (value) => String(value || "").slice(0, 12) || "-" },
          { title: "Size", dataIndex: "image_size", width: 100, render: (value) => formatBytes(Number(value || 0)) },
          {
            title: "", dataIndex: "image_id", width: 50,
            render: (_value, record) => (
              <Popconfirm title="Remove image" content={`Remove ${(record as ManagedHostImage).image_name || "this image"}?`} okType="danger" cancelText={UI_TEXT.cancel} onConfirm={() => void removeImage(record as ManagedHostImage)}>
                <Button icon={<Trash2 size={14} />} theme="borderless" type="danger" size="small"
                  loading={removingId === (record as ManagedHostImage).image_id}
                  aria-label="Remove image"
                />
              </Popconfirm>
            ),
          },
        ]}
      />
    </Modal>
  );
}

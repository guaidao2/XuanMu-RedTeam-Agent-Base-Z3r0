import { Button, Input, InputNumber, Select, Spin, Tag, TextArea } from "@douyinfe/semi-ui";
import { FolderKanban, Plus, ScanSearch, Server, Trash2, UserRound } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  WORK_PROJECT_ASSET_ORIGIN,
  getWorkProjectAssetTypes,
  getWorkProjectTypes,
  isWorkProjectAssetType,
  isWorkProjectType,
  WORK_PROJECT_ASSET_TYPE,
} from "../../shared/api/contract";
import { queryAvailableSandboxContainers } from "../../shared/api/sandboxContainers";
import { querySystemUsers } from "../../shared/api/systemUsers";
import type {
  CreateWorkProjectRequest,
  SandboxContainer,
  SystemUser,
  WorkProject,
  WorkProjectAssetRequest,
} from "../../shared/api/types";
import { ResourceModal } from "../../shared/components/ResourceModal";
import { useOptionList } from "../../shared/hooks/useOptionList";
import {
  SANDBOX_CONTAINER_STATUS_COLOR,
  SANDBOX_CONTAINER_STATUS_LABEL,
  SYSTEM_USER_ROLE_COLOR,
  SYSTEM_USER_ROLE_LABEL,
  WORK_PROJECT_ASSET_TYPE_LABEL,
  WORK_PROJECT_TYPE_LABEL,
} from "../../shared/lib/labels";

type WorkProjectFormModalProps = {
  open: boolean;
  saving: boolean;
  project?: WorkProject | null;
  onCancel: () => void;
  onSubmit: (payload: CreateWorkProjectRequest) => Promise<void>;
};

type SelectedOption = {
  value?: SystemUser["id"];
};

type AssetFormRow = WorkProjectAssetRequest & {
  existingId?: number;
};

type WorkProjectFormValues = Omit<CreateWorkProjectRequest, "assets"> & {
  assets: AssetFormRow[];
};

const projectTypes = getWorkProjectTypes();
const assetTypes = getWorkProjectAssetTypes();

const EMPTY_ASSET: AssetFormRow = {
  type: assetTypes[0],
  path: "",
  host: "",
  port: null,
};

const EMPTY: WorkProjectFormValues = {
  name: "",
  description: "",
  owner_user_ids: [],
  sandbox_container_ids: [],
  assets: [{ ...EMPTY_ASSET }],
  type: projectTypes[0],
};

export function WorkProjectFormModal({ open, saving, project, onCancel, onSubmit }: WorkProjectFormModalProps) {
  const [values, setValues] = useState<WorkProjectFormValues>(EMPTY);
  const { items: sandboxContainers, loading: sandboxLoading } = useOptionList<SandboxContainer>({
    enabled: open,
    query: queryAvailableSandboxContainers,
  });
  const { items: users, loading: usersLoading } = useOptionList<SystemUser>({
    enabled: open,
    query: querySystemUsers,
  });
  const editing = Boolean(project);

  useEffect(() => {
    if (!open) return;
    setValues(project ? {
      name: project.name,
      description: project.description,
      owner_user_ids: project.owner_user_ids,
      sandbox_container_ids: project.sandbox_container_ids,
      assets: scopeAssetsFromProject(project),
      type: project.type,
    } : { ...EMPTY, assets: [{ ...EMPTY_ASSET }] });
  }, [open, project]);

  const userOptionList = useMemo(() => users.map((user) => ({
    label: <UserOption user={user} />,
    value: user.id,
  })), [users]);

  const sandboxOptionList = useMemo(() => sandboxContainers.map((container) => ({
    label: <SandboxContainerOption container={container} />,
    value: container.id,
  })), [sandboxContainers]);
  const canSubmit = Boolean(values.name.trim()) && values.assets.length > 0
    && values.assets.every(isAssetComplete);

  const updateAsset = (index: number, patch: Partial<AssetFormRow>) => {
    setValues((current) => ({
      ...current,
      assets: current.assets.map((asset, assetIndex) => (
        assetIndex === index ? { ...asset, ...patch } : asset
      )),
    }));
  };

  const removeAsset = (index: number) => {
    setValues((current) => ({
      ...current,
      assets: current.assets.filter((_, assetIndex) => assetIndex !== index),
    }));
  };

  const submit = () => onSubmit({
    ...values,
    name: values.name.trim(),
    description: values.description.trim(),
    assets: values.assets.map(normalizeAsset).filter(isAssetComplete),
  });

  return (
    <ResourceModal
      open={open}
      title={editing ? "Edit Work Project" : "Create Work Project"}
      saving={saving}
      submitLabel={editing ? "Save" : "Create"}
      submitDisabled={!canSubmit}
      width={980}
      onCancel={onCancel}
      onSubmit={submit}
    >
      <div className="project-form-grid">
        <label>
          <span>Name</span>
          <Input prefix={<FolderKanban size={16} />} value={values.name} maxLength={255} required
            onChange={(name) => setValues((v) => ({ ...v, name }))}
          />
        </label>
        <label>
          <span>Type</span>
          <Select prefix={<ScanSearch size={16} />} value={values.type}
            onChange={(type) => isWorkProjectType(type) && setValues((v) => ({ ...v, type }))}
            optionList={projectTypes.map((type) => ({ label: WORK_PROJECT_TYPE_LABEL[type], value: type }))}
          />
        </label>
        <label>
          <span>Owners</span>
          <Select
            prefix={<UserRound size={16} />}
            value={values.owner_user_ids}
            optionList={userOptionList}
            placeholder={usersLoading ? "Loading users" : "Select project owners"}
            emptyContent={usersLoading ? <Spin size="small" /> : "No users"}
            loading={usersLoading}
            multiple
            renderSelectedItem={(option: SelectedOption) => ({
              isRenderInTag: true,
              content: users.find((user) => user.id === option.value)?.username ?? String(option.value ?? ""),
            })}
            showClear
            onClear={() => setValues((v) => ({ ...v, owner_user_ids: [] }))}
            onChange={(value) => setValues((v) => ({
              ...v,
              owner_user_ids: Array.isArray(value) ? value.filter((item): item is number => typeof item === "number") : [],
            }))}
          />
        </label>
        <label>
          <span>Sandbox Containers</span>
          <Select
            prefix={<Server size={16} />}
            value={values.sandbox_container_ids}
            optionList={sandboxOptionList}
            placeholder={sandboxLoading ? "Loading sandbox containers" : "Select sandbox containers"}
            emptyContent={sandboxLoading ? <Spin size="small" /> : "No running sandbox containers"}
            loading={sandboxLoading}
            multiple
            showClear
            renderSelectedItem={(option: { value?: number }) => ({
              isRenderInTag: true,
              content: sandboxContainers.find((container) => container.id === option.value)?.container_name ?? String(option.value ?? ""),
            })}
            onClear={() => setValues((v) => ({ ...v, sandbox_container_ids: [] }))}
            onChange={(value) => setValues((v) => ({
              ...v,
              sandbox_container_ids: Array.isArray(value) ? value.filter((item): item is number => typeof item === "number") : [],
            }))}
          />
        </label>
      </div>

      <label>
        <span>Description</span>
        <TextArea value={values.description} maxLength={2000} autosize={{ minRows: 3, maxRows: 6 }}
          onChange={(description) => setValues((v) => ({ ...v, description }))}
        />
      </label>

      <section className="project-assets-editor">
        <header>
          <span>Assets</span>
          <Button
            icon={<Plus size={14} />}
            size="small"
            theme="borderless"
            type="tertiary"
            onClick={() => setValues((v) => ({ ...v, assets: [...v.assets, { ...EMPTY_ASSET }] }))}
          >
            Add Asset
          </Button>
        </header>
        <div className="project-assets-rows">
          {values.assets.map((asset, index) => (
            <article key={index} className="project-asset-row">
              <label>
                <span>Type</span>
                <Select
                  value={asset.type}
                  disabled={Boolean(asset.existingId)}
                  optionList={assetTypes.map((type) => ({ label: WORK_PROJECT_ASSET_TYPE_LABEL[type], value: type }))}
                  onChange={(type) => isWorkProjectAssetType(type) && updateAsset(index, resetAssetForType(type))}
                />
              </label>
              {asset.type === WORK_PROJECT_ASSET_TYPE.BINARY ? (
                <label>
                  <span>Path</span>
                  <Input
                    value={asset.path}
                    maxLength={500}
                    required
                    onChange={(path) => updateAsset(index, { path })}
                  />
                </label>
              ) : (
                <>
                  <label>
                    <span>{ASSET_HOST_FIELD_LABEL[asset.type]}</span>
                    <Input value={asset.host} maxLength={255} onChange={(host) => updateAsset(index, { host })} />
                  </label>
                  {asset.type === WORK_PROJECT_ASSET_TYPE.SERVICE ? (
                    <label>
                      <span>Port</span>
                      <InputNumber value={asset.port ?? undefined} min={1} max={65535} onChange={(port) => updateAsset(index, { port: typeof port === "number" ? port : null })} />
                    </label>
                  ) : null}
                </>
              )}
              <Button
                icon={<Trash2 size={14} />}
                theme="borderless"
                type="danger"
                disabled={values.assets.length <= 1}
                aria-label="Remove asset"
                onClick={() => removeAsset(index)}
              />
            </article>
          ))}
        </div>
      </section>
    </ResourceModal>
  );
}

function UserOption({ user }: { user: SystemUser }) {
  return (
    <div className="project-user-option">
      <span>{user.username}</span>
      <small>{user.email || "No email"}</small>
      <Tag color={SYSTEM_USER_ROLE_COLOR[user.role]}>{SYSTEM_USER_ROLE_LABEL[user.role]}</Tag>
    </div>
  );
}

function SandboxContainerOption({ container }: { container: SandboxContainer }) {
  return (
    <div className="project-sandbox-option">
      <span>{container.container_name}</span>
      <small>ID: {container.id} · {container.container_hash || "Pending hash"}</small>
      <Tag color={SANDBOX_CONTAINER_STATUS_COLOR[container.status]}>
        {SANDBOX_CONTAINER_STATUS_LABEL[container.status]}
      </Tag>
    </div>
  );
}

function assetFromProject(asset: WorkProject["assets"][number]): AssetFormRow {
  return {
    existingId: asset.id,
    type: asset.type,
    path: asset.path,
    host: asset.host,
    port: asset.port,
  };
}

function scopeAssetsFromProject(project: WorkProject): AssetFormRow[] {
  const assets = project.assets
    .filter((asset) => asset.origin === WORK_PROJECT_ASSET_ORIGIN.SCOPE)
    .map(assetFromProject);
  return assets.length ? assets : [{ ...EMPTY_ASSET }];
}

function normalizeAsset(asset: AssetFormRow): WorkProjectAssetRequest {
  if (asset.type === WORK_PROJECT_ASSET_TYPE.BINARY) {
    return { type: asset.type, path: asset.path.trim(), host: "", port: null };
  }
  return {
    type: asset.type,
    path: "",
    host: asset.host.trim(),
    port: asset.type === WORK_PROJECT_ASSET_TYPE.SERVICE ? asset.port : null,
  };
}

function isAssetComplete(asset: WorkProjectAssetRequest): boolean {
  if (asset.type === WORK_PROJECT_ASSET_TYPE.BINARY) return Boolean(asset.path.trim());
  return Boolean(asset.host.trim());
}

function resetAssetForType(type: WorkProjectAssetRequest["type"]): Partial<AssetFormRow> {
  return { type, path: "", host: "", port: null };
}

// Label for the `host` input field, which carries a different identifier per asset type.
const ASSET_HOST_FIELD_LABEL: Record<Exclude<WorkProjectAssetRequest["type"], typeof WORK_PROJECT_ASSET_TYPE.BINARY>, string> = {
  [WORK_PROJECT_ASSET_TYPE.SERVICE]: "Host",
  [WORK_PROJECT_ASSET_TYPE.DOMAIN]: "Domain",
  [WORK_PROJECT_ASSET_TYPE.NETWORK]: "Network (CIDR)",
};

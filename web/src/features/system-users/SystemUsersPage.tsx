import { Button, Popconfirm, Tag } from "@douyinfe/semi-ui";
import { Pencil, Trash2, Users } from "lucide-react";
import { useMemo, useState } from "react";
import { createSystemUser, deleteSystemUser, querySystemUsers, updateSystemUser } from "../../shared/api/systemUsers";
import type { CreateSystemUserRequest, SystemUser, UpdateSystemUserRequest } from "../../shared/api/types";
import { ResourcePageShell } from "../../shared/components/ResourcePageShell";
import { ResourceTable, type ResourceColumn } from "../../shared/components/ResourceTable";
import { ResourceIdentity, RowActions } from "../../shared/components/ResourceCells";
import { useAdminResourceHeader } from "../../shared/hooks/useAdminResourceHeader";
import { usePagedResourceList } from "../../shared/hooks/usePagedResourceList";
import { useResourceAction } from "../../shared/hooks/useResourceAction";
import { useResourceSubmit } from "../../shared/hooks/useResourceSubmit";
import { formatDateTime } from "../../shared/lib/date";
import { SYSTEM_USER_ROLE_COLOR, SYSTEM_USER_ROLE_LABEL } from "../../shared/lib/labels";
import { UI_TEXT } from "../../shared/lib/uiText";
import { UserFormModal } from "./UserFormModal";

type ModalState = { mode: "create" } | { mode: "edit"; user: SystemUser } | null;

export function SystemUsersPage() {
  const {
    items: users, page, keyword, loading, loadItems: loadUsers, total, rangeStart, rangeEnd,
    setKeyword, search, previous, next, canGoBack, canGoNext,
  } = usePagedResourceList<SystemUser>({ query: querySystemUsers });
  const [modal, setModal] = useState<ModalState>(null);
  const { run: deleteUser, busyId: deletingUserId } = useResourceAction<SystemUser>(
    (user) => deleteSystemUser(user.id),
    loadUsers,
  );

  useAdminResourceHeader({
    createLabel: "Create User",
    refreshLabel: "Refresh users",
    loading,
    onCreate: () => setModal({ mode: "create" }),
    onRefresh: loadUsers,
  });

  const { saving, submit } = useResourceSubmit({
    onSuccess: async () => {
      setModal(null);
      await loadUsers();
    },
  });

  const summary = useMemo(
    () => users.reduce(
      (acc, user) => ({
        admin: acc.admin + (user.role === "admin" ? 1 : 0),
        user: acc.user + (user.role === "user" ? 1 : 0),
      }),
      { admin: 0, user: 0 },
    ),
    [users],
  );

  const columns: ResourceColumn<SystemUser>[] = [
    {
      key: "user", header: "User", width: "minmax(220px, 300px)",
      render: (user) => (
        <ResourceIdentity icon={user.username.slice(0, 1).toUpperCase()} title={user.username} detail={user.email || "-"} />
      ),
    },
    {
      key: "role", header: "Role", width: "190px",
      render: (user) => <Tag color={SYSTEM_USER_ROLE_COLOR[user.role]}>{SYSTEM_USER_ROLE_LABEL[user.role]}</Tag>,
    },
    { key: "created", header: "Created", width: "minmax(150px, 1fr)", render: (u) => formatDateTime(u.created_at) },
    { key: "updated", header: "Updated", width: "minmax(150px, 1fr)", render: (u) => formatDateTime(u.updated_at) },
    {
      key: "actions", header: "Actions", width: "104px",
      render: (user) => (
        <RowActions>
          <Button icon={<Pencil size={15} />} theme="borderless" type="tertiary" aria-label={`Edit ${user.username}`}
            onClick={() => setModal({ mode: "edit", user })}
          />
          <Popconfirm title="Delete user" content={`Delete ${user.username}?`} okType="danger" cancelText={UI_TEXT.cancel} onConfirm={() => void deleteUser(user)}>
            <Button icon={<Trash2 size={15} />} theme="borderless" type="danger"
              loading={deletingUserId === user.id} aria-label={`Delete ${user.username}`}
            />
          </Popconfirm>
        </RowActions>
      ),
    },
  ];

  return (
    <>
      <ResourcePageShell
        searchPlaceholder="Search username or email"
        keyword={keyword}
        loading={loading}
        metrics={[
          { label: "Total", value: total },
          { label: "Admins", value: summary.admin },
          { label: "Users", value: summary.user },
        ]}
        empty={users.length === 0}
        emptyIcon={<Users size={42} />}
        emptyTitle="No users found"
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
        <ResourceTable<SystemUser>
          ariaLabel="System users"
          columns={columns}
          rows={users}
          rowKey={(user) => user.id}
        />
      </ResourcePageShell>

      {modal?.mode === "edit" ? (
        <UserFormModal
          open mode="edit" user={modal.user} saving={saving}
          onCancel={() => setModal(null)}
          onSubmit={(payload: UpdateSystemUserRequest) => submit(() => updateSystemUser(modal.user.id, payload))}
        />
      ) : (
        <UserFormModal
          open={modal?.mode === "create"} mode="create" user={null} saving={saving}
          onCancel={() => setModal(null)}
          onSubmit={(payload: CreateSystemUserRequest) => submit(() => createSystemUser(payload))}
        />
      )}
    </>
  );
}

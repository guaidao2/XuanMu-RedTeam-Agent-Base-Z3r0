import { Input, Select } from "@douyinfe/semi-ui";
import { KeyRound, Mail, Shield, User } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { getSystemUserRoles, isSystemUserRole } from "../../shared/api/contract";
import type { CreateSystemUserRequest, SystemUser, SystemUserRole, UpdateSystemUserRequest } from "../../shared/api/types";
import { ResourceModal } from "../../shared/components/ResourceModal";
import { SYSTEM_USER_ROLE_LABEL } from "../../shared/lib/labels";

type UserFormValues = {
  username: string;
  email: string;
  password: string;
  role: SystemUserRole;
};

type UserFormModalProps =
  | {
      open: boolean;
      mode: "create";
      user: null;
      saving: boolean;
      onCancel: () => void;
      onSubmit: (payload: CreateSystemUserRequest) => Promise<void>;
    }
  | {
      open: boolean;
      mode: "edit";
      user: SystemUser;
      saving: boolean;
      onCancel: () => void;
      onSubmit: (payload: UpdateSystemUserRequest) => Promise<void>;
    };

const EMPTY: UserFormValues = { username: "", email: "", password: "", role: "user" };

function initial(user: SystemUser | null): UserFormValues {
  if (!user) return EMPTY;
  return { username: user.username, email: user.email, password: "", role: user.role };
}

export function UserFormModal({ open, mode, user, saving, onCancel, onSubmit }: UserFormModalProps) {
  const [values, setValues] = useState<UserFormValues>(() => initial(user));
  const roles = useMemo(() => getSystemUserRoles(), []);

  useEffect(() => {
    if (open) setValues(initial(user));
  }, [open, user]);

  const submit = async () => {
    const base = { username: values.username.trim(), email: values.email.trim(), role: values.role };
    if (mode === "create") {
      await onSubmit({ ...base, password: values.password });
    } else {
      await onSubmit(values.password ? { ...base, password: values.password } : base);
    }
  };

  return (
    <ResourceModal
      open={open}
      title={mode === "create" ? "Create User" : "Edit User"}
      saving={saving}
      submitLabel={mode === "create" ? "Create" : "Save"}
      onCancel={onCancel}
      onSubmit={submit}
    >
      <label>
        <span>Username</span>
        <Input prefix={<User size={16} />} value={values.username} maxLength={64} required
          onChange={(username) => setValues((v) => ({ ...v, username }))}
        />
      </label>
      <label>
        <span>Email</span>
        <Input type="email" prefix={<Mail size={16} />} value={values.email} maxLength={255}
          onChange={(email) => setValues((v) => ({ ...v, email }))}
        />
      </label>
      <label>
        <span>Role</span>
        <Select prefix={<Shield size={16} />} value={values.role}
          onChange={(role) => isSystemUserRole(role) && setValues((v) => ({ ...v, role }))}
          optionList={roles.map((role) => ({ label: SYSTEM_USER_ROLE_LABEL[role], value: role }))}
        />
      </label>
      <label>
        <span>Password</span>
        <Input mode="password" prefix={<KeyRound size={16} />} value={values.password} maxLength={128}
          required={mode === "create"}
          placeholder={mode === "create" ? "Password" : "Leave blank to keep current password"}
          onChange={(password) => setValues((v) => ({ ...v, password }))}
        />
      </label>
    </ResourceModal>
  );
}

import { Button, Modal } from "@douyinfe/semi-ui";
import { FormEvent, ReactNode } from "react";
import { UI_TEXT } from "../lib/uiText";

type ResourceModalProps = {
  open: boolean;
  title: string;
  saving: boolean;
  submitLabel: string;
  submitDisabled?: boolean;
  width?: number;
  className?: string;
  onCancel: () => void;
  onSubmit: () => void | Promise<void>;
  children: ReactNode;
};

export function ResourceModal({
  open,
  title,
  saving,
  submitLabel,
  submitDisabled = false,
  width = 520,
  className,
  onCancel,
  onSubmit,
  children,
}: ResourceModalProps) {
  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await onSubmit();
  };

  return (
    <Modal
      title={title}
      visible={open}
      onCancel={onCancel}
      footer={null}
      width={width}
      maskClosable={!saving}
      className={className}
    >
      <form className="resource-form" onSubmit={handleSubmit}>
        {children}
        <div className="modal-actions">
          <Button type="tertiary" onClick={onCancel} disabled={saving}>{UI_TEXT.cancel}</Button>
          <Button htmlType="submit" theme="solid" type="primary" loading={saving} disabled={submitDisabled}>{submitLabel}</Button>
        </div>
      </form>
    </Modal>
  );
}

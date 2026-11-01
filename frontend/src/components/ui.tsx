"use client";

import {
  ButtonHTMLAttributes, Children, cloneElement, createContext, isValidElement,
  ReactElement, ReactNode, useContext, useEffect, useId, useRef, useState,
} from "react";

export function Button({ variant = "primary", busy, children, disabled, className = "", ...props }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "text" | "danger"; busy?: boolean }) {
  return <button {...props} disabled={disabled || busy} aria-busy={busy || undefined} className={`ui-button ui-button--${variant} ${className}`}>{children}</button>;
}

export function Notice({ tone = "info", title, children }: { tone?: "info" | "success" | "warning" | "error"; title?: string; children: ReactNode }) {
  return <div className={`ui-notice ui-notice--${tone}`} role={tone === "error" ? "alert" : "status"}>{title && <strong>{title}</strong>}<div>{children}</div></div>;
}

export function StatusBadge({ status }: { status: string }) {
  const tone = /^(published|active|clean|approved|completed|accepted|open)$/.test(status) ? "success"
    : /^(error|infected|quarantined|declined|retracted)$/.test(status) ? "error"
    : /^(pending|needs_verification|revision_requested|unavailable)$/.test(status) ? "warning" : "neutral";
  return <span className={`ui-badge ui-badge--${tone}`}>{status.replaceAll("_", " ").replaceAll("-", " ")}</span>;
}

export function LoadingState({ children = "Loading your workspace..." }: { children?: ReactNode }) {
  return <p className="ui-loading" role="status"><span aria-hidden="true" className="ui-loading__mark" />{children}</p>;
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="ui-empty"><h3>{title}</h3>{children && <div>{children}</div>}</div>;
}

export function FormSection({ title, description, children, className = "" }: { title: string; description?: string; children: ReactNode; className?: string }) {
  return <fieldset className={`form-section ${className}`}><legend>{title}</legend>{description && <p className="form-help">{description}</p>}{children}</fieldset>;
}

type FieldControl = { id?: string; required?: boolean; "aria-invalid"?: boolean; "aria-describedby"?: string };
export function FormField({ label, hint, error, required, children, id, className = "" }: { label: string; hint?: string; error?: string; required?: boolean; children: ReactElement<FieldControl>; id?: string; className?: string }) {
  const generated = useId();
  const fieldId = id ?? generated;
  const describedBy = [hint && `${fieldId}-hint`, error && `${fieldId}-error`, children.props["aria-describedby"]].filter(Boolean).join(" ") || undefined;
  const control = Children.only(children);
  return <div className={`ui-field ${className}`}><label htmlFor={fieldId}>{label}{required && <><span aria-hidden="true" className="required-mark"> *</span><span className="visually-hidden"> (required)</span></>}</label>{isValidElement(control) && cloneElement(control, { id: fieldId, required: required ?? children.props.required, "aria-invalid": error ? true : undefined, "aria-describedby": describedBy })}{hint && <p id={`${fieldId}-hint`} className="form-help">{hint}</p>}{error && <p id={`${fieldId}-error`} className="field-error">{error}</p>}</div>;
}

type ConfirmOptions = { title: string; description: string; confirmLabel?: string; danger?: boolean };
type Confirm = (options: ConfirmOptions) => Promise<boolean>;
const ConfirmContext = createContext<Confirm | null>(null);

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [options, setOptions] = useState<ConfirmOptions | null>(null);
  const resolver = useRef<((value: boolean) => void) | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  const heading = useId();
  const description = useId();

  function finish(value: boolean) {
    dialog.current?.close();
    resolver.current?.(value);
    resolver.current = null;
    setOptions(null);
    previousFocus.current?.focus();
  }

  useEffect(() => {
    if (options) { dialog.current?.showModal(); cancel.current?.focus(); }
  }, [options]);
  useEffect(() => () => resolver.current?.(false), []);

  const confirm: Confirm = (next) => new Promise(resolve => {
    resolver.current?.(false);
    previousFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    resolver.current = resolve;
    setOptions(next);
  });

  return <ConfirmContext.Provider value={confirm}>{children}
    <dialog ref={dialog} className="confirmation-dialog" aria-labelledby={heading} aria-describedby={description} onKeyDown={event => {
      if (event.key !== "Tab") return;
      const controls = dialog.current?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)");
      if (!controls?.length) return;
      const first = controls[0]; const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }} onCancel={event => { event.preventDefault(); finish(false); }}>
      {options && <><h2 id={heading}>{options.title}</h2><p id={description}>{options.description}</p><div className="form-actions"><button ref={cancel} className="secondary-button" type="button" onClick={() => finish(false)}>Cancel</button><Button type="button" variant={options.danger ? "danger" : "primary"} onClick={() => finish(true)}>{options.confirmLabel ?? "Confirm"}</Button></div></>}
    </dialog>
  </ConfirmContext.Provider>;
}

export function useConfirm(): Confirm {
  const confirm = useContext(ConfirmContext);
  if (!confirm) throw new Error("useConfirm must be used within ConfirmProvider");
  return confirm;
}

"use client";

import { forwardRef, useState, type InputHTMLAttributes } from "react";
import { JournalIcon } from "@/components/journal-art";

export const PasswordInput = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function PasswordInput(props, ref) {
  const [visible, setVisible] = useState(false);
  return <div className="password-input"><input {...props} ref={ref} type={visible ? "text" : "password"} /><button type="button" className="password-input__toggle" onClick={() => setVisible(value => !value)} aria-label={visible ? "Hide password" : "Show password"} aria-pressed={visible} aria-controls={props.id}><JournalIcon name={visible ? "eyeOff" : "eye"} size={18} /></button></div>;
});

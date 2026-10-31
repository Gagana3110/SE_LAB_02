import { InputHTMLAttributes } from "react";

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
}

export function Field({ label, ...input }: FieldProps) {
  return (
    <label className="field">
      <span>{label}</span>
      <input {...input} />
    </label>
  );
}

export function ErrorMessage({ text }: { text: string }) {
  return text ? (
    <p className="message error" role="alert">
      {text}
    </p>
  ) : null;
}

export function SuccessMessage({ text }: { text: string }) {
  return text ? (
    <p className="message success" role="status">
      {text}
    </p>
  ) : null;
}

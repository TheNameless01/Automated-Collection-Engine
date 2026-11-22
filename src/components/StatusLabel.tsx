import { AlertTriangle, CheckCircle2, Clock, XCircle } from 'lucide-react';
import type { VerificationStatus } from '../types';

interface StatusLabelProps {
  status: VerificationStatus | string;
  label?: string;
}

export function StatusLabel({ status, label }: StatusLabelProps) {
  const text = label || status;
  if (status === 'VERIFIED') {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-700 whitespace-nowrap shrink-0">
        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
        <span>{text}</span>
      </span>
    );
  }
  if (status === 'NEEDS_REVIEW') {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-amber-700 whitespace-nowrap shrink-0">
        <AlertTriangle className="w-3.5 h-3.5 text-amber-600 shrink-0" />
        <span>{text}</span>
      </span>
    );
  }
  if (status === 'CLOSED') {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-rose-700 whitespace-nowrap shrink-0">
        <XCircle className="w-3.5 h-3.5 text-rose-600 shrink-0" />
        <span>{text}</span>
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-600 whitespace-nowrap shrink-0">
      <Clock className="w-3.5 h-3.5 text-slate-400 shrink-0" />
      <span>{text}</span>
    </span>
  );
}

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type {
  AmortizationPreviewBody,
  AppConfig,
  ConfirmBody,
  ParseBeanRequest,
  PreviewBody,
  ScheduleCreate,
  ScheduleEventBody,
} from "./types";

export const qk = {
  schedules: ["schedules"] as const,
  inbox: ["inbox"] as const,
  history: ["history"] as const,
  historyCheck: ["history", "check"] as const,
  accounts: ["accounts"] as const,
  currencies: ["currencies"] as const,
  config: ["config"] as const,
  beanFiles: ["bean-files"] as const,
  preview: (id: number, body: PreviewBody) => ["preview", id, body] as const,
  amortization: (body: AmortizationPreviewBody) => ["amortization", body] as const,
  // Under the "history" prefix so history-wide invalidation refreshes it too.
  written: (id: number) => ["history", id, "written"] as const,
};

export function useSchedules() {
  return useQuery({ queryKey: qk.schedules, queryFn: api.listSchedules });
}

export function useCreateSchedule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ScheduleCreate) => api.createSchedule(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.schedules });
      qc.invalidateQueries({ queryKey: qk.inbox });
    },
  });
}

export function useUpdateSchedule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: ScheduleCreate }) =>
      api.updateSchedule(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.schedules });
      // Editing the rule can delete (or later add) pending occurrences.
      qc.invalidateQueries({ queryKey: qk.inbox });
    },
  });
}

// Pure transform (no server-state change) so there is nothing to invalidate.
export function useParseTransaction() {
  return useMutation({
    mutationFn: (body: ParseBeanRequest) => api.parseTransaction(body),
  });
}

// Live amortization preview for a draft loan. `enabled` gates it on complete
// params; a bad request (422) is deterministic — don't retry it.
export function usePreviewAmortization(body: AmortizationPreviewBody, enabled: boolean) {
  return useQuery({
    queryKey: qk.amortization(body),
    queryFn: () => api.previewAmortization(body),
    enabled,
    retry: false,
  });
}

export function useAddScheduleEvent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: ScheduleEventBody }) =>
      api.addScheduleEvent(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.schedules });
      // A prepayment/rate change reshapes upcoming occurrences.
      qc.invalidateQueries({ queryKey: qk.inbox });
    },
  });
}

export function useDeleteScheduleEvent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, eventId }: { id: number; eventId: number }) =>
      api.deleteScheduleEvent(id, eventId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.schedules });
      qc.invalidateQueries({ queryKey: qk.inbox });
    },
  });
}

export function useDeleteSchedule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.deleteSchedule(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.schedules }),
  });
}

export function useInbox() {
  return useQuery({ queryKey: qk.inbox, queryFn: api.getInbox });
}

export function usePreview(id: number, body: PreviewBody, enabled: boolean) {
  return useQuery({
    queryKey: qk.preview(id, body),
    queryFn: () => api.previewTransient(id, body),
    enabled,
  });
}

export function useConfirm() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: ConfirmBody }) =>
      api.confirm(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.inbox });
      // A confirmed occurrence enters the history list.
      qc.invalidateQueries({ queryKey: qk.history });
      // Confirming may create the schedule's target file on disk.
      qc.invalidateQueries({ queryKey: qk.beanFiles });
    },
  });
}

export function useSkip() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.skip(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.inbox });
      // A skipped occurrence enters the history list.
      qc.invalidateQueries({ queryKey: qk.history });
    },
  });
}

export function useMarkPaidOutside() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.markPaidOutside(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.inbox });
      qc.invalidateQueries({ queryKey: qk.schedules });
    },
  });
}

export function useHistory() {
  return useQuery({ queryKey: qk.history, queryFn: api.getHistory });
}

export function useHistoryCheck() {
  // 422 (ledger not configured/missing) is deterministic — don't retry it.
  return useQuery({
    queryKey: qk.historyCheck,
    queryFn: api.checkHistory,
    retry: false,
  });
}

export function useReadd() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.readd(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.history });
      qc.invalidateQueries({ queryKey: qk.historyCheck });
    },
    // A 409 means the ledger changed under us — refresh the check too.
    onError: () => qc.invalidateQueries({ queryKey: qk.historyCheck }),
  });
}

export function useWritten(id: number, enabled: boolean) {
  // 409 (state changed under the dialog) is deterministic — don't retry it.
  return useQuery({
    queryKey: qk.written(id),
    queryFn: () => api.getWritten(id),
    enabled,
    retry: false,
  });
}

export function useUnconfirm() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.unconfirm(id),
    onSuccess: () => {
      // The occurrence is pending again: refresh the inbox plus everything
      // under the history prefix (list, reconcile check, written blocks).
      qc.invalidateQueries({ queryKey: qk.inbox });
      qc.invalidateQueries({ queryKey: qk.history });
    },
    // Same as useReadd: a 409 means the ledger changed under us — refresh the
    // check so the row's missing/present state catches up.
    onError: () => qc.invalidateQueries({ queryKey: qk.historyCheck }),
  });
}

export function useUnskip() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.unskip(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.inbox });
      qc.invalidateQueries({ queryKey: qk.history });
    },
  });
}

export function useAccounts() {
  return useQuery({ queryKey: qk.accounts, queryFn: api.accounts });
}

export function useBeanFiles() {
  return useQuery({ queryKey: qk.beanFiles, queryFn: api.beanFiles });
}

export function useCurrencies() {
  return useQuery({ queryKey: qk.currencies, queryFn: api.currencies });
}

export function useConfig() {
  return useQuery({ queryKey: qk.config, queryFn: api.getConfig });
}

export function useUpdateConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AppConfig) => api.updateConfig(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.config }),
  });
}

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { AppConfig, ConfirmBody, PreviewBody, ScheduleCreate } from "./types";

export const qk = {
  schedules: ["schedules"] as const,
  inbox: ["inbox"] as const,
  accounts: ["accounts"] as const,
  currencies: ["currencies"] as const,
  config: ["config"] as const,
  preview: (id: number, body: PreviewBody) => ["preview", id, body] as const,
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
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.inbox }),
  });
}

export function useSkip() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.skip(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.inbox }),
  });
}

export function useAccounts() {
  return useQuery({ queryKey: qk.accounts, queryFn: api.accounts });
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

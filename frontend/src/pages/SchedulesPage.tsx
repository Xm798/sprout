import { useSchedules, useDeleteSchedule } from "../api/hooks";
import { ScheduleForm } from "../components/ScheduleForm";

export function SchedulesPage() {
  const schedules = useSchedules();
  const del = useDeleteSchedule();

  return (
    <div className="space-y-4 p-4">
      <h1 className="text-xl font-semibold">Schedules</h1>
      <ScheduleForm />
      {schedules.isLoading ? (
        <div>Loading…</div>
      ) : (
        <ul className="space-y-1">
          {(schedules.data ?? []).map((s) => (
            <li
              key={s.id}
              className="flex items-center justify-between rounded border px-3 py-2"
            >
              <span>
                {s.name} · {String(s.amount)} {s.currency} · every{" "}
                {s.interval_count} {s.interval_unit}
              </span>
              <button
                className="text-sm text-red-600 hover:underline"
                onClick={() => del.mutate(s.id)}
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

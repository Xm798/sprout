import { useConfirm, useInbox, useSchedules } from "../api/hooks";
import { InboxRow } from "../components/InboxRow";

export function InboxPage() {
  const inbox = useInbox();
  const schedules = useSchedules();
  const confirm = useConfirm();

  const byId = new Map((schedules.data ?? []).map((s) => [s.id, s]));
  const items = inbox.data ?? [];

  function confirmAll() {
    items.forEach((o) => confirm.mutate({ id: o.id, body: {} }));
  }

  return (
    <div className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Inbox</h1>
        {items.length > 0 && (
          <button
            className="rounded border px-3 py-1 text-sm"
            onClick={confirmAll}
            disabled={confirm.isPending}
          >
            Confirm all
          </button>
        )}
      </div>
      {inbox.isLoading ? (
        <div>Loading…</div>
      ) : inbox.isError ? (
        <div className="text-red-600">Failed to load inbox</div>
      ) : items.length === 0 ? (
        <div className="text-gray-500">Nothing due. 🎉</div>
      ) : (
        items.map((occ) => (
          <InboxRow
            key={occ.id}
            occurrence={occ}
            schedule={byId.get(occ.schedule_id)}
          />
        ))
      )}
    </div>
  );
}

import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { useRegisterSW } from "virtual:pwa-register/react";

// A new service worker waits in the background until we tell it to take over.
// Surface a persistent toast so the user reloads on their own terms instead of
// losing in-progress work to an automatic refresh.
export function PwaUpdatePrompt() {
  const { t } = useTranslation();
  const {
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW();

  useEffect(() => {
    if (!needRefresh) return;
    const id = toast(t("pwaUpdate.title"), {
      duration: Infinity,
      action: {
        label: t("pwaUpdate.refresh"),
        // `updateServiceWorker(true)` activates the waiting SW and reloads.
        onClick: () => updateServiceWorker(true),
      },
      onDismiss: () => setNeedRefresh(false),
    });
    return () => {
      toast.dismiss(id);
    };
  }, [needRefresh, setNeedRefresh, updateServiceWorker, t]);

  return null;
}

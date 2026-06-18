import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { ThemeProvider } from "next-themes";

import App from "./App";
import { PwaUpdatePrompt } from "@/components/pwa-update-prompt";
import { Toaster } from "@/components/ui/sonner";
import "./index.css";
import "./i18n";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000 } },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      storageKey="sprout-theme"
      disableTransitionOnChange
    >
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
        <Toaster />
        <PwaUpdatePrompt />
      </QueryClientProvider>
    </ThemeProvider>
  </React.StrictMode>
);

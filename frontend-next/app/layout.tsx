import type { Metadata } from "next";
import { Shell } from "@/components/Shell";
import { WorkspaceProvider } from "@/components/WorkspaceProvider";
import "./globals.css";

export const metadata: Metadata = {
  title: "DocRAG",
  description: "Local multi-tenant document intelligence",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="h-full overflow-hidden">
        {/* Provider and shell live in the layout, so navigating between routes
            keeps the conversation, the loaded documents and the PDF viewer
            mounted instead of refetching and losing state on every click. */}
        <WorkspaceProvider>
          <Shell>{children}</Shell>
        </WorkspaceProvider>
      </body>
    </html>
  );
}

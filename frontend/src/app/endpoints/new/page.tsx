"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import type { EndpointInput } from "@/lib/types";
import { EndpointForm } from "@/components/EndpointForm";

export default function NewEndpointPage() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const create = useMutation({
    mutationFn: (payload: EndpointInput) => api.createEndpoint(payload),
    onSuccess: (endpoint) => {
      queryClient.invalidateQueries({ queryKey: ["endpoints"] });
      router.push(`/endpoints/${endpoint.id}`);
    },
  });

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div>
        <Link href="/endpoints" className="text-xs hover:underline" style={{ color: "var(--muted)" }}>
          ← Endpoints
        </Link>
        <h1 className="mt-1 text-lg font-semibold">New endpoint</h1>
      </div>
      <EndpointForm
        onSubmit={(payload) => create.mutate(payload)}
        submitting={create.isPending}
        error={create.error}
        submitLabel="Create endpoint"
      />
    </div>
  );
}

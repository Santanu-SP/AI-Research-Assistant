import { apiRequest } from "./api";

export interface UserApiKeyMetadata {
  id: string;
  provider: string;
  keyHint: string;
  isActive: boolean;
  usageRequests: number;
  usageTokens: number;
  lastUsedAt?: string | null;
  createdAt: string;
}

export interface WebGPUCapability {
  supported: boolean;
  adapterInfo?: string;
  reason?: string;
}

declare global {
  interface Window {
    puter?: {
      ai?: {
        chat: (
          prompt: string,
          options?: { model?: string; stream?: boolean }
        ) => Promise<{ message?: { content?: string }; toString?: () => string }>;
      };
    };
  }
}

/**
 * Check whether the current browser and GPU support WebGPU for WebLLM inference.
 */
export async function detectWebGPUCapability(): Promise<WebGPUCapability> {
  if (typeof navigator === "undefined" || !("gpu" in navigator)) {
    return {
      supported: false,
      reason: "WebGPU API is not available in this browser.",
    };
  }
  try {
    const gpu = (navigator as unknown as { gpu: { requestAdapter: () => Promise<unknown> } }).gpu;
    const adapter = await gpu.requestAdapter();
    if (!adapter) {
      return {
        supported: false,
        reason: "No compatible WebGPU hardware adapter was found.",
      };
    }
    return {
      supported: true,
      adapterInfo: "WebGPU hardware adapter available",
    };
  } catch (err) {
    return {
      supported: false,
      reason: err instanceof Error ? err.message : "WebGPU initialization failed",
    };
  }
}

/**
 * Run optional client-side generation through Puter.js when loaded in the browser.
 * Never used as the primary backend production dependency.
 */
export async function generateWithPuter(
  prompt: string,
  model = "gpt-4o-mini"
): Promise<string> {
  if (typeof window === "undefined" || !window.puter?.ai?.chat) {
    throw new Error("Puter.js is not loaded in this browser session.");
  }
  const response = await window.puter.ai.chat(prompt, { model });
  if (typeof response === "string") {
    return response;
  }
  if (response?.message?.content) {
    return response.message.content;
  }
  return response?.toString?.() ?? "";
}

export const byokService = {
  async listKeys(): Promise<{ items: UserApiKeyMetadata[] }> {
    return apiRequest<{ items: UserApiKeyMetadata[] }>("/auth/api-keys");
  },

  async saveKey(provider: string, apiKey: string): Promise<UserApiKeyMetadata> {
    return apiRequest<UserApiKeyMetadata>(`/auth/api-keys/${encodeURIComponent(provider)}`, {
      method: "PUT",
      body: JSON.stringify({ apiKey }),
    });
  },

  async revokeKey(provider: string): Promise<void> {
    await apiRequest<void>(`/auth/api-keys/${encodeURIComponent(provider)}`, {
      method: "DELETE",
    });
  },
};


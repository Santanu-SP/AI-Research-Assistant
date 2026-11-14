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

export interface ProviderStatusItem {
  id: string;
  label: string;
  configuredServer: boolean;
  configuredByok: boolean;
  configured: boolean;
  keyHint?: string | null;
  defaultModel: string;
  selectedModel?: string | null;
  suggestedModels?: string[];
  isLocal: boolean;
  available: boolean;
}

export interface LocalModelStatus {
  provider: string;
  available: boolean;
  connected: boolean;
  baseUrl: string;
  configuredModel: string;
  activeModel?: string | null;
  installedModels: string[];
}

export interface ModelUsageBreakdownItem {
  provider: string;
  modelName: string;
  requestsToday: number;
  tokensToday: number;
  totalRequests: number;
  totalTokens: number;
  estimatedCostUsd: number;
  lastUsedAt?: string | null;
}

export interface ModelUsageQuotaSummary {
  enrolledUsers: number;
  sharedRequestsUsedToday: number;
  userDailyRequestCap: number;
  userRequestsRemainingToday: number;
  systemPoolTotal: number;
  systemPoolUsedToday: number;
  systemPoolRemaining: number;
  byokRequestsToday: number;
  localRequestsToday: number;
  totalRequestsToday: number;
  totalTokensToday: number;
  totalRequestsAllTime: number;
  totalTokensAllTime: number;
  resetsAt: string;
  models: ModelUsageBreakdownItem[];
}

export interface ModelsStatusResponse {
  local: LocalModelStatus;
  providers: ProviderStatusItem[];
  routerOrder: string[];
  usage?: ModelUsageQuotaSummary | null;
}

export const byokService = {
  async listKeys(): Promise<{ items: UserApiKeyMetadata[] }> {
    return apiRequest<{ items: UserApiKeyMetadata[] }>("/auth/api-keys");
  },

  async saveKey(provider: string, apiKey: string, modelName?: string): Promise<UserApiKeyMetadata> {
    const cleanedModel = modelName?.trim();
    return apiRequest<UserApiKeyMetadata>(`/auth/api-keys/${encodeURIComponent(provider)}`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        apiKey,
        ...(cleanedModel ? { modelName: cleanedModel } : {}),
      }),
    });
  },

  async setProviderModel(
    provider: string,
    modelName: string | null
  ): Promise<{ provider: string; selectedModel: string | null }> {
    return apiRequest<{ provider: string; selectedModel: string | null }>(
      "/auth/api-keys/provider-model",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          provider,
          modelName: modelName?.trim() || null,
        }),
      }
    );
  },

  async revokeKey(provider: string): Promise<void> {
    await apiRequest<void>(`/auth/api-keys/${encodeURIComponent(provider)}`, {
      method: "DELETE",
    });
  },

  async getModelsStatus(): Promise<ModelsStatusResponse> {
    return apiRequest<ModelsStatusResponse>("/auth/api-keys/models-status");
  },

  async getUsage(): Promise<ModelUsageQuotaSummary> {
    return apiRequest<ModelUsageQuotaSummary>("/auth/api-keys/usage");
  },

  async setLocalFallback(connected: boolean): Promise<LocalModelStatus> {
    return apiRequest<LocalModelStatus>("/auth/api-keys/local-fallback", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ connected }),
    });
  },
};


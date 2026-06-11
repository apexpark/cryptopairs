type ServiceName = "account" | "data" | "execution" | "strategy";

const LOCAL_SERVICE_BASE_URLS: Record<ServiceName, string> = {
  account: "http://127.0.0.1:8081",
  data: "http://127.0.0.1:8080",
  execution: "http://127.0.0.1:8082",
  strategy: "http://127.0.0.1:8083",
};

const HOSTED_SERVICE_BASE_URLS: Record<ServiceName, string> = {
  account: "https://api.apexpark.io/account",
  data: "https://api.apexpark.io/data",
  execution: "https://api.apexpark.io/execution",
  strategy: "https://api.apexpark.io/strategy",
};

function currentHostname(): string {
  if (typeof window === "undefined") {
    return "";
  }
  return window.location.hostname;
}

function isLocalHostname(hostname: string): boolean {
  const normalized = hostname.trim().toLowerCase();
  return (
    normalized === "" ||
    normalized === "localhost" ||
    normalized === "127.0.0.1" ||
    normalized === "::1" ||
    normalized === "[::1]" ||
    normalized.endsWith(".localhost")
  );
}

function normalizeBaseUrl(value: string): string {
  return value.trim().replace(/\/+$/, "");
}

export function resolveServiceBaseUrl(
  configuredValue: string | undefined,
  service: ServiceName,
  hostname = currentHostname()
): string {
  const configured = configuredValue?.trim();
  if (configured) {
    return normalizeBaseUrl(configured);
  }
  return isLocalHostname(hostname)
    ? LOCAL_SERVICE_BASE_URLS[service]
    : HOSTED_SERVICE_BASE_URLS[service];
}

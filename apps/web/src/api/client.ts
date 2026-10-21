const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "";

type TokenReader = () => string | null;
type UnauthorizedHandler = (token: string | null) => void;

let readToken: TokenReader = () => null;
let handleUnauthorized: UnauthorizedHandler = () => {};

type Envelope = {
  data?: unknown;
  error?: { code?: string; message?: string } | null;
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(message: string, status: number, code = "") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export function configureApi(options: {
  getToken: TokenReader;
  onUnauthorized: UnauthorizedHandler;
}): void {
  readToken = options.getToken;
  handleUnauthorized = options.onUnauthorized;
}

export function apiErrorMessage(reason: unknown): string {
  if (reason instanceof ApiError) return reason.message;
  return "Request failed.";
}

export async function getJson<T>(
  path: string,
  allowedStatuses: number[] = [200],
): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, { cache: "no-store" });
  if (!allowedStatuses.includes(response.status)) {
    throw new ApiError(`Request failed: ${response.status}`, response.status);
  }
  return (await response.json()) as T;
}

export async function apiData<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = readToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (
    init.body !== undefined &&
    !(init.body instanceof FormData) &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${baseUrl}${path}`, { ...init, headers, cache: "no-store" });
  let body: Envelope | null = null;
  try {
    body = (await response.json()) as Envelope;
  } catch {
    body = null;
  }

  if (response.ok && body && body.error == null && body.data !== undefined && body.data !== null) {
    return body.data as T;
  }

  if (response.status === 401) {
    handleUnauthorized(token);
  }
  throw new ApiError(
    body?.error?.message ?? `Request failed: ${response.status}`,
    response.status,
    body?.error?.code ?? "HTTP_ERROR",
  );
}

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

function withBearer(init: RequestInit): { headers: Headers; token: string | null } {
  const headers = new Headers(init.headers);
  const token = readToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return { headers, token };
}

async function readEnvelope(response: Response): Promise<Envelope | null> {
  try {
    return (await response.json()) as Envelope;
  } catch {
    return null;
  }
}

function rejectResponse(response: Response, body: Envelope | null, token: string | null): never {
  if (response.status === 401) {
    handleUnauthorized(token);
  }
  throw new ApiError(
    body?.error?.message ?? `Request failed: ${response.status}`,
    response.status,
    body?.error?.code ?? "HTTP_ERROR",
  );
}

export async function apiData<T>(path: string, init: RequestInit = {}): Promise<T> {
  const { headers, token } = withBearer(init);
  if (
    init.body !== undefined &&
    !(init.body instanceof FormData) &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${baseUrl}${path}`, { ...init, headers, cache: "no-store" });
  const body = await readEnvelope(response);

  if (response.ok && body && body.error == null && body.data !== undefined && body.data !== null) {
    return body.data as T;
  }

  return rejectResponse(response, body, token);
}

export async function apiBytes(path: string, init: RequestInit = {}): Promise<Blob> {
  const { headers, token } = withBearer(init);
  const response = await fetch(`${baseUrl}${path}`, { ...init, headers, cache: "no-store" });
  if (response.ok) {
    return response.blob();
  }
  return rejectResponse(response, await readEnvelope(response), token);
}

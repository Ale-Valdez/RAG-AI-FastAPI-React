const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

export async function getJson<T>(
  path: string,
  allowedStatuses: number[] = [200],
): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`);
  if (!allowedStatuses.includes(response.status)) {
    throw new ApiError(`Request failed: ${response.status}`, response.status);
  }
  return (await response.json()) as T;
}

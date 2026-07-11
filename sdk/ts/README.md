# MelosViz TypeScript bridge client (stub)

```ts
// Illustrative — not a published package.
export type AnalyzeRequest = { wav_path: string };

export async function analyze(
  baseUrl: string,
  body: AnalyzeRequest,
  token?: string,
): Promise<unknown> {
  const headers: Record<string, string> = {
    "content-type": "application/json",
  };
  if (token) headers.authorization = `Bearer ${token}`;
  const res = await fetch(`${baseUrl}/analyze`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    // Bridge returns application/problem+json on errors.
    throw Object.assign(new Error(res.statusText), {
      status: res.status,
      problem: await res.json().catch(() => null),
    });
  }
  return res.json();
}
```

Wire this into `web/` or a future `@melosviz/bridge-client` only after an
explicit publish decision (currently private).

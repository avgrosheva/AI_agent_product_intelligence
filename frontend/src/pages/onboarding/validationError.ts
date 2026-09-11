import { ApiError } from '../../api/client'

/** The config PUT endpoint returns 422s whose `detail` is a JSON-encoded
 * array of {field, message} issues (backend.app.routers.domains.put_config);
 * other endpoints just return a plain string. This normalizes both into
 * human-readable lines so a PM/analyst sees the actual problem, not a
 * raw JSON blob (Stage 15 task 4/9). */
export function formatValidationErrors(err: unknown): string[] {
  if (err instanceof ApiError) {
    try {
      const parsed = JSON.parse(err.detail)
      if (Array.isArray(parsed)) {
        return parsed.map((issue) =>
          issue && typeof issue === 'object' && 'field' in issue && 'message' in issue
            ? `${(issue as { field: string }).field}: ${(issue as { message: string }).message}`
            : String(issue),
        )
      }
    } catch {
      // detail wasn't JSON -- fall through and show it as plain text
    }
    return [err.detail]
  }
  return [err instanceof Error ? err.message : 'Something went wrong.']
}

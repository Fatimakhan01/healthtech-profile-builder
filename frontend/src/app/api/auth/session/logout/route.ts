import { proxyAuthRequest } from "../../../../../lib/auth-proxy";

export function POST(request: Request) {
  return proxyAuthRequest(request, "session-logout");
}

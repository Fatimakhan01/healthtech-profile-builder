import { proxyAuthRequest } from "../../../../lib/auth-proxy";

export function GET(request: Request) {
  return proxyAuthRequest(request, "admin-session");
}

export function POST(request: Request) {
  return proxyAuthRequest(request, "admin-session");
}

import { proxyAuthRequest } from "../../../../lib/auth-proxy";

export function GET(request: Request) {
  return proxyAuthRequest(request, "profile");
}

export function PATCH(request: Request) {
  return proxyAuthRequest(request, "profile");
}

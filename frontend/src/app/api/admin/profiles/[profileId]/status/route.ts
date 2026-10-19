import { proxyAuthRequest } from "../../../../../../lib/auth-proxy";

type RouteContext = {
  params: Promise<{ profileId: string }>;
};

export async function PATCH(request: Request, context: RouteContext) {
  const { profileId } = await context.params;
  return proxyAuthRequest(request, "admin-profile-status", profileId);
}

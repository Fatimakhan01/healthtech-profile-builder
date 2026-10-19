type AuthEndpoint =
  | "signup"
  | "login"
  | "me"
  | "profile"
  | "csrf"
  | "session-refresh"
  | "session-logout"
  | "admin-csrf"
  | "admin-login"
  | "admin-session"
  | "admin-profiles"
  | "admin-profile-status";

const SESSION_COOKIE_NAMES = new Set(["sessionid", "csrftoken"]);

function getForwardedCookies(cookieHeader: string | null) {
  if (!cookieHeader) {
    return "";
  }

  return cookieHeader
    .split(";")
    .map((cookie) => cookie.trim())
    .filter((cookie) => SESSION_COOKIE_NAMES.has(cookie.split("=", 1)[0]))
    .join("; ");
}

export async function proxyAuthRequest(
  request: Request,
  endpoint: AuthEndpoint,
  profileId?: string,
): Promise<Response> {
  const backendUrl = (
    process.env.BACKEND_API_URL ?? "http://127.0.0.1:8000/api"
  ).replace(/\/+$/, "");
  const headers = new Headers();
  const hasBody = request.method !== "GET";

  if (
    endpoint === "me" ||
    endpoint === "profile" ||
    endpoint === "session-refresh" ||
    endpoint === "session-logout"
  ) {
    const authorization = request.headers.get("authorization");
    if (authorization) {
      headers.set("authorization", authorization);
    }
  }
  const sessionEndpoints: AuthEndpoint[] = [
    "login",
    "csrf",
    "session-refresh",
    "session-logout",
    "admin-csrf",
    "admin-login",
    "admin-session",
    "admin-profiles",
    "admin-profile-status",
  ];
  const cookies = sessionEndpoints.includes(endpoint)
    ? getForwardedCookies(request.headers.get("cookie"))
    : "";
  if (cookies) {
    headers.set("cookie", cookies);
  }
  const csrfToken = request.headers.get("x-csrftoken");
  if (csrfToken) {
    headers.set("x-csrftoken", csrfToken);
  }
  if (hasBody) {
    headers.set("content-type", "application/json");
  }

  if (endpoint === "admin-profile-status" && !/^\d+$/.test(profileId ?? "")) {
    return Response.json(
      { detail: "A valid profile identifier is required." },
      { status: 400, headers: { "cache-control": "no-store" } },
    );
  }

  try {
    const upstreamPaths: Record<AuthEndpoint, string> = {
      signup: "/auth/signup/",
      login: "/auth/session/login/",
      me: "/auth/me/",
      profile: "/profiles/me/",
      csrf: "/auth/csrf/",
      "session-refresh": "/auth/session/refresh/",
      "session-logout": "/auth/session/logout/",
      "admin-csrf": "/admin/csrf/",
      "admin-login": "/admin/login/",
      "admin-session": "/admin/session/",
      "admin-profiles": "/admin/profiles/",
      "admin-profile-status": "/admin/profiles/",
    };
    const upstreamPath =
      endpoint === "admin-profile-status"
        ? `${upstreamPaths[endpoint]}${profileId}/status/`
        : upstreamPaths[endpoint];
    if (typeof upstreamPath !== "string" || !upstreamPath.startsWith("/")) {
      return Response.json(
        { detail: "No valid upstream route is configured for this request." },
        { status: 500, headers: { "cache-control": "no-store" } },
      );
    }
    const upstreamUrl = new URL(`${backendUrl}${upstreamPath}`);
    if (endpoint === "admin-profiles") {
      for (const parameter of ["search", "active", "page", "page_size"]) {
        const value = new URL(request.url).searchParams.get(parameter);
        if (value !== null) {
          upstreamUrl.searchParams.set(parameter, value);
        }
      }
    }
    const upstream = await fetch(upstreamUrl, {
      method: request.method,
      headers,
      body: hasBody ? await request.text() : undefined,
      cache: "no-store",
    });

    const response = new Response(upstream.body, {
      status: upstream.status,
      headers: {
        "content-type":
          upstream.headers.get("content-type") ?? "application/json",
        "cache-control": "no-store",
      },
    });
    for (const cookie of upstream.headers.getSetCookie()) {
      response.headers.append("set-cookie", cookie);
    }
    return response;
  } catch {
    return Response.json(
      { detail: "The authentication service is unavailable." },
      { status: 502, headers: { "cache-control": "no-store" } },
    );
  }
}

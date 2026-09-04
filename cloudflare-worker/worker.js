// Reverse proxy: serves the Streamlit app (daily-1pct-screener.streamlit.app)
// under the custom domain (dailyonepercent.info), so the browser's address
// bar never shows the streamlit.app URL. Deployed via the Cloudflare
// dashboard (Workers & Pages) and bound to the zone as a Custom Domain.
//
// Access control lives at Cloudflare Access (Zero Trust), in front of this
// Worker's route, not in Streamlit itself — Streamlit's own viewer
// restriction relies on cookies scoped to streamlit.app, which can't survive
// being proxied under a different domain.

const TARGET_HOST = "daily-1pct-screener.streamlit.app";
const REDIRECT_STATUSES = new Set([301, 302, 303, 307, 308]);

export default {
  async fetch(request) {
    const originalUrl = new URL(request.url);

    const targetUrl = new URL(request.url);
    targetUrl.protocol = "https:";
    targetUrl.hostname = TARGET_HOST;
    targetUrl.port = "";

    const headers = new Headers(request.headers);
    headers.set("Host", TARGET_HOST);
    headers.set("Origin", `https://${TARGET_HOST}`);

    const init = {
      method: request.method,
      headers,
      body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
      redirect: "manual",
    };

    const response = await fetch(targetUrl.toString(), init);

    if (REDIRECT_STATUSES.has(response.status)) {
      const location = response.headers.get("Location");
      if (location) {
        const loc = new URL(location, targetUrl);
        if (loc.hostname === TARGET_HOST) {
          loc.hostname = originalUrl.hostname;
          loc.protocol = originalUrl.protocol;
        }
        const newHeaders = new Headers(response.headers);
        newHeaders.set("Location", loc.toString());
        return new Response(response.body, {
          status: response.status,
          statusText: response.statusText,
          headers: newHeaders,
        });
      }
    }

    return response;
  },
};

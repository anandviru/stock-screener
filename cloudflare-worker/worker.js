// Redirects dailyonepercent.info to the Streamlit app.
//
// Originally this Worker reverse-proxied the app so the browser's address
// bar never left the custom domain. That broke: Streamlit Community Cloud
// now bootstraps anonymous public-app sessions through a redirect dance
// across share.streamlit.io and *.streamlit.app -- a real browser follows
// it transparently, but it requires physically navigating to those domains,
// which a same-origin reverse proxy can't intercept or hide. A simple
// redirect is the reliable option instead: the address bar changes after
// landing, but it always works.

const TARGET = "https://daily-1pct-screener.streamlit.app/";

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const dest = new URL(TARGET);
    dest.search = url.search;
    return Response.redirect(dest.toString(), 302);
  },
};

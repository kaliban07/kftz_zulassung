// Repo-Name: muss EXAKT dem GitHub-Repo entsprechen (ZIP heißt "kftz_zulassung-main" -> Repo "kftz_zulassung")
const REPO = "kaliban07/kftz_zulassung";

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === "/test") {
      return await triggerGitHub(env);
    }
    return new Response("KFZ Trigger Worker läuft. /test löst GitHub manuell aus.", {
      headers: { "content-type": "text/plain;charset=UTF-8" },
    });
  },

  async scheduled(event, env, ctx) {
    ctx.waitUntil(triggerGitHub(env));
  },
};

async function triggerGitHub(env) {
  if (!env.GITHUB_TOKEN) {
    return new Response("FEHLER: Secret GITHUB_TOKEN fehlt im Worker.", { status: 500 });
  }
  const res = await fetch(`https://api.github.com/repos/${REPO}/dispatches`, {
    method: "POST",
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      "User-Agent": "Cloudflare-Worker",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    body: JSON.stringify({ event_type: "trigger-check" }),
  });
  const body = await res.text(); // GitHub-Fehlermeldung mit ausgeben
  const ok = res.status === 204;
  console.log(`GitHub dispatch ${REPO}: ${res.status} ${body}`);
  return new Response(
    (ok ? "OK – Workflow ausgelöst (204)" : `FEHLER ${res.status}`) + `\nRepo: ${REPO}\n${body}`,
    { status: ok ? 200 : 502, headers: { "content-type": "text/plain;charset=UTF-8" } }
  );
}

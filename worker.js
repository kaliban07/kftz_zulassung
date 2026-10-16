export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    
    // Wenn du /test aufrufst, wird GitHub direkt ausgelöst
    if (url.pathname === "/test") {
      return await triggerGitHub(env);
    }
    
    // Ansonsten gibt es eine nette Statusseite statt 404
    return new Response("KFZ Trigger Worker läuft! Nutze /test zum manuellen Auslösen.", {
      headers: { "content-type": "text/plain;charset=UTF-8" }
    });
  },

  async scheduled(event, env, ctx) {
    await triggerGitHub(env);
  }
};

async function triggerGitHub(env) {
  const apiurl = "https://api.github.com/repos/kaliban07/kfz_zulassung/dispatches";
  
  const response = await fetch(apiurl, {
    method: "POST",
    headers: {
      "Accept": "application/vnd.github+json",
      "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
      "User-Agent": "Cloudflare-Worker",
      "X-GitHub-Api-Version": "2022-11-28"
    },
    body: JSON.stringify({ event_type: "trigger-check" })
  });

  return new Response("GitHub Trigger Status: " + response.status);
}

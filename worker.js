export default {
  async fetch(request, env, ctx) {
    // Ermöglicht den manuellen Test, indem du deine Worker-URL im Browser aufrufst
    return await triggerGitHub(env);
  },

  async scheduled(event, env, ctx) {
    await triggerGitHub(env);
  }
};

async function triggerGitHub(env) {
  const url = "https://api.github.com/repos/kaliban07/kfz_zulassung/dispatches";
  
  const response = await fetch(url, {
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

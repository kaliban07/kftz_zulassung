export default {
  async scheduled(event, env, ctx) {
    const url = "https://api.github.com/repos/DEIN_GITHUB_USERNAME/kfz_zulassung/dispatches";
    
    await fetch(url, {
      method: "POST",
      headers: {
        "Accept": "application/vnd.github+json",
        "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
        "User-Agent": "Cloudflare-Worker",
        "X-GitHub-Api-Version": "2022-11-28"
      },
      body: JSON.stringify({ event_type: "trigger-check" })
    });
  }
};

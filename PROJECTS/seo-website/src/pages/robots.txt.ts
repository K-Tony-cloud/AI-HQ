export async function GET({ site }: { site: URL }) {
  const siteUrl = site?.toString().replace(/\/$/, '') || 'http://localhost:4321';
  return new Response(
    `User-agent: *\nAllow: /\n\nSitemap: ${siteUrl}/sitemap-index.xml\n`,
    { headers: { 'Content-Type': 'text/plain; charset=utf-8' } }
  );
}

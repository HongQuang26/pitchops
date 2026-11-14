import {store} from '../web/server/store.mjs';
import {routeData,encodeResponse} from '../web/server/api.mjs';

export default async function handler(request,response) {
  response.setHeader('Content-Type','application/json; charset=utf-8');
  response.setHeader('X-Content-Type-Options','nosniff');
  if (!['GET','HEAD'].includes(request.method)) {
    response.setHeader('Allow','GET, HEAD');
    return response.status(405).json({error:'API chỉ đọc.'});
  }
  try {
    const loaded=await store.load();
    const url=new URL(request.url,'https://pitchops.invalid');
    const result=encodeResponse(routeData(url,loaded));
    const statusRoute=/\/(health|status)(\?|$)/.test(request.url) || ['health','status'].includes(url.searchParams.get('endpoint'));
    response.setHeader('Cache-Control',result.status===200?'public, max-age=30':'no-store');
    response.setHeader('Vercel-CDN-Cache-Control',result.status===200?`public, s-maxage=${statusRoute?30:300}, stale-while-revalidate=60`:'no-store');
    response.setHeader('X-PitchOps-Run',loaded.status.run_id);
    return response.status(result.status).send(request.method==='HEAD'?'':result.body);
  } catch (error) {
    console.error('PitchOps snapshot reader failed',{kind:error.name});
    response.setHeader('Cache-Control','no-store');
    return response.status(503).json({error:'Dữ liệu đang tạm thời chưa sẵn sàng. Vui lòng thử lại sau.'});
  }
}

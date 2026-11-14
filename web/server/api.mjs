const MAX_RESPONSE = 4_000_000;
export function routeData(url, loaded) {
  const {snapshot:data,status,registry} = loaded;
  const endpoint = url.searchParams.get('endpoint') || url.pathname.replace(/^\/api\/?/,'') || 'status';
  const league = url.searchParams.get('league');
  const result = body => ({status:200,body});
  const error = (status,message) => ({status,body:{error:message}});
  if (endpoint === 'status' || endpoint === 'health') return result({backend:status,pipeline:{status:registry.status || 'bootstrap',last_attempt_at:registry.last_attempt_at || null,last_success_at:registry.last_success_at || null,workflow_run_id:registry.workflow_run_id || null},schedule:{timezone:'Asia/Ho_Chi_Minh',primary:'14:23 thứ Sáu',recovery:'14:53 thứ Bảy',precision:'GitHub scheduling is best effort; delays are possible'},coverage:{leagues:Object.keys(data.leagues).length,research_as_of:data.research?.as_of || null}});
  if (endpoint === 'bootstrap') {
    const {research,leagues,...base} = data;
    return result({...base,quality:{...base.quality,snapshot_age_days:status.data_age_days},leagues:Object.fromEntries(Object.entries(leagues).map(([code,item]) => [code,{name:item.name,season:item.season}])),web:{hosted:true,...status,research_available:!!research}});
  }
  if (endpoint === 'league') {
    if (!league || !Object.hasOwn(data.leagues,league)) return error(404,'Giải đấu không được hỗ trợ.');
    return result({run_id:data.meta.run_id,league:data.leagues[league]});
  }
  if (endpoint === 'predict') {
    const home = url.searchParams.get('home'), away = url.searchParams.get('away');
    if (!league || !home || !away || home===away || home.length>80 || away.length>80) return error(400,'Chọn giải và hai đội khác nhau.');
    const selected = Object.hasOwn(data.leagues,league) ? data.leagues[league] : null;
    if (!selected || !selected.teams.includes(home) || !selected.teams.includes(away)) return error(404,'Không có đội trong bộ dữ liệu này.');
    const forecast = selected.forecasts[home+'|'+away];
    if (!forecast) return error(404,'Chưa có dự báo cho cặp đấu.');
    return result({run_id:data.meta.run_id,model_run_id:selected.meta?.run_id || data.meta.run_id,training_through:selected.meta?.training_through || data.meta.training_through,league,home,away,forecast});
  }
  if (endpoint === 'fixtures') {
    if (!league || !Object.hasOwn(data.leagues,league)) return error(404,'Chọn một giải đấu được hỗ trợ.');
    const selected=data.leagues[league], team=url.searchParams.get('team'), state=url.searchParams.get('status');
    if (team && !selected.teams.includes(team)) return error(404,'Không có đội trong giải này.');
    if (state && !['completed','upcoming','all'].includes(state)) return error(400,'Trạng thái lịch không hợp lệ.');
    const fixtures=(selected.fixtures || []).filter(f=>(!team || f.home===team || f.away===team) && (!state || state==='all' || (state==='completed' ? f.status==='completed' : f.status!=='completed')));
    return result({run_id:data.meta.run_id,league,available:Array.isArray(selected.fixtures),total:fixtures.length,fixtures});
  }
  if (endpoint === 'research') {
    if (!data.research) return result(null);
    const {forecasts,spatial,team_players,...overview} = data.research;
    const part = url.searchParams.get('part') || 'overview';
    if (part === 'overview') return result(overview);
    if (part === 'forecasts') return result({forecasts});
    if (part === 'spatial') return result({spatial});
    if (part === 'players') return result({team_players});
    return error(400,'Phần nghiên cứu không hợp lệ.');
  }
  if (endpoint === 'players') {
    if (league && !Object.hasOwn(data.leagues,league)) return error(404,'Giải đấu không được hỗ trợ.');
    const query=(url.searchParams.get('q') || '').slice(0,100).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
    const players=(data.media?.players || []).filter(player => (!league || player.league===league) && player.name.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().includes(query));
    return result({run_id:data.meta.run_id,total:players.length,players});
  }
  return error(404,'API không tồn tại.');
}

export function encodeResponse(result) {
  const body=JSON.stringify(result.body);
  if (Buffer.byteLength(body)>MAX_RESPONSE) return {status:413,body:JSON.stringify({error:'Dữ liệu vượt kích thước phản hồi; dùng API theo phần.'})};
  return {status:result.status,body};
}

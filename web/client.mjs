import {startDashboard} from '__APP_PATH__';

async function api(path) {
  const response=await fetch('/api/'+path,{signal:AbortSignal.timeout(20_000)});
  if (!response.ok) throw new Error('Không nhận được dữ liệu từ backend.');
  return response.json();
}
async function boot() {
  const base=await api('bootstrap');
  const codes=Object.keys(base.leagues);
  const leagueResponses=await Promise.all(codes.map(code=>api('league?league='+encodeURIComponent(code))));
  if (leagueResponses.some(item=>item.run_id!==base.meta.run_id)) throw new Error('Backend đang cập nhật model. Vui lòng tải lại sau ít giây.');
  base.leagues=Object.fromEntries(codes.map((code,index)=>[code,leagueResponses[index].league]));
  if (base.web.research_available) {
    const parts=await Promise.all(['overview','forecasts','spatial','players'].map(part=>api('research?part='+part)));
    base.research=Object.assign({},...parts);
  }
  startDashboard(base);
  document.body.classList.remove('web-loading');
  document.getElementById('web-boot').remove();
  const statusCard=document.createElement('div');statusCard.className='note';statusCard.setAttribute('role','status');
  document.getElementById('ops-summary').after(statusCard);
  async function statusCheck() {
    try {
      const live=await api('status');
      statusCard.textContent=`Backend: ${live.backend.degraded?'đang dùng bản dự báo đã lưu':'sẵn sàng'} · Nguồn: ${live.backend.source} · Dữ liệu cách hiện tại ${live.backend.data_age_days} ngày · Pipeline: ${live.pipeline.status} · Lịch ${live.schedule.primary} (giờ Việt Nam).`;
      if (live.backend.dataset_id!==base.web.dataset_id && !document.getElementById('new-model')) {
        const banner=document.createElement('div');banner.id='new-model';banner.className='coverage-banner';
        const text=document.createElement('span');text.textContent='Đã có bản dự báo mới qua kiểm định.';
        const button=document.createElement('button');button.className='outline';button.textContent='Tải bản mới';button.onclick=()=>location.reload();
        banner.append(text,button);document.querySelector('.topbar').after(banner);
      }
    } catch {statusCard.textContent='Chưa kiểm tra được trạng thái pipeline. Bản dự báo đang mở vẫn sử dụng được.';}
  }
  await statusCheck();
  setInterval(()=>{if(document.visibilityState==='visible')void statusCheck();},300_000);
}
boot().catch(error=>{
  document.getElementById('boot-message').textContent=error.message;
  document.getElementById('boot-retry').hidden=false;
});
document.getElementById('boot-retry').onclick=()=>location.reload();

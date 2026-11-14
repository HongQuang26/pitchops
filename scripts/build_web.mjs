import {readFile,writeFile,mkdir,rm} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {decodeSnapshot} from '../web/server/store.mjs';
import {routeData,encodeResponse} from '../web/server/api.mjs';
const read=path=>readFile(new URL('../'+path,import.meta.url),'utf8');
const root=new URL('../public/',import.meta.url);
const receipt=JSON.parse(await read('web/bootstrap.manifest.json'));
const snapshot=decodeSnapshot(await readFile(new URL('../web/bootstrap.json.gz',import.meta.url)),receipt);
const loaded={snapshot,status:{data_age_days:0},registry:{}};
for(const path of ['bootstrap',...Object.keys(snapshot.leagues).map(code=>'league?league='+code),...['overview','forecasts','spatial','players'].map(part=>'research?part='+part)]){
  if(encodeResponse(routeData(new URL('https://build.test/api/'+path),loaded)).status!==200)throw new Error('API response exceeds supported size: '+path);
}
await rm(root,{recursive:true,force:true});await mkdir(new URL('assets/',root),{recursive:true});
const hash=value=>createHash('sha256').update(value).digest('hex').slice(0,16);
const css=await read('src/pitchops/dashboard.css');
const app='export function startDashboard(DATA){\n'+await read('src/pitchops/dashboard.js')+'\n'+await read('src/pitchops/analytics.js')+'\n}\n';
const appPath='/assets/app-'+hash(app)+'.mjs',cssPath='/assets/style-'+hash(css)+'.css';
const client=(await read('web/client.mjs')).replace('__APP_PATH__',appPath);
const clientPath='/assets/client-'+hash(client)+'.mjs';
let html=await read('src/pitchops/dashboard.html');
html=html.replace('<style>__PITCHOPS_STYLES__</style>','<link rel="stylesheet" href="'+cssPath+'">');
html=html.replace('<body>','<body class="web-loading"><div id="web-boot" role="status" style="max-width:520px;margin:12vh auto;padding:30px;font-family:Arial,sans-serif"><h1>PitchOps</h1><p id="boot-message">Đang nhận bản dự báo đã kiểm định từ backend…</p><button id="boot-retry" hidden>Tải lại</button><noscript>Bật JavaScript để dùng dashboard dự đoán.</noscript></div>');
html=html.replace(/<script>[\s\S]*?<\/script>/g,'').replace('</body>','<script type="module" src="'+clientPath+'"></script></body>');
html=html.replace('</head>','<meta name="description" content="PitchOps — dự đoán bóng đá, mô phỏng mùa giải, Event Lab và MLOps tự động hằng tuần."><link rel="icon" type="image/svg+xml" href="/icon.svg"><style>.web-loading .shell{display:none}</style></head>');
await Promise.all([
  writeFile(new URL('index.html',root),html),writeFile(new URL(cssPath.slice(1),root),css),
  writeFile(new URL(appPath.slice(1),root),app),writeFile(new URL(clientPath.slice(1),root),client),
  writeFile(new URL('icon.svg',root),'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="16" fill="#153f30"/><path d="M20 48V16h14c17 0 17 23 0 23h-6v9Zm8-17h6c6 0 6-7 0-7h-6Z" fill="#d6fc51"/></svg>'),
  writeFile(new URL('robots.txt',root),'User-agent: *\nAllow: /\nDisallow: /api/\n')
]);
console.log('Built PitchOps static frontend and shared dashboard assets.');

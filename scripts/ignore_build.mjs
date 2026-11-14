import {execFileSync} from 'node:child_process';
try {
  const files=execFileSync('git',['diff','--name-only','HEAD^','HEAD'],{encoding:'utf8'}).trim().split('\n').filter(Boolean);
  // Registry writes are data updates consumed by the API, not source deployments.
  process.exit(files.length && files.every(file=>file.startsWith('automation/'))?0:1);
} catch {process.exit(1);}

import http from 'k6/http'; import { check, sleep } from 'k6';
export const options={vus:50,duration:'5m',thresholds:{http_req_duration:['p(95)<750','p(99)<1500'],http_req_failed:['rate<0.01']}};
export default function(){const r=http.get(`${__ENV.BASE_URL||'http://127.0.0.1:8000'}/ready`);check(r,{'ready 200':x=>x.status===200});sleep(0.2);}

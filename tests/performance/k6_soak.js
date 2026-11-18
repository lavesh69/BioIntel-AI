import http from 'k6/http';
export const options={vus:100,duration:'30m',thresholds:{http_req_failed:['rate<0.02'],http_req_duration:['p(95)<1000']}};
export default function(){http.get(`${__ENV.BASE_URL||'http://127.0.0.1:8000'}/ready`);}

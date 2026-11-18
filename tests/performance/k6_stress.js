import http from 'k6/http';
export const options={stages:[{duration:'2m',target:100},{duration:'5m',target:500},{duration:'2m',target:0}],thresholds:{http_req_failed:['rate<0.05'],http_req_duration:['p(95)<2000']}};
export default function(){http.get(`${__ENV.BASE_URL||'http://127.0.0.1:8000'}/ready`);}

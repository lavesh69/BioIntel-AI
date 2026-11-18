import http from 'k6/http';
export const options={stages:[{duration:'30s',target:50},{duration:'15s',target:1000},{duration:'1m',target:1000},{duration:'1m',target:0}]};
export default function(){http.get(`${__ENV.BASE_URL||'http://127.0.0.1:8000'}/live`);}

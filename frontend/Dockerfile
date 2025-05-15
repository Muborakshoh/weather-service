#FROM node:alpine

#WORKDIR /app

#COPY index.html .
#COPY chart.min.js .

#EXPOSE 80

#CMD ["node", "-e", "const http = require('http'); const fs = require('fs'); const url = require('url'); http.createServer((req, res) => { const path = url.parse(req.url).pathname; if (path === '/chart.min.js') { fs.readFile('chart.min.js', (err, data) => { if (err) { res.writeHead(500); res.end('Error loading chart.min.js'); } else { res.writeHead(200, {'Content-Type': 'application/javascript'}); res.end(data); } }); } else { fs.readFile('index.html', (err, data) => { if (err) { res.writeHead(500); res.end('Error loading index.html'); } else { res.writeHead(200, {'Content-Type': 'text/html'}); res.end(data); } }); } }).listen(80); console.log('Server running on port 80');"]

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html /usr/share/nginx/html/
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

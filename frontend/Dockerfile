FROM node:22-alpine AS build
WORKDIR /app
ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8
COPY angular20/package*.json ./
RUN npm ci
COPY angular20/ .
RUN npm run build -- --configuration=production

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/angular20/browser /usr/share/nginx/html
# nginx sans root : port 8080 (< 1024 interdit sans privilège), pid et caches accessibles au compte nginx.
RUN sed -i -e '/^user /d' -e 's,^pid .*,pid /tmp/nginx.pid;,' /etc/nginx/nginx.conf \
    && chown -R nginx:nginx /var/cache/nginx
USER nginx
EXPOSE 8080

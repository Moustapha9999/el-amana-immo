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
EXPOSE 80

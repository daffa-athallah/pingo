FROM node:22-alpine AS build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
ARG VITE_API_BASE_URL=/api
ARG VITE_CHECKIN_DEMO=false
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_CHECKIN_DEMO=${VITE_CHECKIN_DEMO}
RUN npm run build

FROM nginx:alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/frontend/dist /usr/share/nginx/html
EXPOSE 80

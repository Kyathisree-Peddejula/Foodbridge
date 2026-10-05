# Flutter web build -> static files served by nginx
FROM ghcr.io/cirruslabs/flutter:stable AS build
ARG API_BASE_URL=http://localhost:8000/api
ARG ML_DOCS_URL=http://localhost:8001/docs
# Render/Railway pass service env vars as build args; PUBLIC_* take precedence when set
ARG PUBLIC_API_URL=
ARG PUBLIC_ML_DOCS_URL=
WORKDIR /src
COPY . .
RUN flutter create . --project-name foodbridge --platforms=web >/dev/null \
 && flutter pub get \
 && DEFS="--dart-define=API_BASE_URL=${PUBLIC_API_URL:-$API_BASE_URL} --dart-define=ML_DOCS_URL=${PUBLIC_ML_DOCS_URL:-$ML_DOCS_URL}" \
 && (flutter build web --release --no-web-resources-cdn $DEFS || flutter build web --release $DEFS)
# --no-web-resources-cdn bundles CanvasKit locally so the installed PWA also works offline

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/build/web /usr/share/nginx/html
EXPOSE 80

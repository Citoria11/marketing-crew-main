# ---- dev stage (used by docker-compose.override.yml) ----
FROM node:20-alpine AS dev

WORKDIR /app
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY . .

EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# ---- production build stage ----
FROM node:20-alpine AS build

WORKDIR /app
COPY package.json package-lock.json* ./
# Use ci for reproducible installs when lockfile is present, fallback to install
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

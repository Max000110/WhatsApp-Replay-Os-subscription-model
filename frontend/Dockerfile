FROM node:20-slim AS builder
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

FROM node:20-slim AS runner
WORKDIR /app
COPY package*.json ./
RUN npm install --only=production
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/next.config.js ./next.config.js
EXPOSE 3000
CMD ["npm", "start"]

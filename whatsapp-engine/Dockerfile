FROM node:20-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y git openssh-client ca-certificates --no-install-recommends && rm -rf /var/lib/apt/lists/*
COPY gitconfig /etc/gitconfig
COPY gitconfig /root/.gitconfig
RUN mkdir -p /home/node
COPY gitconfig /home/node/.gitconfig
RUN chown -R node:node /home/node
COPY package*.json tsconfig.json ./
RUN npm install
COPY src ./src
RUN npm run build

FROM node:20-slim AS runner
WORKDIR /app
RUN apt-get update && apt-get install -y git openssh-client ca-certificates --no-install-recommends && rm -rf /var/lib/apt/lists/*
COPY gitconfig /etc/gitconfig
COPY gitconfig /root/.gitconfig
RUN mkdir -p /home/node
COPY gitconfig /home/node/.gitconfig
RUN chown -R node:node /home/node
COPY package*.json ./
RUN npm install --only=production
COPY --from=builder /app/dist ./dist
EXPOSE 3000
CMD ["node", "dist/index.js"]

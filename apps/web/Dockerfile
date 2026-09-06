FROM node:22-slim
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
# Run as the non-root `node` user the base image already ships (uid/gid
# 1000). `next dev` writes a .next/ build cache at runtime, so it needs to
# own /app, not just read it.
RUN chown -R node:node /app
USER node
CMD ["npm", "run", "dev"]

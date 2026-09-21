FROM node:22-bookworm-slim

RUN mkdir /app && chown node:node /app
WORKDIR /app
USER node

COPY --chown=node:node package.json ./
RUN npm install
COPY --chown=node:node . .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

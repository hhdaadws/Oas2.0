FROM node:20-alpine AS frontend-builder
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM golang:1.25.7-alpine AS backend-builder
WORKDIR /src
COPY go.mod go.sum* ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o /out/oas-cloud ./cmd/server

FROM gcr.io/distroless/static-debian12
WORKDIR /app
COPY --from=backend-builder /out/oas-cloud /app/oas-cloud
COPY --from=frontend-builder /frontend/dist /app/web
EXPOSE 7000
ENTRYPOINT ["/app/oas-cloud"]


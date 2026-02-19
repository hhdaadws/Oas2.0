package config

import (
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

type Config struct {
	Addr               string
	ServeFrontend      bool
	FrontendDistDir    string
	DatabaseURL        string
	RedisAddr          string
	RedisPassword      string
	RedisDB            int
	RedisKeyPrefix     string
	JWTSecret          string
	JWTTTL             time.Duration
	AgentJWTTTL        time.Duration
	UserTokenTTL       time.Duration
	DefaultLeaseSecond int
	MaxPollLimit       int
	SchedulerEnabled   bool
	SchedulerInterval  time.Duration
	SchedulerScanLimit int
	SchedulerSlotTTL   time.Duration
}

func Load() Config {
	return Config{
		Addr:               getEnv("ADDR", ":7000"),
		ServeFrontend:      getBoolEnv("SERVE_FRONTEND", true),
		FrontendDistDir:    getEnv("FRONTEND_DIST_DIR", "/app/web"),
		DatabaseURL:        getEnvOrFile("DATABASE_URL", "DATABASE_URL_FILE", "postgres://postgres:postgres@127.0.0.1:5432/oas_cloud?sslmode=disable"),
		RedisAddr:          getEnv("REDIS_ADDR", "127.0.0.1:6379"),
		RedisPassword:      getEnvOrFile("REDIS_PASSWORD", "REDIS_PASSWORD_FILE", ""),
		RedisDB:            getIntEnv("REDIS_DB", 0),
		RedisKeyPrefix:     getEnv("REDIS_KEY_PREFIX", "oas:cloud"),
		JWTSecret:          getEnvOrFile("JWT_SECRET", "JWT_SECRET_FILE", "change-me-in-production"),
		JWTTTL:             getDurationEnv("JWT_TTL", 24*time.Hour),
		AgentJWTTTL:        getDurationEnv("AGENT_JWT_TTL", 12*time.Hour),
		UserTokenTTL:       getDurationEnv("USER_TOKEN_TTL", 180*24*time.Hour),
		DefaultLeaseSecond: getIntEnv("DEFAULT_LEASE_SECONDS", 90),
		MaxPollLimit:       getIntEnv("MAX_POLL_LIMIT", 20),
		SchedulerEnabled:   getBoolEnv("SCHEDULER_ENABLED", true),
		SchedulerInterval:  getDurationEnv("SCHEDULER_INTERVAL", 10*time.Second),
		SchedulerScanLimit: getIntEnv("SCHEDULER_SCAN_LIMIT", 500),
		SchedulerSlotTTL:   getDurationEnv("SCHEDULER_SLOT_TTL", 90*time.Second),
	}
}

func getEnvOrFile(key string, keyFile string, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	if path := os.Getenv(keyFile); path != "" {
		content, err := os.ReadFile(filepath.Clean(path))
		if err == nil {
			trimmed := strings.TrimSpace(string(content))
			if trimmed != "" {
				return trimmed
			}
		}
	}
	return fallback
}

func getEnv(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func getIntEnv(key string, fallback int) int {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}
	parsed, err := strconv.Atoi(value)
	if err != nil {
		return fallback
	}
	return parsed
}

func getDurationEnv(key string, fallback time.Duration) time.Duration {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}
	parsed, err := time.ParseDuration(value)
	if err != nil {
		return fallback
	}
	return parsed
}

func getBoolEnv(key string, fallback bool) bool {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}
	switch strings.ToLower(value) {
	case "1", "true", "yes", "on":
		return true
	case "0", "false", "no", "off":
		return false
	default:
		return fallback
	}
}

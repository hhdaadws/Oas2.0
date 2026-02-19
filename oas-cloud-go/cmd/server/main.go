package main

import (
	"log"

	"oas-cloud-go/internal/cache"
	"oas-cloud-go/internal/config"
	"oas-cloud-go/internal/models"
	"oas-cloud-go/internal/server"

	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

func main() {
	cfg := config.Load()

	db, err := gorm.Open(postgres.Open(cfg.DatabaseURL), &gorm.Config{})
	if err != nil {
		log.Fatalf("failed to connect database: %v", err)
	}

	if err := models.AutoMigrate(db); err != nil {
		log.Fatalf("failed to migrate database: %v", err)
	}

	redisStore, err := cache.NewRedisStore(cfg)
	if err != nil {
		log.Fatalf("failed to connect redis: %v", err)
	}
	defer redisStore.Close()

	app := server.New(cfg, db, redisStore)
	if err := app.Run(); err != nil {
		log.Fatalf("server stopped with error: %v", err)
	}
}

package server

import (
	"net/http"
	"sync"
	"testing"
	"time"

	"oas-cloud-go/internal/models"
)

func TestRegisterByCodeConcurrentOnlyOneSuccess(t *testing.T) {
	srv, db := setupTestServer(t)

	manager := createActiveManager(t, db, "manager_concurrent", "passwordConcurrent123")
	code := models.UserActivationCode{
		ManagerID:    manager.ID,
		UserType:     models.UserTypeDaily,
		Code:         "uac_concurrent_once",
		DurationDays: 30,
		Status:       models.CodeStatusUnused,
		CreatedAt:    time.Now().UTC(),
	}
	if err := db.Create(&code).Error; err != nil {
		t.Fatalf("create activation code failed: %v", err)
	}

	const workers = 12
	var wg sync.WaitGroup
	results := make(chan int, workers)

	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			resp := doJSONRequest(
				t,
				srv.router,
				http.MethodPost,
				"/api/v1/user/auth/register-by-code",
				map[string]any{"code": "uac_concurrent_once"},
				"",
			)
			results <- resp.Code
		}()
	}
	wg.Wait()
	close(results)

	successCount := 0
	for code := range results {
		if code == http.StatusCreated {
			successCount++
		}
	}
	if successCount != 1 {
		t.Fatalf("expected exactly 1 success, got %d", successCount)
	}

	var usersCount int64
	if err := db.Model(&models.User{}).Count(&usersCount).Error; err != nil {
		t.Fatalf("count users failed: %v", err)
	}
	if usersCount != 1 {
		t.Fatalf("expected users_count=1, got %d", usersCount)
	}

	var refreshed models.UserActivationCode
	if err := db.Where("id = ?", code.ID).First(&refreshed).Error; err != nil {
		t.Fatalf("reload activation code failed: %v", err)
	}
	if refreshed.Status != models.CodeStatusUsed {
		t.Fatalf("expected activation code used, got %s", refreshed.Status)
	}
}

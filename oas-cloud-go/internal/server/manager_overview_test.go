package server

import (
	"net/http"
	"testing"
	"time"

	"oas-cloud-go/internal/models"
)

func TestManagerOverviewReturnsAggregatedStats(t *testing.T) {
	srv, db := setupTestServer(t)

	manager := createActiveManager(t, db, "manager_overview", "passwordOverview123")
	now := time.Now().UTC()

	users := []models.User{
		{
			AccountNo: "U_OVERVIEW_ACTIVE",
			ManagerID: manager.ID,
			UserType:  models.UserTypeDaily,
			Status:    models.UserStatusActive,
			ExpiresAt: ptrTime(now.Add(10 * 24 * time.Hour)),
			CreatedBy: "manager_create",
			CreatedAt: now,
			UpdatedAt: now,
		},
		{
			AccountNo: "U_OVERVIEW_EXPIRED",
			ManagerID: manager.ID,
			UserType:  models.UserTypeShuaka,
			Status:    models.UserStatusExpired,
			ExpiresAt: ptrTime(now.Add(-24 * time.Hour)),
			CreatedBy: "manager_create",
			CreatedAt: now,
			UpdatedAt: now,
		},
	}
	if err := db.Create(&users).Error; err != nil {
		t.Fatalf("create users failed: %v", err)
	}

	jobs := []models.TaskJob{
		{
			ManagerID:   manager.ID,
			UserID:      users[0].ID,
			TaskType:    "sign_in",
			Priority:    50,
			ScheduledAt: now,
			Status:      models.JobStatusPending,
			MaxAttempts: 3,
			CreatedAt:   now,
			UpdatedAt:   now,
		},
		{
			ManagerID:   manager.ID,
			UserID:      users[0].ID,
			TaskType:    "guild",
			Priority:    60,
			ScheduledAt: now,
			Status:      models.JobStatusRunning,
			MaxAttempts: 3,
			CreatedAt:   now,
			UpdatedAt:   now,
		},
	}
	if err := db.Create(&jobs).Error; err != nil {
		t.Fatalf("create jobs failed: %v", err)
	}
	failEvent := models.TaskJobEvent{
		JobID:     jobs[1].ID,
		EventType: "fail",
		Message:   "boom",
		EventAt:   now,
	}
	if err := db.Create(&failEvent).Error; err != nil {
		t.Fatalf("create fail event failed: %v", err)
	}

	loginResp := doJSONRequest(
		t,
		srv.router,
		http.MethodPost,
		"/api/v1/manager/auth/login",
		map[string]any{
			"username": manager.Username,
			"password": "passwordOverview123",
		},
		"",
	)
	if loginResp.Code != http.StatusOK {
		t.Fatalf("manager login failed, status=%d, body=%s", loginResp.Code, loginResp.Body.String())
	}
	token := extractTokenFromBody(t, loginResp.Body.Bytes())
	if token == "" {
		t.Fatalf("token should not be empty")
	}

	overviewResp := doJSONRequest(
		t,
		srv.router,
		http.MethodGet,
		"/api/v1/manager/overview",
		nil,
		token,
	)
	if overviewResp.Code != http.StatusOK {
		t.Fatalf("overview should success, status=%d body=%s", overviewResp.Code, overviewResp.Body.String())
	}
	payload := decodeBodyMap(t, overviewResp.Body.Bytes())
	userStats, ok := payload["user_stats"].(map[string]any)
	if !ok {
		t.Fatalf("user_stats should be an object")
	}
	if int(userStats["total"].(float64)) != 2 {
		t.Fatalf("expected user total 2, got %v", userStats["total"])
	}
	jobStats, ok := payload["job_stats"].(map[string]any)
	if !ok {
		t.Fatalf("job_stats should be an object")
	}
	if int(jobStats["pending"].(float64)) != 1 || int(jobStats["running"].(float64)) != 1 {
		t.Fatalf("unexpected job stats: %+v", jobStats)
	}
	if int(payload["recent_failures_24h"].(float64)) != 1 {
		t.Fatalf("expected recent_failures_24h=1, got %v", payload["recent_failures_24h"])
	}
}

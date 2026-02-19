package server

import (
	"net/http"
	"testing"
	"time"

	"oas-cloud-go/internal/models"

	"gorm.io/datatypes"
)

func TestManagerCannotAccessOtherManagersUserTasks(t *testing.T) {
	srv, db := setupTestServer(t)

	managerA := createActiveManager(t, db, "manager_a", "passwordA123")
	managerB := createActiveManager(t, db, "manager_b", "passwordB123")

	user := models.User{
		AccountNo: "U_PERMISSION_001",
		ManagerID: managerB.ID,
		UserType:  models.UserTypeDaily,
		Status:    models.UserStatusActive,
		ExpiresAt: ptrTime(time.Now().UTC().Add(7 * 24 * time.Hour)),
		CreatedBy: "manager_create",
		CreatedAt: time.Now().UTC(),
		UpdatedAt: time.Now().UTC(),
	}
	if err := db.Create(&user).Error; err != nil {
		t.Fatalf("create user failed: %v", err)
	}
	taskCfg := models.UserTaskConfig{
		UserID:     user.ID,
		TaskConfig: datatypes.JSONMap{"签到": map[string]any{"enabled": true}},
		UpdatedAt:  time.Now().UTC(),
		Version:    1,
	}
	if err := db.Create(&taskCfg).Error; err != nil {
		t.Fatalf("create task config failed: %v", err)
	}

	loginResp := doJSONRequest(
		t,
		srv.router,
		http.MethodPost,
		"/api/v1/manager/auth/login",
		map[string]any{
			"username": managerA.Username,
			"password": "passwordA123",
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

	resp := doJSONRequest(
		t,
		srv.router,
		http.MethodGet,
		"/api/v1/manager/users/"+itoa(user.ID)+"/tasks",
		nil,
		token,
	)
	if resp.Code != http.StatusForbidden {
		t.Fatalf("expected 403, got %d, body=%s", resp.Code, resp.Body.String())
	}
}

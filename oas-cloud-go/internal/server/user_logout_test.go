package server

import (
	"net/http"
	"testing"
	"time"

	"oas-cloud-go/internal/models"
)

func TestUserLogoutRevokesCurrentToken(t *testing.T) {
	srv, db := setupTestServer(t)

	manager := createActiveManager(t, db, "manager_logout", "passwordLogout123")
	user := models.User{
		AccountNo: "U_LOGOUT_001",
		ManagerID: manager.ID,
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

	rawToken, _, err := srv.issueUserToken(user.ID, "test-device")
	if err != nil {
		t.Fatalf("issue user token failed: %v", err)
	}

	logoutResp := doJSONRequest(
		t,
		srv.router,
		http.MethodPost,
		"/api/v1/user/auth/logout",
		map[string]any{"all": false},
		rawToken,
	)
	if logoutResp.Code != http.StatusOK {
		t.Fatalf("logout should success, got status=%d, body=%s", logoutResp.Code, logoutResp.Body.String())
	}

	taskResp := doJSONRequest(
		t,
		srv.router,
		http.MethodGet,
		"/api/v1/user/me/tasks",
		nil,
		rawToken,
	)
	if taskResp.Code != http.StatusUnauthorized {
		t.Fatalf("revoked token should be unauthorized, got status=%d, body=%s", taskResp.Code, taskResp.Body.String())
	}
}
